from __future__ import annotations

"""Run one Gymnasium environment episode with a fixed heuristic action sequence."""

import argparse
import json
from pathlib import Path

from policy.gymnasium_qlearning.env import GymLogisticsEnv, GymLogisticsEnvConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Gymnasium logistics episode")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--charging-strategy", choices=["optimal_station", "nearest_station"], default="optimal_station")
    parser.add_argument(
        "--action",
        type=int,
        default=0,
        help="Unified rule id from RULE_LIBRARY (0 nearest+best-charge, 1 edf+best-charge, 2 max-weight+best-charge, 3 best-score+best-charge, 4 nearest+nearest-charge, 5 best-score+nearest-charge)",
    )
    parser.add_argument("--out", default="policy/gymnasium_qlearning/output/single_episode.json")
    args = parser.parse_args()

    env = GymLogisticsEnv(
        GymLogisticsEnvConfig(
            scale=args.scale,
            max_steps=args.max_steps,
            charging_strategy=args.charging_strategy,
        )
    )
    state, info = env.reset()

    frames: list[dict] = [{"step": 0, "state": state.tolist(), "info": info}]
    terminated = False
    total_reward = 0.0
    step_count = 0

    while not terminated:
        state, reward, terminated, truncated, info = env.step(args.action)
        step_count += 1
        total_reward += reward
        frames.append(
            {
                "step": step_count,
                "state": state.tolist(),
                "reward": reward,
                "terminated": terminated,
                "truncated": truncated,
                "info": info,
            }
        )
        if truncated:
            break

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Gymnasium Episode Complete ===")
    print(f"steps        : {step_count}")
    print(f"total_reward : {total_reward:.4f}")
    print(f"output       : {out_path}")


if __name__ == "__main__":
    main()
