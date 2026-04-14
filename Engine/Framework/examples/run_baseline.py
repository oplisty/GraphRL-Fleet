from __future__ import annotations

import argparse
from pathlib import Path

from Framework.core import Environment, SimulationConfig, Vehicle, preset_scenario
from Framework.generator import generate_dynamic_tasks, generate_random_map
from Framework.examples.yaml_config import parse_args_with_yaml
from Framework.scheduler import EarliestDeadlineScheduler, HeaviestTaskScheduler, NearestTaskScheduler


def build_environment(
    scale: str,
    scheduler_name: str,
    collaborative_task_ratio: float = 0.0,
    enable_collaborative_tasks: bool = True,
    auto_collaborative_dispatch: bool = True,
    charging_strategy: str = "optimal_station",
) -> Environment:
    scenario = preset_scenario(scale)
    scenario.collaborative_task_ratio = collaborative_task_ratio
    map_bundle = generate_random_map(scenario)
    tasks = generate_dynamic_tasks(scenario, map_bundle.task_candidate_nodes)

    vehicles = [
        Vehicle(
            id=i,
            vehicle_type="standard_ev",
            current_node=map_bundle.depot.node_id,
            battery=scenario.vehicle_battery_capacity,
            battery_capacity=scenario.vehicle_battery_capacity,
            load_capacity=scenario.vehicle_load_capacity,
            speed=scenario.vehicle_speed,
            energy_per_km=scenario.vehicle_energy_per_km,
        )
        for i in range(scenario.num_vehicles)
    ]

    sim_config = SimulationConfig(
        end_time=scenario.horizon,
        enable_collaborative_tasks=enable_collaborative_tasks,
        auto_collaborative_dispatch=auto_collaborative_dispatch,
        charging_strategy=charging_strategy if charging_strategy in {"optimal_station", "nearest_station"} else "optimal_station",
    )

    if scheduler_name == "nearest":
        scheduler = NearestTaskScheduler()
    elif scheduler_name == "earliest_deadline":
        scheduler = EarliestDeadlineScheduler()
    else:
        scheduler = HeaviestTaskScheduler()

    return Environment(
        graph=map_bundle.graph,
        depot=map_bundle.depot,
        vehicles=vehicles,
        tasks=tasks,
        stations=map_bundle.stations,
        config=sim_config,
        scheduler=scheduler,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline EV logistics simulation")
    parser.add_argument("--config", default=None, help="YAML config path")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--scheduler", choices=["nearest", "heaviest", "earliest_deadline"], default="nearest")
    parser.add_argument("--charging-strategy", choices=["optimal_station", "nearest_station"], default="optimal_station")
    parser.add_argument("--collaborative-task-ratio", type=float, default=0.0)
    parser.add_argument("--disable-collaborative-tasks", action="store_true")
    parser.add_argument("--disable-auto-collaborative-dispatch", action="store_true")
    parser.add_argument("--out", default="Framework/output/baseline")
    args = parse_args_with_yaml(parser)

    env = build_environment(
        scale=args.scale,
        scheduler_name=args.scheduler,
        collaborative_task_ratio=args.collaborative_task_ratio,
        enable_collaborative_tasks=not args.disable_collaborative_tasks,
        auto_collaborative_dispatch=not args.disable_auto_collaborative_dispatch,
        charging_strategy=args.charging_strategy,
    )
    summary = env.run()

    out_dir = Path(args.out) / f"{args.scale}_{args.scheduler}"
    env.export_logs(str(out_dir))

    print("Simulation Summary")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    print(f"- logs: {out_dir}")


if __name__ == "__main__":
    main()
