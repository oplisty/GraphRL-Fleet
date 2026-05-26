from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from Framework.core import Environment
from Framework.examples.run_baseline import build_environment

from .heuristics import RULE_LIBRARY
from .state_encoder import StateEncoder


DECISION_EVENT_TYPES = {
    "task_released",
    "task_completed",
    "vehicle_reached_station",
    "vehicle_finished_charging",
    "vehicle_became_idle",
}


@dataclass(slots=True)
class GymLogisticsEnvConfig:
    scale: str = "small"
    max_steps: int = 180
    charging_strategy: str = "optimal_station"
    charging_action_mode: str = "all"
    random_seed: int = 7
    collaborative_task_ratio: float = 0.0
    enable_collaborative_tasks: bool = False
    auto_collaborative_dispatch: bool = False


class GymLogisticsEnv(gym.Env[np.ndarray, np.int64]):
    """Gymnasium wrapper for tabular Q-learning over heuristic choices."""

    metadata = {"render_modes": []}

    ACTION_NAMES = tuple(rule.name for rule in RULE_LIBRARY)

    def __init__(self, config: GymLogisticsEnvConfig | None = None):
        super().__init__()
        self.config = config or GymLogisticsEnvConfig()
        self.rule_library = self._select_rule_library()
        self.action_names = tuple(rule.name for rule in self.rule_library)
        self.encoder = StateEncoder()
        self.action_space = spaces.Discrete(len(self.action_names))
        self.observation_space = spaces.MultiDiscrete(np.array([3, 3, 3, 3, 3], dtype=np.int64))
        self.env: Environment | None = None
        self.last_metrics: dict[str, float] = {}
        self._last_decision_event: str = "reset"
        self._reset_environment()

    def _select_rule_library(self):
        mode = self.config.charging_action_mode
        if mode == "best_charge":
            return tuple(rule for rule in RULE_LIBRARY if rule.charging_strategy == "optimal_station")
        if mode == "nearest_charge":
            return tuple(rule for rule in RULE_LIBRARY if rule.charging_strategy == "nearest_station")
        return RULE_LIBRARY

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self.config.random_seed = seed
        self._reset_environment()
        obs = self._get_observation()
        info = self._build_info()
        return obs, info

    def step(self, action: int):
        assert self.env is not None
        rule = self.rule_library[action]

        prev_score = self.env.total_score
        prev_distance = sum(vehicle.total_distance for vehicle in self.env.vehicles.values())
        prev_completed = len(self.env.completed_task_ids)
        prev_expired = len(self.env.expired_task_ids)
        prev_charge_starts = self._count_vehicle_events("charge_start")

        applied_actions = rule.apply(self.env)
        self.env.step(actions=applied_actions)
        decision_event = self._last_decision_event

        while self.env.current_time < self.env.end_time and not self._has_decision_event():
            self.env.step(actions=None)
            decision_event = self._last_decision_event

        obs = self._get_observation()
        reward = self._compute_reward(
            prev_score=prev_score,
            prev_distance=prev_distance,
            prev_completed=prev_completed,
            prev_expired=prev_expired,
            prev_charge_starts=prev_charge_starts,
        )
        terminated = self.env.current_time >= self.env.end_time
        truncated = False
        info = self._build_info(action=action, reward=reward)
        info["decision_event"] = decision_event
        info["applied_action_count"] = len(applied_actions)
        return obs, reward, terminated, truncated, info

    def render(self):
        return self._build_info()

    def close(self):
        return None

    def _reset_environment(self) -> None:
        self.env = build_environment(
            scale=self.config.scale,
            scheduler_name="nearest",
            seed=self.config.random_seed,
            collaborative_task_ratio=self.config.collaborative_task_ratio,
            enable_collaborative_tasks=self.config.enable_collaborative_tasks,
            auto_collaborative_dispatch=self.config.auto_collaborative_dispatch,
            charging_strategy=self.config.charging_strategy,
        )
        self.env.end_time = self.config.max_steps
        self.env.config.end_time = self.config.max_steps
        self.last_metrics = self._snapshot_metrics()
        self._last_decision_event = "reset"

    def _has_decision_event(self) -> bool:
        assert self.env is not None
        previous_time = self.env.current_time - self.env.config.time_step
        previous_event_count = self.last_metrics.get("event_count", 0.0)
        new_events = self.env.logger.events[int(previous_event_count):]
        for event in new_events:
            if event.get("time") != previous_time:
                continue
            event_type = str(event.get("event_type", ""))
            if event_type in DECISION_EVENT_TYPES:
                self._last_decision_event = event_type
                self.last_metrics = self._snapshot_metrics()
                return True
        self.last_metrics = self._snapshot_metrics()
        return False

    def _compute_reward(
        self,
        *,
        prev_score: float,
        prev_distance: float,
        prev_completed: int,
        prev_expired: int,
        prev_charge_starts: int,
    ) -> float:
        assert self.env is not None
        delta_score = self.env.total_score - prev_score
        delta_distance = sum(vehicle.total_distance for vehicle in self.env.vehicles.values()) - prev_distance
        delta_completed = len(self.env.completed_task_ids) - prev_completed
        delta_expired = len(self.env.expired_task_ids) - prev_expired
        delta_charge_starts = self._count_vehicle_events("charge_start") - prev_charge_starts

        emergency_unserved = sum(
            1
            for task_id in self.env.pending_task_ids
            if self.env.tasks[task_id].deadline - self.env.current_time <= 10
        )

        reward = float(delta_score)
        reward += 20.0 * delta_completed
        reward -= 0.1 * delta_distance
        reward -= 5.0 * max(0, delta_expired)
        reward -= 2.0 * emergency_unserved
        reward -= 0.5 * max(0, delta_charge_starts)
        return reward

    def _count_vehicle_events(self, event_type: str) -> int:
        assert self.env is not None
        return sum(1 for log in self.env.logger.vehicle_logs if log.get("event_type") == event_type)

    def _get_observation(self) -> np.ndarray:
        assert self.env is not None
        return np.asarray(self.encoder.encode(self.env).as_tuple(), dtype=np.int64)

    def _snapshot_metrics(self) -> dict[str, float]:
        assert self.env is not None
        return {
            "score": float(self.env.total_score),
            "completed": float(len(self.env.completed_task_ids)),
            "expired": float(len(self.env.expired_task_ids)),
            "event_count": float(len(self.env.logger.events)),
        }

    def _build_info(self, action: int | None = None, reward: float | None = None) -> dict[str, Any]:
        assert self.env is not None
        info = {
            "time": self.env.current_time,
            "total_score": self.env.total_score,
            "completed_tasks": len(self.env.completed_task_ids),
            "expired_tasks": len(self.env.expired_task_ids),
            "pending_tasks": len(self.env.pending_task_ids),
            "charging_strategy": self.env.config.charging_strategy,
        }
        if action is not None:
            info["action"] = self.action_names[action]
        if reward is not None:
            info["reward"] = reward
        return info
