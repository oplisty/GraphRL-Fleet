from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from policy.gymnasium_qlearning import (
    GymLogisticsEnv,
    GymLogisticsEnvConfig,
    RULE_LIBRARY,
    TrainingConfig,
    evaluate_policy,
    train_q_learning,
)


def _write_csv(rows: list[dict[str, float]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train tabular Q-learning hyper-heuristic with Gymnasium")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--train-scales", nargs="+", choices=["small", "medium", "large"], default=None)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--charging-strategy", choices=["optimal_station", "nearest_station"], default="optimal_station")
    parser.add_argument("--charging-action-mode", choices=["all", "best_charge", "nearest_charge"], default="all")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--seed-stride", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument("--gamma", type=float, default=0.95)
    parser.add_argument("--epsilon", type=float, default=0.2)
    parser.add_argument("--epsilon-decay", type=float, default=0.995)
    parser.add_argument("--epsilon-min", type=float, default=0.05)
    parser.add_argument("--eval-episodes", type=int, default=5)
    parser.add_argument("--checkpoint-interval", type=int, default=0)
    parser.add_argument("--early-stop-patience", type=int, default=0)
    parser.add_argument("--early-stop-min-delta", type=float, default=0.0)
    parser.add_argument("--out-dir", default="policy/gymnasium_qlearning/output")
    args = parser.parse_args()

    train_scales = tuple(args.train_scales) if args.train_scales else (args.scale,)

    env_cfg = GymLogisticsEnvConfig(
        scale=args.scale,
        max_steps=args.max_steps,
        charging_strategy=args.charging_strategy,
        charging_action_mode=args.charging_action_mode,
        random_seed=args.seed,
    )
    train_cfg = TrainingConfig(
        episodes=args.episodes,
        alpha=args.alpha,
        gamma=args.gamma,
        epsilon=args.epsilon,
        epsilon_decay=args.epsilon_decay,
        epsilon_min=args.epsilon_min,
        eval_episodes=args.eval_episodes,
        seed_stride=args.seed_stride,
        scales=train_scales,
        checkpoint_interval=args.checkpoint_interval,
        early_stop_patience=args.early_stop_patience,
        early_stop_min_delta=args.early_stop_min_delta,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    agent, history, summary = train_q_learning(env_cfg, train_cfg, checkpoint_dir=out_dir / "checkpoints")
    eval_rows = evaluate_policy(agent, env_cfg, episodes=train_cfg.eval_episodes)

    q_path = agent.save(out_dir / "q_table.json")
    _write_json(history, out_dir / "train_history.json")
    _write_json(eval_rows, out_dir / "eval_summary.json")
    _write_json(asdict(summary), out_dir / "training_summary.json")
    _write_json(asdict(train_cfg), out_dir / "training_config.json")
    action_names = list(GymLogisticsEnv(env_cfg).action_names)
    _write_json(
        {
            "action_names": action_names,
            "train_scales": list(train_scales),
            "selected_eval_scale": env_cfg.scale,
            "charging_action_mode": env_cfg.charging_action_mode,
        },
        out_dir / "run_meta.json",
    )
    _write_csv(history, out_dir / "train_history.csv")
    _write_csv(eval_rows, out_dir / "eval_summary.csv")

    print("=== Gymnasium Q-Learning Training Complete ===")
    print(f"q_table           : {q_path}")
    print(f"train_history     : {out_dir / 'train_history.json'}")
    print(f"eval_summary      : {out_dir / 'eval_summary.json'}")
    print(f"training_summary  : {out_dir / 'training_summary.json'}")
    print(f"episodes_ran      : {summary.episodes_ran}")
    print(f"best_eval_episode : {summary.best_episode}")
    print(f"best_eval_score   : {summary.best_eval_score:.4f}")
    print(f"stop_reason       : {summary.stop_reason}")
    if eval_rows:
        last = eval_rows[-1]
        print(f"final_score       : {last['final_score']:.4f}")
        print(f"completed_tasks   : {last['completed_tasks']:.0f}")
        print(f"expired_tasks     : {last['expired_tasks']:.0f}")


if __name__ == "__main__":
    main()
