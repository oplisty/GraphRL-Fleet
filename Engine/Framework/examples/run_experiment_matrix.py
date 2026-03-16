from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from Framework.examples.yaml_config import parse_args_with_yaml
from Framework.examples.run_baseline import build_environment as build_random_environment
from Framework.examples.run_panyu_processed_baseline import build_environment as build_panyu_environment


def run_random_case(
    scale: str,
    scheduler: str,
    collaborative_task_ratio: float,
    disable_collaborative_tasks: bool,
    disable_auto_collaborative_dispatch: bool,
    export_logs: bool,
    out_dir: Path,
) -> dict:
    env = build_random_environment(
        scale=scale,
        scheduler_name=scheduler,
        collaborative_task_ratio=collaborative_task_ratio,
        enable_collaborative_tasks=not disable_collaborative_tasks,
        auto_collaborative_dispatch=not disable_auto_collaborative_dispatch,
    )
    summary = env.run()

    log_dir = out_dir / "logs" / f"random_{scale}_{scheduler}"
    if export_logs:
        env.export_logs(str(log_dir))

    return {
        "scenario": f"random_{scale}",
        "scheduler": scheduler,
        "log_dir": str(log_dir) if export_logs else "",
        **summary,
    }


def run_panyu_case(
    processed_dir: str,
    scheduler: str,
    task_mode: str,
    vehicles: int,
    tasks: int,
    horizon: int,
    seed: int,
    battery_capacity: float,
    load_capacity: float,
    speed: float,
    energy_per_km: float,
    task_max_weight: float,
    task_ttl_min: int,
    task_ttl_max: int,
    collaborative_task_ratio: float,
    collaborative_weight_min_scale: float,
    collaborative_weight_max_scale: float,
    disable_collaborative_tasks: bool,
    disable_auto_collaborative_dispatch: bool,
    station_piles: int,
    station_rate: float,
    export_logs: bool,
    out_dir: Path,
) -> dict:
    args = SimpleNamespace(
        processed_dir=processed_dir,
        scheduler=scheduler,
        task_mode=task_mode,
        vehicles=vehicles,
        tasks=tasks,
        horizon=horizon,
        seed=seed,
        battery_capacity=battery_capacity,
        load_capacity=load_capacity,
        speed=speed,
        energy_per_km=energy_per_km,
        task_max_weight=task_max_weight,
        task_ttl_min=task_ttl_min,
        task_ttl_max=task_ttl_max,
        collaborative_task_ratio=collaborative_task_ratio,
        collaborative_weight_min_scale=collaborative_weight_min_scale,
        collaborative_weight_max_scale=collaborative_weight_max_scale,
        disable_collaborative_tasks=disable_collaborative_tasks,
        disable_auto_collaborative_dispatch=disable_auto_collaborative_dispatch,
        station_piles=station_piles,
        station_rate=station_rate,
        out=str(out_dir / "logs"),
    )
    env = build_panyu_environment(args)
    summary = env.run()

    log_dir = out_dir / "logs" / f"panyu_processed_{scheduler}_v{vehicles}_t{tasks}"
    if export_logs:
        env.export_logs(str(log_dir))

    return {
        "scenario": "panyu_processed",
        "scheduler": scheduler,
        "log_dir": str(log_dir) if export_logs else "",
        **summary,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict]) -> None:
    lines: list[str] = [
        "# Experiment Matrix Summary",
        "",
        "| scenario | scheduler | total_score | completed | expired | pending | total_distance | utilization | avg_queue | avg_completion_time | avg_charge_wait |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        lines.append(
            "| {scenario} | {scheduler} | {total_score:.2f} | {completed} | {expired} | {pending} | "
            "{total_distance:.2f} | {avg_vehicle_utilization:.4f} | {avg_station_queue_length:.4f} | "
            "{avg_task_completion_time:.2f} | {avg_charge_waiting_time:.2f} |".format(**row)
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_scales(value: str) -> list[str]:
    scales = [v.strip() for v in value.split(",") if v.strip()]
    valid = {"small", "medium", "large"}
    invalid = [s for s in scales if s not in valid]
    if invalid:
        raise ValueError(f"Invalid scales: {invalid}, choose from {sorted(valid)}")
    return scales


def main() -> None:
    parser = argparse.ArgumentParser(description="Run random + Panyu baseline matrix experiments")
    parser.add_argument("--config", default=None, help="YAML config path")
    parser.add_argument("--random-scales", default="small,medium,large")
    parser.add_argument("--no-random", action="store_true")
    parser.add_argument("--no-panyu", action="store_true")
    parser.add_argument("--random-collaborative-task-ratio", type=float, default=0.0)
    parser.add_argument("--disable-collaborative-tasks", action="store_true")
    parser.add_argument("--disable-auto-collaborative-dispatch", action="store_true")
    parser.add_argument("--processed-dir", default="Map Resource/processed/panyu")
    parser.add_argument("--panyu-task-mode", choices=["uniform_nodes", "hotspot_nodes"], default="uniform_nodes")
    parser.add_argument("--panyu-vehicles", type=int, default=10)
    parser.add_argument("--panyu-tasks", type=int, default=120)
    parser.add_argument("--panyu-horizon", type=int, default=360)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--panyu-battery-capacity", type=float, default=120.0)
    parser.add_argument("--panyu-load-capacity", type=float, default=80.0)
    parser.add_argument("--panyu-speed", type=float, default=1.5)
    parser.add_argument("--panyu-energy-per-km", type=float, default=1.0)
    parser.add_argument("--panyu-task-max-weight", type=float, default=30.0)
    parser.add_argument("--panyu-task-ttl-min", type=int, default=25)
    parser.add_argument("--panyu-task-ttl-max", type=int, default=80)
    parser.add_argument("--panyu-collaborative-task-ratio", type=float, default=0.0)
    parser.add_argument("--panyu-collaborative-weight-min-scale", type=float, default=1.1)
    parser.add_argument("--panyu-collaborative-weight-max-scale", type=float, default=1.6)
    parser.add_argument("--panyu-station-piles", type=int, default=2)
    parser.add_argument("--panyu-station-rate", type=float, default=6.0)
    parser.add_argument("--export-logs", action="store_true")
    parser.add_argument("--out", default="Framework/output/experiment_matrix")
    args = parse_args_with_yaml(parser)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scales = parse_scales(args.random_scales)
    schedulers = ["nearest", "heaviest"]

    results: list[dict] = []

    if not args.no_random:
        for scale in scales:
            for scheduler in schedulers:
                result = run_random_case(
                    scale=scale,
                    scheduler=scheduler,
                    collaborative_task_ratio=args.random_collaborative_task_ratio,
                    disable_collaborative_tasks=args.disable_collaborative_tasks,
                    disable_auto_collaborative_dispatch=args.disable_auto_collaborative_dispatch,
                    export_logs=args.export_logs,
                    out_dir=out_dir,
                )
                results.append(result)
                print(
                    f"[random/{scale}/{scheduler}] score={result['total_score']:.2f}, "
                    f"completed={result['completed']}, expired={result['expired']}"
                )

    if not args.no_panyu:
        for scheduler in schedulers:
            result = run_panyu_case(
                processed_dir=args.processed_dir,
                scheduler=scheduler,
                task_mode=args.panyu_task_mode,
                vehicles=args.panyu_vehicles,
                tasks=args.panyu_tasks,
                horizon=args.panyu_horizon,
                seed=args.seed,
                battery_capacity=args.panyu_battery_capacity,
                load_capacity=args.panyu_load_capacity,
                speed=args.panyu_speed,
                energy_per_km=args.panyu_energy_per_km,
                task_max_weight=args.panyu_task_max_weight,
                task_ttl_min=args.panyu_task_ttl_min,
                task_ttl_max=args.panyu_task_ttl_max,
                collaborative_task_ratio=args.panyu_collaborative_task_ratio,
                collaborative_weight_min_scale=args.panyu_collaborative_weight_min_scale,
                collaborative_weight_max_scale=args.panyu_collaborative_weight_max_scale,
                disable_collaborative_tasks=args.disable_collaborative_tasks,
                disable_auto_collaborative_dispatch=args.disable_auto_collaborative_dispatch,
                station_piles=args.panyu_station_piles,
                station_rate=args.panyu_station_rate,
                export_logs=args.export_logs,
                out_dir=out_dir,
            )
            results.append(result)
            print(
                f"[panyu_processed/{scheduler}] score={result['total_score']:.2f}, "
                f"completed={result['completed']}, expired={result['expired']}"
            )

    json_path = out_dir / "summary.json"
    csv_path = out_dir / "summary.csv"
    md_path = out_dir / "summary.md"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, results)
    write_markdown(md_path, results)

    print("\nSaved:")
    print(f"- {json_path}")
    print(f"- {csv_path}")
    print(f"- {md_path}")


if __name__ == "__main__":
    main()
