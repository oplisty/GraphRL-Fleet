from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from Framework.core import Environment, PathFinder, Task, Vehicle, preset_scenario
from Framework.examples.run_baseline import build_environment
from Framework.scheduler import OfflinePlanScheduler


def parse_task_id_from_node(node: str) -> int | None:
    if not node.startswith("T_"):
        return None
    try:
        return int(node.split("_", 1)[1])
    except ValueError:
        return None


def build_plan_csv_from_offline_result(result_json_path: Path, out_plan_csv: Path) -> Path:
    payload = json.loads(result_json_path.read_text(encoding="utf-8"))
    routes: dict[str, list[str]] = payload["result"]["routes"]

    rows: list[dict[str, int]] = []
    for vehicle_key, route in routes.items():
        vehicle_id = int(vehicle_key)
        for node in route:
            task_id = parse_task_id_from_node(node)
            if task_id is None:
                continue
            rows.append(
                {
                    "task_id": task_id,
                    "vehicle_id": vehicle_id,
                    # 离线上帝视角中任务已知，回放时按 release_time 触发。
                    # 这里交给调度器在 env 中检查 release/pending 状态。
                    "release_time": 0,
                }
            )

    out_plan_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_plan_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "vehicle_id", "release_time"])
        writer.writeheader()
        writer.writerows(rows)

    return out_plan_csv


def remap_environment_to_offline_task_ids(env: Environment) -> None:
    """
    run_baseline 生成的 task id 通常是 0..N-1。
    你的 offline demo 结果是 1..N。
    为了直接对接，把环境任务重映射为 1..N。
    """
    old_tasks = env.tasks
    sorted_old_ids = sorted(old_tasks.keys())

    new_tasks: dict[int, Task] = {}
    for idx, old_id in enumerate(sorted_old_ids, start=1):
        t = old_tasks[old_id]
        t.id = idx
        new_tasks[idx] = t

    env.tasks = new_tasks
    env.pending_task_ids.clear()
    env.assigned_task_ids.clear()
    env.completed_task_ids.clear()
    env.expired_task_ids.clear()

    env._future_task_ids = sorted(env.tasks, key=lambda tid: env.tasks[tid].release_time)  # type: ignore[attr-defined]
    env._future_index = 0  # type: ignore[attr-defined]


def sync_environment_vehicle_count(env: Environment, expected_count: int) -> None:
    if len(env.vehicles) == expected_count:
        return

    scenario = preset_scenario("small")
    depot_node = env.depot.node_id
    new_vehicles: dict[int, Vehicle] = {}
    for i in range(expected_count):
        new_vehicles[i] = Vehicle(
            id=i,
            vehicle_type="standard_ev",
            current_node=depot_node,
            battery=scenario.vehicle_battery_capacity,
            battery_capacity=scenario.vehicle_battery_capacity,
            load_capacity=scenario.vehicle_load_capacity,
            speed=scenario.vehicle_speed,
            energy_per_km=scenario.vehicle_energy_per_km,
        )
    env.vehicles = new_vehicles


def _resolve_semantic_graph_node_id(semantic_node: str, task_origin_map: dict[int, int], depot_node_id: int) -> int | None:
    if semantic_node in {"DEPOT", "DEPOT_START", "DEPOT_END"}:
        return depot_node_id
    if semantic_node.startswith("T_"):
        try:
            return task_origin_map[int(semantic_node.split("_", 1)[1])]
        except (ValueError, KeyError):
            return None
    return None


def build_replay_compare_payload(offline_payload: dict[str, Any], env: Environment) -> dict[str, Any]:
    routes: dict[str, list[str]] = offline_payload.get("result", {}).get("routes", {})
    task_origin_map = {task.id: task.origin_node for task in env.tasks.values()}
    depot_node_id = env.depot.node_id
    pathfinder = PathFinder(env.graph)

    vehicle_routes: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []

    for vehicle_key, semantic_route in sorted(routes.items(), key=lambda item: int(item[0])):
        vehicle_id = int(vehicle_key)
        semantic_stops: list[dict[str, Any]] = []
        engine_node_route: list[int] = []
        engine_segments: list[dict[str, Any]] = []

        prev_semantic: str | None = None
        prev_graph_node_id: int | None = None

        for seq, semantic_node in enumerate(semantic_route):
            graph_node_id = _resolve_semantic_graph_node_id(semantic_node, task_origin_map, depot_node_id)
            semantic_stops.append(
                {
                    "vehicle_id": vehicle_id,
                    "seq": seq,
                    "semantic_node": semantic_node,
                    "graph_node_id": graph_node_id,
                }
            )
            flat_rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "record_type": "semantic_stop",
                    "seq": seq,
                    "semantic_node": semantic_node,
                    "graph_node_id": graph_node_id if graph_node_id is not None else "",
                    "engine_node_id": "",
                    "segment_from": "",
                    "segment_to": "",
                }
            )

            if graph_node_id is None:
                prev_semantic = semantic_node
                prev_graph_node_id = None
                continue

            if prev_graph_node_id is None:
                if not engine_node_route:
                    engine_node_route.append(graph_node_id)
                prev_semantic = semantic_node
                prev_graph_node_id = graph_node_id
                continue

            segment_path = [graph_node_id] if prev_graph_node_id == graph_node_id else pathfinder.shortest_path(prev_graph_node_id, graph_node_id)
            if segment_path:
                if not engine_node_route:
                    engine_node_route.extend(segment_path)
                elif engine_node_route[-1] == segment_path[0]:
                    engine_node_route.extend(segment_path[1:])
                else:
                    engine_node_route.extend(segment_path)

            engine_segments.append(
                {
                    "from_semantic_node": prev_semantic,
                    "to_semantic_node": semantic_node,
                    "node_path": segment_path,
                }
            )
            prev_semantic = semantic_node
            prev_graph_node_id = graph_node_id

        for node_seq, node_id in enumerate(engine_node_route):
            flat_rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "record_type": "engine_node",
                    "seq": node_seq,
                    "semantic_node": "",
                    "graph_node_id": node_id,
                    "engine_node_id": node_id,
                    "segment_from": "",
                    "segment_to": "",
                }
            )

        for seg_idx, segment in enumerate(engine_segments):
            flat_rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "record_type": "engine_segment",
                    "seq": seg_idx,
                    "semantic_node": "",
                    "graph_node_id": "",
                    "engine_node_id": json.dumps(segment["node_path"], ensure_ascii=False),
                    "segment_from": segment["from_semantic_node"],
                    "segment_to": segment["to_semantic_node"],
                }
            )

        vehicle_routes.append(
            {
                "vehicle_id": vehicle_id,
                "milp_semantic_route": [item["semantic_node"] for item in semantic_stops],
                "semantic_stops": semantic_stops,
                "engine_node_route": engine_node_route,
                "engine_segments": engine_segments,
            }
        )

    return {
        "vehicle_routes": vehicle_routes,
        "flat_rows": flat_rows,
    }


def write_replay_compare_exports(out_dir: Path, offline_payload: dict[str, Any], env: Environment) -> None:
    compare_payload = build_replay_compare_payload(offline_payload, env)
    summary_path = out_dir / "summary.json"
    route_compare_csv = out_dir / "route_compare.csv"

    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["replay_compare"] = compare_payload
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with route_compare_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "vehicle_id",
                "record_type",
                "seq",
                "semantic_node",
                "graph_node_id",
                "engine_node_id",
                "segment_from",
                "segment_to",
            ],
        )
        writer.writeheader()
        writer.writerows(compare_payload["flat_rows"])


def main() -> None:
    parser = argparse.ArgumentParser(description="对接离线 MILP 结果到 Engine 回放")
    parser.add_argument(
        "--offline-json",
        default="policy/offline/output/god_view_milp_summary.json",
        help="离线 MILP 输出的 summary json 路径",
    )
    parser.add_argument(
        "--plan-csv",
        default="policy/offline/output/engine_plan.csv",
        help="生成/读取的 Engine 计划 CSV 路径",
    )
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--out", default="Framework/output/offline_plan_replay")
    args = parser.parse_args()

    offline_json = Path(args.offline_json)
    plan_csv = Path(args.plan_csv)

    build_plan_csv_from_offline_result(offline_json, plan_csv)

    payload = json.loads(offline_json.read_text(encoding="utf-8"))
    routes = payload["result"]["routes"]
    expected_vehicles = len(routes)

    env = build_environment(
        scale=args.scale,
        scheduler_name="nearest",
        collaborative_task_ratio=0.0,
        enable_collaborative_tasks=False,
        auto_collaborative_dispatch=False,
    )

    remap_environment_to_offline_task_ids(env)
    sync_environment_vehicle_count(env, expected_vehicles)

    scheduler = OfflinePlanScheduler.from_csv(plan_csv)
    env.scheduler = scheduler

    summary = env.run()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    env.export_logs(str(out_dir / "logs"))
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_replay_compare_exports(out_dir=out_dir, offline_payload=payload, env=env)

    print("=== Offline Plan Replay Summary ===")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    print(f"- plan_csv: {plan_csv}")
    print(f"- logs: {out_dir / 'logs'}")
    print(f"- summary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()

