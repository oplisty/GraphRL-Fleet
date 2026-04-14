from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import json
import random
from statistics import mean

import numpy as np

from .env import GymLogisticsEnv, GymLogisticsEnvConfig


@dataclass(slots=True)
class TrainingConfig:
    episodes: int = 200
    alpha: float = 0.1
    gamma: float = 0.95
    epsilon: float = 0.2
    epsilon_decay: float = 0.995
    epsilon_min: float = 0.05
    eval_episodes: int = 5
    seed_stride: int = 1
    scales: tuple[str, ...] = ("small",)
    checkpoint_interval: int = 0
    early_stop_patience: int = 0
    early_stop_min_delta: float = 0.0


@dataclass(slots=True)
class TrainingSummary:
    best_eval_score: float
    best_episode: int
    final_epsilon: float
    episodes_ran: int
    stop_reason: str


class QLearningAgent:
    def __init__(self, action_size: int, state_shape: tuple[int, ...], alpha: float, gamma: float):
        self.action_size = action_size
        self.state_shape = state_shape
        self.alpha = alpha
        self.gamma = gamma
        self.q_table = np.zeros(state_shape + (action_size,), dtype=np.float64)

    def select_action(self, state: np.ndarray, epsilon: float) -> int:
        if random.random() < epsilon:
            return random.randrange(self.action_size)
        return int(np.argmax(self.q_table[tuple(state)]))

    def update(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, terminated: bool) -> None:
        state_key = tuple(state)
        next_key = tuple(next_state)
        best_next = 0.0 if terminated else float(np.max(self.q_table[next_key]))
        td_target = reward + self.gamma * best_next
        td_error = td_target - self.q_table[state_key][action]
        self.q_table[state_key][action] += self.alpha * td_error

    def save(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state_shape": [int(v) for v in self.state_shape],
            "action_size": int(self.action_size),
            "alpha": float(self.alpha),
            "gamma": float(self.gamma),
            "q_table": self.q_table.tolist(),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    @classmethod
    def load(cls, path: str | Path) -> "QLearningAgent":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        agent = cls(
            action_size=int(payload["action_size"]),
            state_shape=tuple(int(v) for v in payload["state_shape"]),
            alpha=float(payload["alpha"]),
            gamma=float(payload["gamma"]),
        )
        agent.q_table = np.asarray(payload["q_table"], dtype=np.float64)
        return agent


def train_q_learning(
    env_config: GymLogisticsEnvConfig,
    training_config: TrainingConfig | None = None,
    checkpoint_dir: str | Path | None = None,
) -> tuple[QLearningAgent, list[dict[str, float]], TrainingSummary]:
    cfg = training_config or TrainingConfig()
    scales = cfg.scales or (env_config.scale,)
    base_env = GymLogisticsEnv(replace(env_config, scale=scales[0]))
    agent = QLearningAgent(
        action_size=base_env.action_space.n,
        state_shape=tuple(int(v) for v in base_env.observation_space.nvec.tolist()),
        alpha=cfg.alpha,
        gamma=cfg.gamma,
    )

    checkpoint_root = Path(checkpoint_dir) if checkpoint_dir is not None else None
    if checkpoint_root is not None:
        checkpoint_root.mkdir(parents=True, exist_ok=True)

    epsilon = cfg.epsilon
    history: list[dict[str, float]] = []
    best_eval_score = float("-inf")
    best_episode = -1
    stale_evals = 0
    stop_reason = "max_episodes"
    episodes_ran = 0

    for episode in range(cfg.episodes):
        scale = scales[episode % len(scales)]
        episode_seed = env_config.random_seed + episode * cfg.seed_stride
        episode_env = GymLogisticsEnv(replace(env_config, scale=scale, random_seed=episode_seed))
        state, _ = episode_env.reset(seed=episode_seed)
        total_reward = 0.0
        terminated = False
        truncated = False
        step_count = 0
        action_counts = [0 for _ in range(agent.action_size)]
        info: dict[str, float | int | str] = {}

        while not (terminated or truncated):
            action = agent.select_action(state, epsilon)
            action_counts[action] += 1
            next_state, reward, terminated, truncated, info = episode_env.step(action)
            agent.update(state, action, reward, next_state, terminated or truncated)
            state = next_state
            total_reward += reward
            step_count += 1

        greedy_eval = evaluate_policy(
            agent,
            replace(env_config, scale=scale, random_seed=episode_seed),
            episodes=cfg.eval_episodes,
        )
        mean_eval_score = mean(row["final_score"] for row in greedy_eval) if greedy_eval else 0.0
        mean_eval_reward = mean(row["total_reward"] for row in greedy_eval) if greedy_eval else 0.0

        history.append(
            {
                "episode": float(episode),
                "seed": float(episode_seed),
                "scale_index": float(episode % len(scales)),
                "scale": scale,
                "epsilon": float(epsilon),
                "total_reward": float(total_reward),
                "steps": float(step_count),
                "final_score": float(info.get("total_score", 0.0)),
                "completed_tasks": float(info.get("completed_tasks", 0.0)),
                "expired_tasks": float(info.get("expired_tasks", 0.0)),
                "eval_score_mean": float(mean_eval_score),
                "eval_reward_mean": float(mean_eval_reward),
                **{f"action_{idx}_count": float(count) for idx, count in enumerate(action_counts)},
            }
        )
        episodes_ran = episode + 1

        improved = mean_eval_score > best_eval_score + cfg.early_stop_min_delta
        if improved:
            best_eval_score = mean_eval_score
            best_episode = episode
            stale_evals = 0
            if checkpoint_root is not None:
                agent.save(checkpoint_root / "best_q_table.json")
        else:
            stale_evals += 1

        if checkpoint_root is not None and cfg.checkpoint_interval > 0 and (episode + 1) % cfg.checkpoint_interval == 0:
            agent.save(checkpoint_root / f"q_table_episode_{episode + 1}.json")

        epsilon = max(cfg.epsilon_min, epsilon * cfg.epsilon_decay)

        if cfg.early_stop_patience > 0 and stale_evals >= cfg.early_stop_patience:
            stop_reason = "early_stop"
            break

    summary = TrainingSummary(
        best_eval_score=float(best_eval_score if best_episode >= 0 else 0.0),
        best_episode=best_episode,
        final_epsilon=float(epsilon),
        episodes_ran=episodes_ran,
        stop_reason=stop_reason,
    )
    return agent, history, summary


def evaluate_policy(
    agent: QLearningAgent,
    env_config: GymLogisticsEnvConfig,
    episodes: int = 5,
) -> list[dict[str, float]]:
    env = GymLogisticsEnv(env_config)
    results: list[dict[str, float]] = []

    for episode in range(episodes):
        state, _ = env.reset(seed=env_config.random_seed + 1000 + episode)
        terminated = False
        total_reward = 0.0
        step_count = 0
        info: dict[str, float] = {}

        while not terminated:
            action = int(np.argmax(agent.q_table[tuple(state)]))
            state, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            step_count += 1
            if truncated:
                break

        results.append(
            {
                "episode": float(episode),
                "total_reward": float(total_reward),
                "steps": float(step_count),
                "final_score": float(info.get("total_score", 0.0)),
                "completed_tasks": float(info.get("completed_tasks", 0.0)),
                "expired_tasks": float(info.get("expired_tasks", 0.0)),
            }
        )

    return results
