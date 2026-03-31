from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from Framework.core import Environment, SimulationConfig, Vehicle, preset_scenario
from Framework.examples.run_baseline import build_environment as build_random_environment
from Framework.generator import generate_real_tasks, load_real_map_from_processed
from Framework.scheduler import HeaviestTaskScheduler, NearestTaskScheduler


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
