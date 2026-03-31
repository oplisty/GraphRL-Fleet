from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from importlib import util as importlib_util
from pydantic import BaseModel, ConfigDict, Field

from Framework.core import (
    ChargingStation,
    Depot,
    Environment,
    Graph,
    Node,
    PathFinder,
    SimulationConfig,
    Task,
    Vehicle,
    preset_scenario,
)
from Framework.examples.run_baseline import build_environment as build_random_environment
from Framework.generator import generate_real_tasks, load_real_map_from_processed
from Framework.scheduler import HeaviestTaskScheduler, NearestTaskScheduler, OfflineRouteScheduler


app = FastAPI(title="Engine Realtime API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProblemScaleModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = "medium"
    name: str | None = None
    description: str | None = None


class SimulationStartRequest(BaseModel):
    scale: ProblemScaleModel = Field(default_factory=ProblemScaleModel)
    strategy: str = "nearest_first"
    simulationSpeed: float = 1.0
    maxSimulationTime: int = 240
    enableCollaboration: bool = False
    randomSeed: int | None = None


class OfflineSolveRequest(BaseModel):
    scale: ProblemScaleModel = Field(default_factory=ProblemScaleModel)
    maxSimulationTime: int = 240
    solver: str = "gurobi"
    chargeMode: str = "piecewise"
    timeLimit: int = 120


@dataclass
class SimulationSession:
    simulation_id: str
    env: Environment
    config_payload: dict[str, Any]
    scheduler_name: str
    simulation_speed: float
    status: str = "idle"
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    loop_task: asyncio.Task | None = None
    clients: set[WebSocket] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)


SESSIONS: dict[str, SimulationSession] = {}

DEFAULT_PANYU_BBOX = (113.243972, 22.858513, 113.569794, 23.082811)


def _parse_env_bbox() -> tuple[float, float, float, float]:
    """Read optional bbox from ENGINE_PANYU_BBOX=min_lon,min_lat,max_lon,max_lat."""
    raw = os.getenv("ENGINE_PANYU_BBOX", "").strip()
    if not raw:
        return DEFAULT_PANYU_BBOX

    try:
        values = [float(item.strip()) for item in raw.split(",")]
        if len(values) != 4:
            raise ValueError("bbox must contain 4 numbers")
        min_lon, min_lat, max_lon, max_lat = values
        if not (min_lon < max_lon and min_lat < max_lat):
            raise ValueError("bbox min/max order invalid")
        return (min_lon, min_lat, max_lon, max_lat)
    except Exception:
        # Fallback to default when env string is malformed.
        return DEFAULT_PANYU_BBOX


PANYU_BBOX = _parse_env_bbox()


def _load_offline_milp_module():
    engine_root = Path(__file__).resolve().parents[3]
    module_path = engine_root / "policy" / "offline" / "god_view_milp.py"
    if not module_path.exists():
        raise RuntimeError(f"offline milp module not found: {module_path}")

    spec = importlib_util.spec_from_file_location("policy_offline_god_view_milp", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load offline milp module spec")

    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serialize_graph_for_milp(graph: Graph) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": int(node.id),
                "x": float(node.x),
                "y": float(node.y),
                "node_type": node.node_type,
            }
            for node in graph.nodes.values()
        ],
        "edges": [
            {
                "u": int(from_id),
                "v": int(edge.to),
                "distance": float(edge.distance),
                "travel_time": float(edge.travel_time),
                "bidirectional": False,
            }
            for from_id, edge_list in graph.adj.items()
            for edge in edge_list
        ],
    }


def _build_engine_constrained_offline_instance(module: Any, scale_id: str, max_simulation_time: int):
    processed_dir = Path(__file__).resolve().parents[2] / "Map Resource" / "processed" / "panyu"
    if not processed_dir.exists():
        return module.build_tiny_demo_instance()

    scenario = preset_scenario(scale_id if scale_id in {"small", "medium", "large"} else "small")
    scenario.horizon = max_simulation_time
    scenario.collaborative_task_ratio = 0.0

    map_bundle = load_real_map_from_processed(
        processed_dir=processed_dir,
        station_num_piles=max(1, scenario.station_num_piles),
        station_charge_rate=scenario.station_charge_rate,
        bbox=PANYU_BBOX,
    )
    tasks = generate_real_tasks(
        scenario,
        candidate_node_ids=map_bundle.task_candidate_nodes,
        mode="uniform_nodes",
    )

    pathfinder = PathFinder(map_bundle.graph)
    depot_node = map_bundle.depot.node_id
    semantic_to_graph: dict[str, int] = {"DEPOT": int(depot_node)}

    offline_tasks: list[Any] = []
    for task in tasks:
        node = map_bundle.graph.nodes[task.origin_node]
        semantic_to_graph[f"T_{int(task.id)}"] = int(task.origin_node)
        offline_tasks.append(
            module.Task(
                id=int(task.id),
                x=float(node.x),
                y=float(node.y),
                demand=float(task.weight),
                release=float(task.release_time),
                deadline=float(task.deadline),
            )
        )

    offline_stations: list[Any] = []
    shortest_distances: dict[str, float] = {}
    semantic_nodes: dict[str, int] = {"DEPOT_START": depot_node, "DEPOT_END": depot_node}

    for station in map_bundle.stations.values():
        node = map_bundle.graph.nodes[station.node_id]
        semantic_to_graph[f"S_{int(station.id)}"] = int(station.node_id)
        semantic_nodes[f"S_{int(station.id)}"] = int(station.node_id)
        offline_stations.append(
            module.Station(
                id=int(station.id),
                x=float(node.x),
                y=float(node.y),
            )
        )

    for task in tasks:
        semantic_nodes[f"T_{int(task.id)}"] = int(task.origin_node)

    semantic_items = list(semantic_nodes.items())
    for from_semantic, from_graph in semantic_items:
        for to_semantic, to_graph in semantic_items:
            if from_semantic == to_semantic:
                continue
            if from_semantic == "DEPOT_END":
                continue
            if to_semantic == "DEPOT_START":
                continue
            distance = pathfinder.shortest_distance(from_graph, to_graph)
            if distance == float("inf"):
                continue
            shortest_distances[f"{from_semantic}->{to_semantic}"] = float(distance)

    graph_data = _serialize_graph_for_milp(map_bundle.graph)
    graph_data["semantic_to_graph"] = semantic_to_graph
    graph_data["shortest_distances"] = shortest_distances

    return module.OfflineInstance(
        num_vehicles=scenario.num_vehicles,
        vehicle_capacity=scenario.vehicle_load_capacity,
        battery_capacity=scenario.vehicle_battery_capacity,
        horizon=float(scenario.horizon),
        depot_x=float(map_bundle.graph.nodes[depot_node].x),
        depot_y=float(map_bundle.graph.nodes[depot_node].y),
        tasks=offline_tasks,
        stations=offline_stations,
        max_station_visits_per_station=1,
        speed_levels=(scenario.vehicle_speed,),
        energy_base_per_km=float(scenario.vehicle_energy_per_km),
        energy_speed_coeff=0.0,
        energy_load_coeff=0.0,
        linear_charge_rate=float(scenario.station_charge_rate),
        piecewise_segments=((float(scenario.vehicle_battery_capacity), float(scenario.station_charge_rate)),),
        graph_data=graph_data,
    )


def _build_offline_plan_csv_from_result(payload: dict[str, Any], out_plan_csv: Path) -> Path:
    routes: dict[str, list[str]] = payload["result"]["routes"]
    instance_tasks = payload.get("instance", {}).get("tasks", [])
    release_map = {
        int(item.get("id")): int(float(item.get("release", 0)))
        for item in instance_tasks
        if item.get("id") is not None
    }

    rows: list[dict[str, int]] = []
    for vehicle_key, route in routes.items():
        vehicle_id = int(vehicle_key)
        for node in route:
            if not isinstance(node, str) or not node.startswith("T_"):
                continue
            task_id = int(node.split("_", 1)[1])
            rows.append(
                {
                    "task_id": task_id,
                    "vehicle_id": vehicle_id,
                    "release_time": release_map.get(task_id, 0),
                }
            )

    out_plan_csv.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with out_plan_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "vehicle_id", "release_time"])
        writer.writeheader()
        writer.writerows(rows)
    return out_plan_csv


def _build_graph_from_offline_instance(instance: Any) -> tuple[Graph, dict[int, int], dict[int, int], dict[str, Any]]:
    graph_data = getattr(instance, "graph_data", None) or {}
    raw_nodes = graph_data.get("nodes") or []
    raw_edges = graph_data.get("edges") or []
    semantic_to_graph = graph_data.get("semantic_to_graph") or {}

    if raw_nodes and raw_edges and semantic_to_graph:
        graph = Graph()
        for raw_node in raw_nodes:
            graph.add_node(
                Node(
                    id=int(raw_node["id"]),
                    x=float(raw_node["x"]),
                    y=float(raw_node["y"]),
                    node_type=str(raw_node.get("node_type", "road")),
                )
            )

        for raw_edge in raw_edges:
            graph.add_edge(
                int(raw_edge["u"]),
                int(raw_edge["v"]),
                distance=float(raw_edge["distance"]),
                travel_time=float(raw_edge.get("travel_time", raw_edge["distance"])),
                bidirectional=bool(raw_edge.get("bidirectional", True)),
            )

        depot_node_id = int(semantic_to_graph["DEPOT"])
        station_node_map = {
            int(station.id): int(semantic_to_graph[f"S_{int(station.id)}"])
            for station in instance.stations
            if f"S_{int(station.id)}" in semantic_to_graph
        }
        task_node_map = {
            int(task.id): int(semantic_to_graph[f"T_{int(task.id)}"])
            for task in instance.tasks
            if f"T_{int(task.id)}" in semantic_to_graph
        }
        replay_meta = {
            "semantic_to_graph": semantic_to_graph,
            "depot_node_id": depot_node_id,
        }
        return graph, task_node_map, station_node_map, replay_meta

    graph = Graph()
    depot_node_id = 0
    graph.add_node(Node(id=depot_node_id, x=float(instance.depot_x), y=float(instance.depot_y), node_type="depot"))

    station_node_map: dict[int, int] = {}
    next_node_id = 1
    for station in instance.stations:
        node_id = next_node_id
        next_node_id += 1
        station_node_map[int(station.id)] = node_id
        graph.add_node(Node(id=node_id, x=float(station.x), y=float(station.y), node_type="station"))

    task_node_map: dict[int, int] = {}
    for task in instance.tasks:
        node_id = next_node_id
        next_node_id += 1
        task_node_map[int(task.id)] = node_id
        graph.add_node(Node(id=node_id, x=float(task.x), y=float(task.y), node_type="task_point"))

    node_ids = list(graph.nodes.keys())
    for i, from_id in enumerate(node_ids):
        from_node = graph.nodes[from_id]
        for to_id in node_ids[i + 1 :]:
            to_node = graph.nodes[to_id]
            distance = ((from_node.x - to_node.x) ** 2 + (from_node.y - to_node.y) ** 2) ** 0.5
            graph.add_edge(from_id, to_id, distance=distance, travel_time=distance, bidirectional=True)

    replay_meta = {
        "semantic_to_graph": {"DEPOT": depot_node_id, **{f"S_{sid}": nid for sid, nid in station_node_map.items()}, **{f"T_{tid}": nid for tid, nid in task_node_map.items()}},
        "depot_node_id": depot_node_id,
    }
    return graph, task_node_map, station_node_map, replay_meta


def _build_offline_replay_environment(instance: Any, max_simulation_time: int, offline_payload: dict[str, Any]) -> Environment:
    graph, task_node_map, station_node_map, replay_meta = _build_graph_from_offline_instance(instance)
    depot = Depot(id=0, node_id=int(replay_meta["depot_node_id"]))

    tasks = [
        Task(
            id=int(task.id),
            release_time=int(float(task.release)),
            deadline=int(float(task.deadline)),
            origin_node=task_node_map[int(task.id)],
            weight=float(task.demand),
        )
        for task in instance.tasks
    ]

    charge_rate = float(
        max((seg[1] for seg in getattr(instance, "piecewise_segments", []) if len(seg) >= 2), default=0.0)
        or getattr(instance, "linear_charge_rate", 3.0)
    )
    station_num_piles = max(1, int(getattr(instance, "max_station_visits_per_station", 1)))
    stations = [
        ChargingStation(
            id=int(station.id),
            node_id=station_node_map[int(station.id)],
            num_piles=station_num_piles,
            charge_rate=charge_rate,
        )
        for station in instance.stations
    ]

    speed_levels = tuple(float(level) for level in getattr(instance, "speed_levels", (1.0,)))
    vehicle_speed = speed_levels[len(speed_levels) // 2]
    energy_per_km = float(getattr(instance, "energy_base_per_km", 1.0))
    vehicles = [
        Vehicle(
            id=vehicle_id,
            vehicle_type="offline_milp_ev",
            current_node=depot.node_id,
            battery=float(instance.battery_capacity),
            battery_capacity=float(instance.battery_capacity),
            load_capacity=float(instance.vehicle_capacity),
            speed=vehicle_speed,
            energy_per_km=energy_per_km,
        )
        for vehicle_id in range(int(instance.num_vehicles))
    ]

    sim_config = SimulationConfig(
        end_time=min(max_simulation_time, int(float(instance.horizon))),
        enable_collaborative_tasks=False,
        auto_collaborative_dispatch=False,
    )

    env = Environment(
        graph=graph,
        depot=depot,
        vehicles=vehicles,
        tasks=tasks,
        stations=stations,
        config=sim_config,
        scheduler=None,
    )
    env.end_time = sim_config.end_time
    env.config.end_time = sim_config.end_time

    engine_root = Path(__file__).resolve().parents[3]
    offline_output_dir = engine_root / "policy" / "offline" / "output"
    plan_csv = _build_offline_plan_csv_from_result(offline_payload, offline_output_dir / "engine_plan.csv")

    release_map = {
        int(task.id): int(float(task.release))
        for task in instance.tasks
    }
    routes = offline_payload.get("result", {}).get("routes", {})
    env.scheduler = OfflineRouteScheduler.from_semantic_routes(
        routes=routes,
        task_node_map=task_node_map,
        station_node_map=station_node_map,
        release_map=release_map,
        depot_node_id=depot.node_id,
    )
    env.offline_plan_csv = str(plan_csv)
    env.offline_replay_meta = replay_meta
    return env


def _resolve_semantic_graph_node_id(
    semantic_node: str,
    semantic_to_graph: dict[str, int],
    depot_node_id: int,
) -> int | None:
    if semantic_node in {"DEPOT_START", "DEPOT_END", "DEPOT"}:
        return depot_node_id
    if semantic_node.startswith("T_"):
        task_id = semantic_node.split("_", 1)[1]
        return semantic_to_graph.get(f"T_{task_id}")
    if semantic_node.startswith("S_"):
        parts = semantic_node.split("_")
        if len(parts) >= 2:
            return semantic_to_graph.get(f"S_{parts[1]}")
    return semantic_to_graph.get(semantic_node)


def _build_offline_route_comparison(
    offline_payload: dict[str, Any],
    env: Environment,
) -> dict[str, Any]:
    replay_meta = getattr(env, "offline_replay_meta", {}) or {}
    semantic_to_graph = replay_meta.get("semantic_to_graph", {}) or {}
    depot_node_id = int(replay_meta.get("depot_node_id", env.depot.node_id))
    routes: dict[str, list[str]] = offline_payload.get("result", {}).get("routes", {})
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
            graph_node_id = _resolve_semantic_graph_node_id(
                semantic_node=semantic_node,
                semantic_to_graph=semantic_to_graph,
                depot_node_id=depot_node_id,
            )
            semantic_stop = {
                "vehicle_id": vehicle_id,
                "seq": seq,
                "semantic_node": semantic_node,
                "graph_node_id": graph_node_id,
            }
            semantic_stops.append(semantic_stop)
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

            if prev_graph_node_id == graph_node_id:
                segment_path = [graph_node_id]
            else:
                segment_path = pathfinder.shortest_path(prev_graph_node_id, graph_node_id)

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


def _write_offline_route_comparison_exports(
    summary_json_path: Path,
    route_csv_path: Path,
    offline_payload: dict[str, Any],
    env: Environment,
) -> dict[str, Any]:
    comparison = _build_offline_route_comparison(offline_payload=offline_payload, env=env)
    payload = dict(offline_payload)
    payload["replay_compare"] = comparison
    summary_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    import csv

    with route_csv_path.open("w", encoding="utf-8", newline="") as f:
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
        writer.writerows(comparison["flat_rows"])

    return comparison


def _map_strategy(strategy: str) -> str:
    # Engine currently has nearest/heaviest baseline schedulers.
    mapping = {
        "nearest_first": "nearest",
        "largest_first": "heaviest",
        "highest_reward": "nearest",
        "earliest_deadline": "nearest",
        "balanced": "nearest",
        "collaborative": "nearest",
    }
    return mapping.get(strategy, "nearest")


def _build_environment(
    scale_id: str,
    scheduler_name: str,
    enable_collaboration: bool,
    max_simulation_time: int,
) -> Environment:
    """Prefer real Panyu processed map; fallback to random map if unavailable."""
    engine_root = Path(__file__).resolve().parents[2]
    processed_dir = engine_root / "Map Resource" / "processed" / "panyu"

    if processed_dir.exists():
        scenario = preset_scenario(scale_id if scale_id in {"small", "medium", "large"} else "medium")
        scenario.horizon = max_simulation_time
        scenario.collaborative_task_ratio = 0.3 if enable_collaboration else 0.0

        map_bundle = load_real_map_from_processed(
            processed_dir=processed_dir,
            station_num_piles=2,
            station_charge_rate=6.0,
            bbox=PANYU_BBOX,
        )

        tasks = generate_real_tasks(
            scenario,
            candidate_node_ids=map_bundle.task_candidate_nodes,
            mode="uniform_nodes",
        )

        vehicles = [
            Vehicle(
                id=i,
                vehicle_type="panyu_ev",
                current_node=map_bundle.depot.node_id,
                battery=scenario.vehicle_battery_capacity,
                battery_capacity=scenario.vehicle_battery_capacity,
                load_capacity=scenario.vehicle_load_capacity,
                speed=scenario.vehicle_speed,
                energy_per_km=scenario.vehicle_energy_per_km,
            )
            for i in range(scenario.num_vehicles)
        ]

        scheduler = NearestTaskScheduler() if scheduler_name == "nearest" else HeaviestTaskScheduler()
        sim_config = SimulationConfig(
            end_time=max_simulation_time,
            enable_collaborative_tasks=enable_collaboration,
            auto_collaborative_dispatch=enable_collaboration,
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

    # Fallback for environments without processed data files.
    return build_random_environment(
        scale=scale_id,
        scheduler_name=scheduler_name,
        collaborative_task_ratio=0.3 if enable_collaboration else 0.0,
        enable_collaborative_tasks=enable_collaboration,
        auto_collaborative_dispatch=enable_collaboration,
    )


def _vehicle_status_for_ui(status: str) -> str:
    mapping = {
        "idle": "idle",
        "moving_to_task": "delivering",
        "moving_to_depot": "returning",
        "moving_to_charge": "waiting",
        "waiting_charge": "waiting",
        "charging": "charging",
    }
    return mapping.get(status, "idle")


def _task_status_for_ui(status: str) -> str:
    if status == "assigned":
        return "assigned"
    if status == "completed":
        return "completed"
    if status == "expired":
        return "expired"
    return "pending"


def _task_priority(weight: float, ttl_left: int) -> str:
    if ttl_left <= 10:
        return "urgent"
    if weight >= 24:
        return "high"
    if weight >= 12:
        return "medium"
    return "low"


def _build_graph_payload(env: Environment) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for node_id, node in env.graph.nodes.items():
        node_type = "intersection"
        if node.node_type == "depot":
            node_type = "warehouse"
        elif node.node_type == "station":
            node_type = "charging_station"
        nodes.append(
            {
                "id": str(node_id),
                "position": {"x": node.x, "y": node.y},
                "type": node_type,
                "name": f"N{node_id}",
            }
        )

    for from_id, edge_list in env.graph.adj.items():
        for idx, edge in enumerate(edge_list):
            edges.append(
                {
                    "id": f"{from_id}_{edge.to}_{idx}",
                    "from": str(from_id),
                    "to": str(edge.to),
                    "distance": edge.distance,
                    "trafficFactor": 1.0,
                }
            )

    return {"nodes": nodes, "edges": edges}


def _build_statistics(env: Environment) -> dict[str, Any]:
    total_tasks = len(env.tasks)
    completed = len(env.completed_task_ids)
    failed = len(env.expired_task_ids)
    pending = len(env.pending_task_ids)

    completed_durations = [
        (task.complete_time - task.release_time)
        for task in env.tasks.values()
        if task.complete_time is not None and task.status.value == "completed"
    ]
    avg_delivery = sum(completed_durations) / len(completed_durations) if completed_durations else 0.0

    busy = sum(1 for v in env.vehicles.values() if v.status.value != "idle")
    vehicle_util = (busy / max(1, len(env.vehicles))) * 100.0

    total_piles = sum(station.num_piles for station in env.stations.values())
    occupied = sum(station.occupied_piles for station in env.stations.values())
    station_util = (occupied / max(1, total_piles)) * 100.0

    on_time_denom = completed + failed
    on_time_rate = (completed / on_time_denom) * 100.0 if on_time_denom > 0 else 0.0

    collaborative_tasks = sum(
        1 for t in env.tasks.values() if t.collaborative and t.status.value == "completed"
    )

    total_distance = sum(v.total_distance for v in env.vehicles.values())

    return {
        "totalTasks": total_tasks,
        "completedTasks": completed,
        "failedTasks": failed,
        "pendingTasks": pending,
        "totalScore": round(env.total_score, 4),
        "totalDistance": round(total_distance, 4),
        "averageDeliveryTime": round(avg_delivery, 4),
        "vehicleUtilization": round(vehicle_util, 4),
        "chargingStationUtilization": round(station_util, 4),
        "onTimeRate": round(on_time_rate, 4),
        "collaborativeTasks": collaborative_tasks,
    }


def _build_events(env: Environment) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    task_events = env.logger.task_logs[-20:]
    for idx, event in enumerate(task_events):
        event_type = event.get("event_type", "")
        mapped_type = {
            "released": "task_created",
            "assigned": "task_assigned",
            "completed": "task_completed",
            "expired": "task_failed",
        }.get(event_type)
        if not mapped_type:
            continue
        events.append(
            {
                "id": f"task_{event.get('time', 0)}_{idx}",
                "time": event.get("time", 0),
                "type": mapped_type,
                "message": f"任务 {event.get('task_id')} {event_type}",
                "details": {
                    "taskId": str(event.get("task_id")),
                    "status": event.get("status"),
                },
            }
        )
    return events


def _build_ui_state(session: SimulationSession) -> dict[str, Any]:
    env = session.env
    graph_payload = _build_graph_payload(env)

    vehicles: list[dict[str, Any]] = []
    for vehicle in env.vehicles.values():
        node = env.graph.nodes[vehicle.current_node]
        v_x, v_y = node.x, node.y
        if vehicle.route_index < len(vehicle.route) - 1:
            u = vehicle.route[vehicle.route_index]
            v = vehicle.route[vehicle.route_index + 1]
            u_node = env.graph.nodes[u]
            v_node = env.graph.nodes[v]
            edge_dist = env.graph.edge_distance(u, v) or 1e-9
            progress = 1.0 - (vehicle.distance_to_next / edge_dist)
            progress = max(0.0, min(1.0, progress))
            v_x = u_node.x + (v_node.x - u_node.x) * progress
            v_y = u_node.y + (v_node.y - u_node.y) * progress

        assigned_tasks = []
        if vehicle.assigned_task is not None:
            assigned_tasks = [str(vehicle.assigned_task)]

        completed_tasks = sum(
            1
            for task in env.tasks.values()
            if task.status.value == "completed" and task.delivered_by_vehicle.get(vehicle.id, 0.0) > 0
        )

        vehicles.append(
            {
                "id": f"vehicle_{vehicle.id}",
                "name": f"车辆 {vehicle.id + 1}",
                "position": {"x": v_x, "y": v_y},
                "currentNodeId": str(vehicle.current_node),
                "targetNodeId": str(vehicle.target_node) if vehicle.target_node is not None else None,
                "battery": round(vehicle.battery, 4),
                "maxBattery": vehicle.battery_capacity,
                "batteryConsumption": vehicle.energy_per_km,
                "currentLoad": round(vehicle.task_load, 4),
                "maxLoad": vehicle.load_capacity,
                "status": _vehicle_status_for_ui(vehicle.status.value),
                "speed": vehicle.speed,
                "path": [str(node_id) for node_id in vehicle.route[vehicle.route_index + 1:]],
                "pathProgress": 0,
                "assignedTasks": assigned_tasks,
                "completedTasks": completed_tasks,
                "totalDistance": round(vehicle.total_distance, 4),
                "color": f"hsl({(vehicle.id * 47) % 360}, 70%, 55%)",
            }
        )

    tasks: list[dict[str, Any]] = []
    for task in env.tasks.values():
        if task.status.value == "future":
            continue
        node = env.graph.nodes.get(task.origin_node)
        if node is None:
            continue
        ttl_left = task.deadline - env.current_time
        assigned_vehicle_id = None
        if task.assigned_vehicle is not None:
            assigned_vehicle_id = f"vehicle_{task.assigned_vehicle}"
        elif task.assigned_vehicles:
            assigned_vehicle_id = f"vehicle_{next(iter(task.assigned_vehicles))}"

        tasks.append(
            {
                "id": str(task.id),
                "position": {"x": node.x, "y": node.y},
                "nodeId": str(task.origin_node),
                "weight": round(task.weight, 2),
                "createTime": task.release_time,
                "deadline": task.deadline,
                "status": _task_status_for_ui(task.status.value),
                "priority": _task_priority(task.weight, ttl_left),
                "reward": max(0.0, env.config.reward_base - task.weight * env.config.distance_penalty),
                "assignedVehicleId": assigned_vehicle_id,
                "completedTime": task.complete_time,
                "pickupNodeId": str(env.depot.node_id),
            }
        )

    charging_stations: list[dict[str, Any]] = []
    for station in env.stations.values():
        node = env.graph.nodes[station.node_id]
        charging_vehicles = [
            f"vehicle_{vehicle_id}"
            for vehicle_id in station.charging_slots
            if vehicle_id is not None
        ]
        queue = [f"vehicle_{vehicle_id}" for vehicle_id in station.queue]
        charging_stations.append(
            {
                "id": str(station.id),
                "nodeId": str(station.node_id),
                "position": {"x": node.x, "y": node.y},
                "name": f"充电站 {station.id}",
                "capacity": station.num_piles,
                "currentQueue": queue,
                "chargingVehicles": charging_vehicles,
                "chargingSpeed": station.charge_rate,
                "maxLoad": 100,
                "currentLoad": round((station.occupied_piles / max(1, station.num_piles)) * 100, 2),
            }
        )

    state = {
        "status": session.status,
        "currentTime": env.current_time,
        "vehicles": vehicles,
        "tasks": tasks,
        "chargingStations": charging_stations,
        "warehouses": [
            {
                "id": "warehouse_0",
                "nodeId": str(env.depot.node_id),
                "position": {
                    "x": env.graph.nodes[env.depot.node_id].x,
                    "y": env.graph.nodes[env.depot.node_id].y,
                },
                "name": "主仓库",
            }
        ],
        "graph": graph_payload,
        "statistics": _build_statistics(env),
        "config": session.config_payload,
        "eventLog": _build_events(env),
    }
    return state


async def _publish_state(session: SimulationSession) -> None:
    if not session.clients:
        return

    payload = {
        "type": "simulation_state",
        "data": _build_ui_state(session),
    }
    dead_clients: list[WebSocket] = []
    for client in list(session.clients):
        try:
            await client.send_json(payload)
        except Exception:
            dead_clients.append(client)

    for client in dead_clients:
        session.clients.discard(client)


async def _run_session_loop(session: SimulationSession) -> None:
    while not session.stop_event.is_set():
        async with session.lock:
            if session.status == "running":
                if session.env.current_time >= session.env.end_time:
                    session.status = "completed"
                else:
                    session.env.step()
                    if session.env.current_time >= session.env.end_time:
                        session.status = "completed"

            await _publish_state(session)

            if session.status == "completed":
                session.stop_event.set()

        tick = max(0.05, 0.25 / max(session.simulation_speed, 0.1))
        await asyncio.sleep(tick)


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/v1/solver/offline/start")
async def start_offline_solver(req: OfflineSolveRequest) -> dict[str, Any]:
    try:
        scale_id = req.scale.id if req.scale and req.scale.id else "small"
        module = _load_offline_milp_module()
        instance = _build_engine_constrained_offline_instance(
            module=module,
            scale_id=scale_id,
            max_simulation_time=req.maxSimulationTime,
        )
        engine = module.GodViewMILP(instance, solver=req.solver, charge_mode=req.chargeMode)
        result = engine.solve(time_limit_sec=req.timeLimit)

        engine_root = Path(__file__).resolve().parents[3]
        out_dir = engine_root / "policy" / "offline" / "output"
        json_path, summary_csv, route_csv = engine.save_result(result, out_dir=out_dir, prefix="god_view_milp")
        payload = json.loads(json_path.read_text(encoding="utf-8"))

        env = _build_offline_replay_environment(
            instance=instance,
            max_simulation_time=req.maxSimulationTime,
            offline_payload=payload,
        )
        comparison = _write_offline_route_comparison_exports(
            summary_json_path=json_path,
            route_csv_path=route_csv,
            offline_payload=payload,
            env=env,
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))

        simulation_id = str(uuid.uuid4())
        config_payload = {
            "scale": {
                "id": scale_id,
                "name": req.scale.name or scale_id,
                "description": (req.scale.description or "") + "（离线求解回放）",
                "vehicleCount": len(env.vehicles),
                "nodeCount": len(env.graph.nodes),
                "chargingStationCount": len(env.stations),
                "taskGenerationRate": 1,
                "mapSize": 100,
            },
            "strategy": "offline_optimal",
            "simulationSpeed": 1.0,
            "maxSimulationTime": req.maxSimulationTime,
            "enableCollaboration": False,
            "offlineSolve": {
                "solver": req.solver,
                "chargeMode": req.chargeMode,
                "timeLimit": req.timeLimit,
                "summaryJson": str(json_path),
                "summaryCsv": str(summary_csv),
                "routeCsv": str(route_csv),
                "compareVehicleCount": len(comparison.get("vehicle_routes", [])),
            },
        }

        session = SimulationSession(
            simulation_id=simulation_id,
            env=env,
            config_payload=config_payload,
            scheduler_name="offline_plan",
            simulation_speed=1.0,
            status="paused",
        )
        session.loop_task = asyncio.create_task(_run_session_loop(session))
        SESSIONS[simulation_id] = session

        return {
            "simulationId": simulation_id,
            "summaryJson": str(json_path),
            "summaryCsv": str(summary_csv),
            "routeCsv": str(route_csv),
            "objective": payload["result"]["objective"],
            "status": payload["result"]["status"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"offline solve failed: {exc}") from exc


@app.post("/api/v1/simulation/start")
async def start_simulation(req: SimulationStartRequest) -> dict[str, Any]:
    scale_id = req.scale.id if req.scale and req.scale.id else "medium"
    scheduler_name = _map_strategy(req.strategy)

    env = _build_environment(
        scale_id=scale_id,
        scheduler_name=scheduler_name,
        enable_collaboration=req.enableCollaboration,
        max_simulation_time=req.maxSimulationTime,
    )

    env.end_time = req.maxSimulationTime
    env.config.end_time = req.maxSimulationTime

    simulation_id = str(uuid.uuid4())
    config_payload = {
        "scale": {
            "id": scale_id,
            "name": req.scale.name or scale_id,
            "description": req.scale.description or "",
            "vehicleCount": len(env.vehicles),
            "nodeCount": len(env.graph.nodes),
            "chargingStationCount": len(env.stations),
            "taskGenerationRate": 1,
            "mapSize": 100,
        },
        "strategy": req.strategy,
        "simulationSpeed": req.simulationSpeed,
        "maxSimulationTime": req.maxSimulationTime,
        "enableCollaboration": req.enableCollaboration,
        "randomSeed": req.randomSeed,
    }

    session = SimulationSession(
        simulation_id=simulation_id,
        env=env,
        config_payload=config_payload,
        scheduler_name=scheduler_name,
        simulation_speed=max(0.1, req.simulationSpeed),
        status="running",
    )

    session.loop_task = asyncio.create_task(_run_session_loop(session))
    SESSIONS[simulation_id] = session

    return {"simulationId": simulation_id}


@app.get("/api/v1/simulation/{simulation_id}/state")
async def get_simulation_state(simulation_id: str) -> dict[str, Any]:
    session = SESSIONS.get(simulation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="simulation not found")

    async with session.lock:
        return _build_ui_state(session)


@app.post("/api/v1/simulation/{simulation_id}/pause")
async def pause_simulation(simulation_id: str) -> dict[str, Any]:
    session = SESSIONS.get(simulation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="simulation not found")

    async with session.lock:
        if session.status == "running":
            session.status = "paused"
    return {"paused": True}


@app.post("/api/v1/simulation/{simulation_id}/resume")
async def resume_simulation(simulation_id: str) -> dict[str, Any]:
    session = SESSIONS.get(simulation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="simulation not found")

    async with session.lock:
        if session.status == "paused":
            session.status = "running"
    return {"resumed": True}


@app.post("/api/v1/simulation/{simulation_id}/stop")
async def stop_simulation(simulation_id: str) -> dict[str, Any]:
    session = SESSIONS.get(simulation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="simulation not found")

    async with session.lock:
        session.status = "idle"
        session.stop_event.set()

    if session.loop_task is not None:
        await session.loop_task

    SESSIONS.pop(simulation_id, None)
    return {"stopped": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    subscribed_session: SimulationSession | None = None

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            data = message.get("data") or {}

            if msg_type == "subscribe":
                simulation_id = data.get("simulationId")
                session = SESSIONS.get(simulation_id)
                if session is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": "simulation not found", "simulationId": simulation_id},
                        }
                    )
                    continue

                if subscribed_session is not None:
                    subscribed_session.clients.discard(websocket)

                subscribed_session = session
                subscribed_session.clients.add(websocket)
                async with subscribed_session.lock:
                    await websocket.send_json(
                        {
                            "type": "simulation_state",
                            "data": _build_ui_state(subscribed_session),
                        }
                    )
            elif msg_type == "unsubscribe":
                if subscribed_session is not None:
                    subscribed_session.clients.discard(websocket)
                subscribed_session = None
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "data": {"time": time.time()}})
    except WebSocketDisconnect:
        if subscribed_session is not None:
            subscribed_session.clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("Framework.api.server:app", host="0.0.0.0", port=8000, reload=False)
