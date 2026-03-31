from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ..core import VehicleStatus
from .base import SchedulerBase

if TYPE_CHECKING:
    from ..core.simulation import Environment


@dataclass(slots=True)
class PlanItem:
    task_id: int
    vehicle_id: int
    release_time: int


@dataclass(slots=True)
class RoutePlanStop:
    vehicle_id: int
    seq: int
    semantic_node: str
    kind: Literal["task", "station", "depot_start", "depot_end"]
    graph_node_id: int
    release_time: int = 0
    task_id: int | None = None
    station_id: int | None = None


class OfflinePlanScheduler(SchedulerBase):
    """
    将离线求得的“任务->车辆”分配计划接入在线仿真引擎。

    说明：
    - 这个调度器不负责重新优化，仅按给定计划在任务释放后触发派单。
    - 适用于把上帝视角 MILP 结果回放到 Engine 中，便于做对比实验。
    """

    def __init__(self, plan_items: list[PlanItem]):
        self.plan_items = sorted(plan_items, key=lambda x: (x.release_time, x.task_id))
        self._dispatched_task_ids: set[int] = set()

    @classmethod
    def from_csv(cls, csv_path: str | Path) -> "OfflinePlanScheduler":
        import csv

        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"offline plan csv not found: {path}")

        items: list[PlanItem] = []
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                task_id = row.get("task_id")
                vehicle_id = row.get("vehicle_id")
                release_time = row.get("release_time", "0")
                if task_id is None or vehicle_id is None:
                    continue
                items.append(
                    PlanItem(
                        task_id=int(task_id),
                        vehicle_id=int(vehicle_id),
                        release_time=int(float(release_time)),
                    )
                )

        return cls(items)

    def select_actions(self, env: Environment) -> list[tuple[int, int] | dict]:
        actions: list[tuple[int, int] | dict] = []

        idle_set = set(env.get_idle_vehicle_ids())
        pending_set = set(env.pending_task_ids)

        for item in self.plan_items:
            if item.task_id in self._dispatched_task_ids:
                continue
            if env.current_time < item.release_time:
                continue
            if item.task_id not in pending_set:
                continue
            if item.vehicle_id not in idle_set:
                continue

            actions.append((item.vehicle_id, item.task_id))
            self._dispatched_task_ids.add(item.task_id)
            idle_set.remove(item.vehicle_id)

        return actions


class OfflineRouteScheduler(SchedulerBase):
    """按 MILP 语义路径顺序做强回放。

    特点：
    - 不仅回放“任务归属”，还回放车辆访问 task/station/depot 的顺序；
    - 具体道路节点路径仍由 Engine 的 `PathFinder.shortest_path` 生成，
      因而实际行驶路径严格服从 Engine 道路规则；
    - 适合把 MILP 的语义路径（DEPOT/T_i/S_j_k）映射为 Engine 中的逐段运行。
    """

    def __init__(self, route_plans: dict[int, list[RoutePlanStop]]):
        self.route_plans = {
            vehicle_id: sorted(stops, key=lambda item: item.seq)
            for vehicle_id, stops in route_plans.items()
        }
        self.next_index: dict[int, int] = {vehicle_id: 0 for vehicle_id in route_plans}

    @classmethod
    def from_semantic_routes(
        cls,
        routes: dict[int, list[str]] | dict[str, list[str]],
        task_node_map: dict[int, int],
        station_node_map: dict[int, int],
        release_map: dict[int, int],
        depot_node_id: int,
    ) -> "OfflineRouteScheduler":
        route_plans: dict[int, list[RoutePlanStop]] = {}

        for vehicle_key, semantic_route in routes.items():
            vehicle_id = int(vehicle_key)
            stops: list[RoutePlanStop] = []
            for seq, semantic_node in enumerate(semantic_route):
                if semantic_node == "DEPOT_START":
                    stops.append(
                        RoutePlanStop(
                            vehicle_id=vehicle_id,
                            seq=seq,
                            semantic_node=semantic_node,
                            kind="depot_start",
                            graph_node_id=depot_node_id,
                        )
                    )
                    continue

                if semantic_node == "DEPOT_END":
                    stops.append(
                        RoutePlanStop(
                            vehicle_id=vehicle_id,
                            seq=seq,
                            semantic_node=semantic_node,
                            kind="depot_end",
                            graph_node_id=depot_node_id,
                        )
                    )
                    continue

                if semantic_node.startswith("T_"):
                    task_id = int(semantic_node.split("_", 1)[1])
                    stops.append(
                        RoutePlanStop(
                            vehicle_id=vehicle_id,
                            seq=seq,
                            semantic_node=semantic_node,
                            kind="task",
                            graph_node_id=task_node_map[task_id],
                            release_time=release_map.get(task_id, 0),
                            task_id=task_id,
                        )
                    )
                    continue

                if semantic_node.startswith("S_"):
                    station_id = int(semantic_node.split("_")[1])
                    stops.append(
                        RoutePlanStop(
                            vehicle_id=vehicle_id,
                            seq=seq,
                            semantic_node=semantic_node,
                            kind="station",
                            graph_node_id=station_node_map[station_id],
                            station_id=station_id,
                        )
                    )
                    continue

            route_plans[vehicle_id] = stops

        return cls(route_plans)

    def select_actions(self, env: Environment) -> list[tuple[int, int] | dict]:
        actions: list[tuple[int, int] | dict] = []

        for vehicle_id, stops in self.route_plans.items():
            vehicle = env.vehicles.get(vehicle_id)
            if vehicle is None:
                continue

            if not vehicle.is_idle():
                continue

            pointer = self.next_index.get(vehicle_id, 0)
            while pointer < len(stops) and stops[pointer].kind == "depot_start":
                pointer += 1

            if pointer >= len(stops):
                self.next_index[vehicle_id] = pointer
                continue

            stop = stops[pointer]

            if stop.kind == "task":
                task_id = stop.task_id
                if task_id is None:
                    self.next_index[vehicle_id] = pointer + 1
                    continue

                task = env.tasks.get(task_id)
                if task is None or task_id in env.completed_task_ids or task_id in env.expired_task_ids:
                    self.next_index[vehicle_id] = pointer + 1
                    continue

                if env.current_time < stop.release_time:
                    continue

                if task_id not in env.pending_task_ids:
                    continue

                if env.dispatch(vehicle_id, task_id):
                    self.next_index[vehicle_id] = pointer + 1
                continue

            if stop.kind == "station":
                station_id = stop.station_id
                if station_id is None or station_id not in env.stations:
                    self.next_index[vehicle_id] = pointer + 1
                    continue

                station = env.stations[station_id]
                if vehicle.current_node == stop.graph_node_id:
                    station.enqueue(vehicle.id)
                    vehicle.start_waiting_charge(station_id)
                    self.next_index[vehicle_id] = pointer + 1
                    break

                route = env.pathfinder.shortest_path(vehicle.current_node, stop.graph_node_id)
                if len(route) < 2:
                    break

                vehicle.clear_task_assignment()
                vehicle.plan_route(route=route, target_node=stop.graph_node_id, status=VehicleStatus.MOVING_TO_CHARGE)
                vehicle.target_station = station_id
                self.next_index[vehicle_id] = pointer + 1
                break

            if stop.kind == "depot_end":
                if vehicle.current_node == stop.graph_node_id:
                    self.next_index[vehicle_id] = pointer + 1
                    break

                route = env.pathfinder.shortest_path(vehicle.current_node, stop.graph_node_id)
                if len(route) < 2:
                    break

                vehicle.plan_route(route=route, target_node=stop.graph_node_id, status=VehicleStatus.MOVING_TO_DEPOT)
                self.next_index[vehicle_id] = pointer + 1
                break

            self.next_index[vehicle_id] = pointer + 1

        return actions
