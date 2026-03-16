from __future__ import annotations

import argparse
from pathlib import Path

from Framework.core import Environment, ScenarioConfig, SimulationConfig, Vehicle
from Framework.generator import generate_dynamic_tasks, load_panyu_map
from Framework.examples.yaml_config import parse_args_with_yaml
from Framework.scheduler import HeaviestTaskScheduler, NearestTaskScheduler


def build_environment(args: argparse.Namespace) -> Environment:
    map_bundle = load_panyu_map(
        graph_json_path=args.graph_json,
        station_num_piles=args.station_piles,
        station_charge_rate=args.station_rate,
    )

    scenario = ScenarioConfig(
        num_vehicles=args.vehicles,
        num_tasks=args.tasks,
        num_stations=len(map_bundle.stations),
        num_road_nodes=len(map_bundle.task_candidate_nodes),
        map_width=1,
        map_height=1,
        horizon=args.horizon,
        vehicle_battery_capacity=args.battery_capacity,
        vehicle_load_capacity=args.load_capacity,
        vehicle_speed=args.speed,
        vehicle_energy_per_km=args.energy_per_km,
        task_max_weight=args.task_max_weight,
        task_ttl_min=args.task_ttl_min,
        task_ttl_max=args.task_ttl_max,
        collaborative_task_ratio=args.collaborative_task_ratio,
        collaborative_weight_min_scale=args.collaborative_weight_min_scale,
        collaborative_weight_max_scale=args.collaborative_weight_max_scale,
        station_num_piles=args.station_piles,
        station_charge_rate=args.station_rate,
        random_seed=args.seed,
    )

    tasks = generate_dynamic_tasks(scenario, map_bundle.task_candidate_nodes)

    vehicles = [
        Vehicle(
            id=i,
            vehicle_type="panyu_ev",
            current_node=map_bundle.depot.node_id,
            battery=args.battery_capacity,
            battery_capacity=args.battery_capacity,
            load_capacity=args.load_capacity,
            speed=args.speed,
            energy_per_km=args.energy_per_km,
        )
        for i in range(args.vehicles)
    ]

    scheduler = NearestTaskScheduler() if args.scheduler == "nearest" else HeaviestTaskScheduler()
    sim_config = SimulationConfig(
        end_time=args.horizon,
        enable_collaborative_tasks=not args.disable_collaborative_tasks,
        auto_collaborative_dispatch=not args.disable_auto_collaborative_dispatch,
    )

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
    parser = argparse.ArgumentParser(description="Run baseline simulation on fixed Panyu OSM graph")
    parser.add_argument("--config", default=None, help="YAML config path")
    parser.add_argument("--graph-json", default="Map Resource/analysis/panyu_graph.json")
    parser.add_argument("--scheduler", choices=["nearest", "heaviest"], default="nearest")
    parser.add_argument("--vehicles", type=int, default=10)
    parser.add_argument("--tasks", type=int, default=120)
    parser.add_argument("--horizon", type=int, default=360)
    parser.add_argument("--seed", type=int, default=7)

    parser.add_argument("--battery-capacity", type=float, default=120.0)
    parser.add_argument("--load-capacity", type=float, default=80.0)
    parser.add_argument("--speed", type=float, default=1.5)
    parser.add_argument("--energy-per-km", type=float, default=1.0)

    parser.add_argument("--task-max-weight", type=float, default=30.0)
    parser.add_argument("--task-ttl-min", type=int, default=25)
    parser.add_argument("--task-ttl-max", type=int, default=80)
    parser.add_argument("--collaborative-task-ratio", type=float, default=0.0)
    parser.add_argument("--collaborative-weight-min-scale", type=float, default=1.1)
    parser.add_argument("--collaborative-weight-max-scale", type=float, default=1.6)

    parser.add_argument("--station-piles", type=int, default=2)
    parser.add_argument("--station-rate", type=float, default=6.0)
    parser.add_argument("--disable-collaborative-tasks", action="store_true")
    parser.add_argument("--disable-auto-collaborative-dispatch", action="store_true")

    parser.add_argument("--out", default="Framework/output/panyu")
    args = parse_args_with_yaml(parser)

    env = build_environment(args)
    summary = env.run()

    out_dir = Path(args.out) / f"panyu_{args.scheduler}_v{args.vehicles}_t{args.tasks}"
    env.export_logs(str(out_dir))

    print("Panyu Simulation Summary")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    print(f"- logs: {out_dir}")


if __name__ == "__main__":
    main()
