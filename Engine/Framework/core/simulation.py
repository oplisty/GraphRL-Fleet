from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping

from .config import SimulationConfig
from .entities import ChargingStation, Depot, Task, TaskStatus, Vehicle, VehicleStatus
from .graph import Graph
from .logger import SimulationLogger
from .pathfinder import PathFinder

if TYPE_CHECKING:
    from ..scheduler.base import SchedulerBase


class Environment:
    """B-group simulation kernel with stable APIs for schedulers and visualization."""

    def __init__(
        self,
        graph: Graph,
        depot: Depot,
        vehicles: Iterable[Vehicle] | dict[int, Vehicle],
        tasks: Iterable[Task] | dict[int, Task],
        stations: Iterable[ChargingStation] | dict[int, ChargingStation],
        config: SimulationConfig | None = None,
        scheduler: SchedulerBase | None = None,
        logger: SimulationLogger | None = None,
    ) -> None:
        self.graph = graph
        self.depot = depot
        self.vehicles = self._to_dict(vehicles)
        self.tasks = self._to_dict(tasks)
        self.stations = self._to_dict(stations)

        self.config = config or SimulationConfig()
        self.scheduler = scheduler
        self.logger = logger or SimulationLogger()

        self.pathfinder = PathFinder(graph)
        self.current_time = 0
        self.end_time = self.config.end_time
        self.total_score = 0.0

        self.station_by_node = {station.node_id: station.id for station in self.stations.values()}

        self.pending_task_ids: set[int] = set()
        self.assigned_task_ids: set[int] = set()
        self.completed_task_ids: set[int] = set()
        self.expired_task_ids: set[int] = set()

        self._future_task_ids = sorted(self.tasks, key=lambda task_id: self.tasks[task_id].release_time)
        self._future_index = 0

    def get_available_tasks(self, t: int | None = None) -> list[Task]:
        """API for A-group.

        - t == current_time: current pending tasks.
        - t > current_time: pending tasks + future tasks released by t (forecast view).
        - t < current_time: returns current pending tasks (history is not replayed here).
        """
        if t is None:
            t = self.current_time

        if t == self.current_time:
            return [self.tasks[task_id] for task_id in sorted(self.pending_task_ids)]

        result = [self.tasks[task_id] for task_id in sorted(self.pending_task_ids)]
        if t < self.current_time:
            return result

        idx = self._future_index
        while idx < len(self._future_task_ids):
            task_id = self._future_task_ids[idx]
            task = self.tasks[task_id]
            if task.release_time > t:
                break
            if task.status == TaskStatus.FUTURE:
                result.append(task)
            idx += 1
        return result

    def get_vehicle_state(self, vehicle_id: int) -> dict:
        """API for A-group: query state of one vehicle."""
        vehicle = self.vehicles[vehicle_id]
        return {
            "vehicle_id": vehicle.id,
            "current_node": vehicle.current_node,
            "battery": vehicle.battery,
            "battery_capacity": vehicle.battery_capacity,
            "load_capacity": vehicle.load_capacity,
            "speed": vehicle.speed,
            "status": vehicle.status.value,
            "assigned_task": vehicle.assigned_task,
            "task_load": vehicle.task_load,
            "target_station": vehicle.target_station,
            "total_distance": vehicle.total_distance,
            "total_score": vehicle.total_score,
        }

    def get_state_snapshot(self, raw: bool = False) -> dict:
        """API for A/C-group.

        - raw=False (default): returns serializable immutable-style view.
        - raw=True: returns internal objects for advanced local debugging only.
        """
        if not raw:
            return self.get_serializable_snapshot()

        return {
            "time": self.current_time,
            "vehicles": self.vehicles,
            "tasks": self.tasks,
            "stations": self.stations,
            "pending_task_ids": set(self.pending_task_ids),
            "assigned_task_ids": set(self.assigned_task_ids),
            "completed_task_ids": set(self.completed_task_ids),
            "expired_task_ids": set(self.expired_task_ids),
            "depot_node": self.depot.node_id,
            "total_score": self.total_score,
        }

    def get_serializable_snapshot(self) -> dict:
        return {
            "time": self.current_time,
            "depot_node": self.depot.node_id,
            "total_score": round(self.total_score, 4),
            "vehicles": {
                vehicle_id: self._vehicle_to_dict(vehicle)
                for vehicle_id, vehicle in sorted(self.vehicles.items())
            },
            "tasks": {
                task_id: self._task_to_dict(task)
                for task_id, task in sorted(self.tasks.items())
            },
            "stations": {
                station_id: self._station_to_dict(station)
                for station_id, station in sorted(self.stations.items())
            },
            "pending_task_ids": sorted(self.pending_task_ids),
            "assigned_task_ids": sorted(self.assigned_task_ids),
            "completed_task_ids": sorted(self.completed_task_ids),
            "expired_task_ids": sorted(self.expired_task_ids),
        }

    def export_state_snapshot_json(self, output_path: str | Path) -> None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(self.get_serializable_snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_idle_vehicle_ids(self) -> list[int]:
        return [v.id for v in self.vehicles.values() if v.is_idle()]

    def dispatch(
        self,
        task_or_vehicle_id: int,
        task_id_or_allocations: int | Mapping[int, float],
    ) -> bool:
        """Dispatch API (backward compatible).

        Supported signatures:
        - dispatch(vehicle_id, task_id): legacy single-vehicle API
        - dispatch(task_id, {vehicle_id: load, ...}): collaborative API
        """
        if isinstance(task_id_or_allocations, Mapping):
            return self.dispatch_collaborative(task_id=task_or_vehicle_id, vehicle_allocations=task_id_or_allocations)
        return self._dispatch_single(vehicle_id=task_or_vehicle_id, task_id=task_id_or_allocations)

    def dispatch_collaborative(self, task_id: int, vehicle_allocations: Mapping[int, float]) -> bool:
        if task_id not in self.tasks:
            return False
        if not vehicle_allocations:
            return False

        task = self.tasks[task_id]
        if task.status not in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
            return False
        if task.status == TaskStatus.ASSIGNED and not task.collaborative:
            return False
        if not self.config.enable_collaborative_tasks and len(vehicle_allocations) > 1:
            return False

        remaining = task.remaining_weight
        allocations: dict[int, float] = {}
        total_assigned = 0.0
        for vehicle_id, load in vehicle_allocations.items():
            if vehicle_id not in self.vehicles:
                return False
            if load <= 0:
                return False
            vehicle = self.vehicles[vehicle_id]
            if not vehicle.is_idle():
                return False
            assigned_load = min(float(load), vehicle.load_capacity)
            allocations[vehicle_id] = assigned_load
            total_assigned += assigned_load

        if total_assigned <= 0:
            return False
        if total_assigned > remaining + 1e-9:
            # Normalize to remaining demand.
            scale = remaining / total_assigned if total_assigned > 0 else 0.0
            allocations = {vid: load * scale for vid, load in allocations.items()}

        for vehicle_id, assigned_load in allocations.items():
            if assigned_load <= 1e-9:
                return False
            vehicle = self.vehicles[vehicle_id]
            if not self.pathfinder.can_finish_task_and_return(
                vehicle=vehicle,
                current_node=vehicle.current_node,
                task_node=task.origin_node,
                depot_node=self.depot.node_id,
                safety_margin=self.config.safety_energy_margin,
            ):
                self._redirect_to_charge(vehicle)
                return False

        for vehicle_id, assigned_load in allocations.items():
            if not self._dispatch_vehicle_to_task(
                vehicle_id=vehicle_id,
                task_id=task_id,
                assigned_load=assigned_load,
                collaborative=(len(allocations) > 1 or task.collaborative),
            ):
                return False
        return True

    def _dispatch_single(self, vehicle_id: int, task_id: int) -> bool:
        if vehicle_id not in self.vehicles or task_id not in self.tasks:
            return False
        task = self.tasks[task_id]
        if task.status != TaskStatus.PENDING:
            return False
        return self._dispatch_vehicle_to_task(
            vehicle_id=vehicle_id,
            task_id=task_id,
            assigned_load=task.weight,
            collaborative=False,
        )

    def _dispatch_vehicle_to_task(
        self,
        vehicle_id: int,
        task_id: int,
        assigned_load: float,
        collaborative: bool,
    ) -> bool:
        vehicle = self.vehicles[vehicle_id]
        task = self.tasks[task_id]

        if not vehicle.is_idle():
            return False
        if task.status not in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
            return False
        if task.status == TaskStatus.ASSIGNED and not task.collaborative and not collaborative:
            return False
        if assigned_load > vehicle.load_capacity + 1e-9:
            return False
        if assigned_load > task.remaining_weight + 1e-9:
            return False

        if not self.pathfinder.can_finish_task_and_return(
            vehicle=vehicle,
            current_node=vehicle.current_node,
            task_node=task.origin_node,
            depot_node=self.depot.node_id,
            safety_margin=self.config.safety_energy_margin,
        ):
            self._redirect_to_charge(vehicle)
            return False

        route: list[int] | None = None
        if vehicle.current_node != task.origin_node:
            route = self.pathfinder.shortest_path(vehicle.current_node, task.origin_node)
            if len(route) < 2:
                return False

        task.assign_vehicle(
            vehicle_id=vehicle.id,
            assigned_load=assigned_load,
            from_node=vehicle.current_node,
            time_now=self.current_time,
            vehicle_distance=vehicle.total_distance,
            collaborative=collaborative,
        )
        self.pending_task_ids.discard(task.id)
        self.assigned_task_ids.add(task.id)

        if vehicle.current_node == task.origin_node:
            vehicle.assigned_task = task.id
            vehicle.task_load = assigned_load
            vehicle.task_start_distance = vehicle.total_distance
            self._on_reach_task(vehicle)
            return True

        if route is None:
            return False
        vehicle.assign_task(task.id, route=route, target_node=task.origin_node, task_load=assigned_load)
        self.logger.log_task_event(self.current_time, task, "assigned")
        self.logger.log_vehicle_event(self.current_time, vehicle, "dispatch")
        return True

    def step(self, actions: list[tuple[int, int] | dict] | None = None) -> None:
        self._release_tasks()
        self._expire_tasks()

        self._auto_dispatch_collaborative_tasks()

        if actions is None and self.scheduler is not None:
            actions = self.scheduler.select_actions(self)

        if actions:
            for action in actions:
                if isinstance(action, tuple) and len(action) == 2:
                    vehicle_id, task_id = action
                    self.dispatch(vehicle_id, task_id)
                elif isinstance(action, dict):
                    task_id = action.get("task_id")
                    allocations = action.get("vehicle_allocations")
                    if isinstance(task_id, int) and isinstance(allocations, Mapping):
                        self.dispatch(task_id, allocations)

        self._update_vehicles()
        self._update_stations()

        self.logger.log_step_snapshot(
            self.current_time,
            vehicles=self.vehicles,
            tasks=self.tasks,
            stations=self.stations,
            total_score=self.total_score,
        )
        self.current_time += self.config.time_step

    def _auto_dispatch_collaborative_tasks(self) -> None:
        if not self.config.enable_collaborative_tasks:
            return
        if not self.config.auto_collaborative_dispatch:
            return
        if not self.pending_task_ids:
            return

        max_single_capacity = max((v.load_capacity for v in self.vehicles.values()), default=0.0)
        for task_id in sorted(self.pending_task_ids):
            task = self.tasks[task_id]
            if task.status != TaskStatus.PENDING:
                continue
            if task.weight <= max_single_capacity + 1e-9:
                continue

            allocations = self._build_collaborative_allocations(task)
            if not allocations:
                continue
            self.dispatch(task.id, allocations)

    def _build_collaborative_allocations(self, task: Task) -> dict[int, float]:
        candidates: list[tuple[float, Vehicle]] = []
        remaining = task.remaining_weight
        if remaining <= 1e-9:
            return {}

        for vehicle in self.vehicles.values():
            if not vehicle.is_idle():
                continue
            if not self.pathfinder.can_finish_task_and_return(
                vehicle=vehicle,
                current_node=vehicle.current_node,
                task_node=task.origin_node,
                depot_node=self.depot.node_id,
                safety_margin=self.config.safety_energy_margin,
            ):
                continue
            distance = self.pathfinder.shortest_distance(vehicle.current_node, task.origin_node)
            if math.isinf(distance):
                continue
            candidates.append((distance, vehicle))

        if not candidates:
            return {}

        # Prefer closer vehicles; if same distance, prefer higher load capacity.
        candidates.sort(key=lambda item: (item[0], -item[1].load_capacity))

        allocations: dict[int, float] = {}
        for _, vehicle in candidates:
            if remaining <= 1e-9:
                break
            load = min(vehicle.load_capacity, remaining)
            if load <= 1e-9:
                continue
            allocations[vehicle.id] = load
            remaining -= load

        if remaining > 1e-9:
            return {}
        return allocations

    def run(self, end_time: int | None = None, scheduler: SchedulerBase | None = None) -> dict:
        if scheduler is not None:
            self.scheduler = scheduler

        target_time = end_time if end_time is not None else self.end_time
        while self.current_time < target_time:
            self.step()

        summary = {
            "time": self.current_time,
            "total_score": round(self.total_score, 4),
            "completed": len(self.completed_task_ids),
            "expired": len(self.expired_task_ids),
            "pending": len(self.pending_task_ids),
            "assigned": len(self.assigned_task_ids),
        }
        summary.update(self._build_metrics_summary())
        return summary

    def export_logs(self, output_dir: str) -> None:
        self.logger.export_json(output_dir)
        self.logger.export_csv(output_dir)

    def _release_tasks(self) -> None:
        while self._future_index < len(self._future_task_ids):
            task_id = self._future_task_ids[self._future_index]
            task = self.tasks[task_id]
            if task.release_time > self.current_time:
                break

            task.mark_released()
            self.pending_task_ids.add(task_id)
            self.logger.log_task_event(self.current_time, task, "released")
            self._future_index += 1

    def _expire_tasks(self) -> None:
        for task_id in list(self.pending_task_ids):
            task = self.tasks[task_id]
            if task.deadline < self.current_time:
                self._expire_task(task)

        for task_id in list(self.assigned_task_ids):
            task = self.tasks[task_id]
            if task.deadline < self.current_time:
                self._expire_task(task)

    def _expire_task(self, task: Task) -> None:
        was_assigned = task.status == TaskStatus.ASSIGNED
        progress_ratio = 0.0
        if task.weight > 1e-9:
            progress_ratio = min(1.0, max(0.0, task.delivered_weight / task.weight))

        task.mark_expired(self.current_time)
        self.pending_task_ids.discard(task.id)
        self.assigned_task_ids.discard(task.id)
        self.expired_task_ids.add(task.id)

        if (
            self.config.enable_collaborative_tasks
            and self.config.collaborative_partial_credit
            and progress_ratio > 0
        ):
            partial_reward = (
                self.config.reward_base * progress_ratio * self.config.collaborative_partial_credit_ratio
            )
            self.total_score += partial_reward

        self.total_score -= self.config.overdue_penalty

        if was_assigned:
            for vehicle in self.vehicles.values():
                if vehicle.assigned_task != task.id:
                    continue
                vehicle.clear_task_assignment()
                vehicle.clear_route()
                self._recover_vehicle_after_task_expired(vehicle)

        task.assigned_vehicles.clear()
        self.logger.log_task_event(self.current_time, task, "expired")

    def _update_vehicles(self) -> None:
        for vehicle in self.vehicles.values():
            if vehicle.status == VehicleStatus.MOVING_TO_TASK and vehicle.assigned_task is not None:
                task = self.tasks.get(vehicle.assigned_task)
                if task is None or task.status != TaskStatus.ASSIGNED:
                    vehicle.clear_task_assignment()
                    vehicle.clear_route()
                    self._recover_vehicle_after_task_expired(vehicle)
                    continue

            if vehicle.status in (
                VehicleStatus.MOVING_TO_TASK,
                VehicleStatus.MOVING_TO_CHARGE,
                VehicleStatus.MOVING_TO_DEPOT,
            ):
                arrived = self._advance_vehicle(vehicle)
                if arrived and vehicle.status == VehicleStatus.MOVING_TO_TASK:
                    self._on_reach_task(vehicle)
                elif arrived and vehicle.status == VehicleStatus.MOVING_TO_CHARGE:
                    self._on_reach_station(vehicle)
                elif arrived and vehicle.status == VehicleStatus.MOVING_TO_DEPOT:
                    self._on_reach_depot(vehicle)
            elif vehicle.status == VehicleStatus.IDLE and self._should_charge(vehicle):
                self._redirect_to_charge(vehicle)

    def _update_stations(self) -> None:
        for station in self.stations.values():
            for i, vehicle_id in enumerate(station.charging_slots):
                if vehicle_id is None:
                    continue

                vehicle = self.vehicles[vehicle_id]
                vehicle.battery = min(
                    vehicle.battery_capacity,
                    vehicle.battery + station.charge_rate * self.config.time_step,
                )

                if vehicle.battery >= vehicle.battery_capacity * self.config.charge_to_ratio:
                    station.charging_slots[i] = None
                    vehicle.finish_charging()
                    self.logger.log_vehicle_event(self.current_time, vehicle, "charge_finish")
                    self._resume_vehicle_after_charging(vehicle)

            for i, slot in enumerate(station.charging_slots):
                if slot is not None:
                    continue
                if not station.queue:
                    break

                next_vehicle_id = station.queue.popleft()
                station.charging_slots[i] = next_vehicle_id
                vehicle = self.vehicles[next_vehicle_id]
                vehicle.start_charging(station.id)
                self.logger.log_vehicle_event(self.current_time, vehicle, "charge_start")

    def _on_reach_task(self, vehicle: Vehicle) -> None:
        if vehicle.assigned_task is None:
            vehicle.status = VehicleStatus.IDLE
            vehicle.clear_route()
            return

        task = self.tasks[vehicle.assigned_task]
        if task.status != TaskStatus.ASSIGNED:
            vehicle.clear_task_assignment()
            vehicle.status = VehicleStatus.IDLE
            vehicle.clear_route()
            return

        assigned_load = vehicle.task_load if vehicle.task_load > 0 else min(task.remaining_weight, task.weight)
        start_distance = vehicle.task_start_distance
        if start_distance is None:
            start_distance = vehicle.total_distance
        trip_distance = max(0.0, vehicle.total_distance - start_distance)
        task.record_delivery(
            vehicle_id=vehicle.id,
            delivered_load=min(assigned_load, task.remaining_weight),
            trip_distance=trip_distance,
            time_now=self.current_time,
        )

        vehicle.clear_task_assignment()
        vehicle.clear_route()

        if task.remaining_weight <= 1e-9:
            self._finalize_task_completion(task)
        elif not task.assigned_vehicles:
            task.status = TaskStatus.PENDING
            self.assigned_task_ids.discard(task.id)
            self.pending_task_ids.add(task.id)
            self.logger.log_task_event(self.current_time, task, "partial_delivered")
        else:
            self.logger.log_task_event(self.current_time, task, "partial_delivered")

        self.logger.log_vehicle_event(self.current_time, vehicle, "task_finish")

        # Keep simulation semantics consistent with dispatch feasibility:
        # if dispatch checks "task + return", the execution should really return.
        if self.config.auto_return_to_depot and vehicle.current_node != self.depot.node_id:
            if self.pathfinder.can_reach(
                vehicle,
                start=vehicle.current_node,
                end=self.depot.node_id,
                safety_margin=self.config.safety_energy_margin,
            ):
                self._route_vehicle_to_depot(vehicle)
            else:
                self._redirect_to_charge(
                    vehicle,
                    resume_status=VehicleStatus.MOVING_TO_DEPOT,
                    resume_target_node=self.depot.node_id,
                )
            return

        vehicle.status = VehicleStatus.IDLE
        if self._should_charge(vehicle):
            self._redirect_to_charge(vehicle)

    def _finalize_task_completion(self, task: Task) -> None:
        task.mark_completed(self.current_time)
        task.assigned_vehicles.clear()
        self.pending_task_ids.discard(task.id)
        self.assigned_task_ids.discard(task.id)
        self.completed_task_ids.add(task.id)

        task_score = self._compute_task_score(task)
        total_delivered = sum(task.delivered_by_vehicle.values())
        if total_delivered <= 1e-9:
            self.total_score += task_score
        else:
            for vehicle_id, delivered in task.delivered_by_vehicle.items():
                vehicle = self.vehicles.get(vehicle_id)
                if vehicle is None:
                    continue
                share = delivered / total_delivered
                vehicle.total_score += task_score * share
            self.total_score += task_score

        self.logger.log_task_event(self.current_time, task, "completed")

    def _compute_task_score(self, task: Task) -> float:
        travel_dist = task.service_distance
        wait_time = max(0, self.current_time - task.release_time)
        overdue = max(0, self.current_time - task.deadline)
        score = self.config.reward_base - travel_dist * self.config.distance_penalty
        score -= wait_time * self.config.wait_time_penalty
        if overdue > 0:
            score -= self.config.overdue_penalty
        return score

    def _on_reach_station(self, vehicle: Vehicle) -> None:
        station_id = vehicle.target_station
        if station_id is None:
            station_id = self.station_by_node.get(vehicle.current_node)

        if station_id is None:
            vehicle.status = VehicleStatus.IDLE
            vehicle.clear_route()
            return

        station = self.stations[station_id]
        station.enqueue(vehicle.id)
        vehicle.start_waiting_charge(station.id)
        self.logger.log_vehicle_event(self.current_time, vehicle, "queue_charge")

    def _on_reach_depot(self, vehicle: Vehicle) -> None:
        vehicle.clear_route()
        vehicle.status = VehicleStatus.IDLE
        self.logger.log_vehicle_event(self.current_time, vehicle, "reach_depot")

        if self._should_charge(vehicle):
            self._redirect_to_charge(vehicle)

    def _advance_vehicle(self, vehicle: Vehicle) -> bool:
        if not vehicle.route:
            return False
        if len(vehicle.route) == 1:
            return True

        move_budget = vehicle.speed * self.config.time_step

        while move_budget > 1e-9 and vehicle.route_index < len(vehicle.route) - 1:
            if vehicle.distance_to_next <= 1e-9:
                u = vehicle.route[vehicle.route_index]
                v = vehicle.route[vehicle.route_index + 1]
                edge_dist = self.graph.edge_distance(u, v)
                if edge_dist is None:
                    raise ValueError(f"Invalid route segment {u} -> {v}")
                vehicle.distance_to_next = edge_dist

            step_dist = min(move_budget, vehicle.distance_to_next)

            if vehicle.energy_per_km > 0:
                max_move_by_energy = vehicle.battery / vehicle.energy_per_km
                step_dist = min(step_dist, max_move_by_energy)

            if step_dist <= 1e-9:
                break

            energy_cost = step_dist * vehicle.energy_per_km
            vehicle.battery = max(0.0, vehicle.battery - energy_cost)
            vehicle.total_distance += step_dist
            move_budget -= step_dist
            vehicle.distance_to_next -= step_dist

            if vehicle.distance_to_next <= 1e-9:
                vehicle.route_index += 1
                vehicle.current_node = vehicle.route[vehicle.route_index]
                vehicle.distance_to_next = 0.0

        reached = vehicle.route_index >= len(vehicle.route) - 1 and vehicle.distance_to_next <= 1e-9
        return reached

    def _should_charge(self, vehicle: Vehicle) -> bool:
        if vehicle.battery <= vehicle.battery_capacity * self.config.low_battery_ratio:
            return True
        return not self.pathfinder.can_reach(
            vehicle,
            start=vehicle.current_node,
            end=self.depot.node_id,
            safety_margin=self.config.safety_energy_margin,
        )

    def _redirect_to_charge(
        self,
        vehicle: Vehicle,
        resume_status: VehicleStatus | None = None,
        resume_target_node: int | None = None,
    ) -> bool:
        if resume_status is not None and resume_target_node is not None:
            vehicle.set_resume_intent(resume_status, resume_target_node)
        elif resume_status is None and resume_target_node is None:
            vehicle.clear_resume_intent()

        station_id = self._choose_reachable_station(vehicle)
        if station_id is None:
            self.logger.log_event(
                self.current_time,
                "charge_unreachable",
                {"vehicle_id": vehicle.id, "node": vehicle.current_node},
            )
            return False

        station = self.stations[station_id]
        station_node = station.node_id

        if vehicle.current_node == station_node:
            station.enqueue(vehicle.id)
            vehicle.start_waiting_charge(station_id)
            self.logger.log_vehicle_event(self.current_time, vehicle, "queue_charge")
            return True

        route = self.pathfinder.shortest_path(vehicle.current_node, station_node)
        if len(route) < 2:
            return False

        vehicle.clear_task_assignment()
        vehicle.plan_route(route=route, target_node=station_node, status=VehicleStatus.MOVING_TO_CHARGE)
        vehicle.target_station = station_id
        self.logger.log_vehicle_event(self.current_time, vehicle, "move_to_charge")
        return True

    def _choose_reachable_station(self, vehicle: Vehicle) -> int | None:
        best_station_id: int | None = None
        best_cost = math.inf
        best_distance = math.inf

        for station in self.stations.values():
            distance = self.pathfinder.shortest_distance(vehicle.current_node, station.node_id)
            if math.isinf(distance):
                continue
            needed = distance * vehicle.energy_per_km + self.config.safety_energy_margin
            if vehicle.battery < needed:
                continue

            load_cost = (
                self.config.charge_queue_weight * station.queue_length
                + self.config.charge_occupied_weight * station.occupied_piles
            )
            total_cost = distance + load_cost
            if total_cost < best_cost or (total_cost == best_cost and distance < best_distance):
                best_cost = total_cost
                best_distance = distance
                best_station_id = station.id

        return best_station_id

    def _route_vehicle_to_depot(self, vehicle: Vehicle) -> bool:
        if vehicle.current_node == self.depot.node_id:
            vehicle.status = VehicleStatus.IDLE
            vehicle.clear_resume_intent()
            return True

        route = self.pathfinder.shortest_path(vehicle.current_node, self.depot.node_id)
        if len(route) < 2:
            vehicle.status = VehicleStatus.IDLE
            return False

        vehicle.plan_route(route=route, target_node=self.depot.node_id, status=VehicleStatus.MOVING_TO_DEPOT)
        vehicle.clear_resume_intent()
        self.logger.log_vehicle_event(self.current_time, vehicle, "move_to_depot")
        return True

    def _resume_vehicle_after_charging(self, vehicle: Vehicle) -> None:
        if (
            vehicle.resume_status == VehicleStatus.MOVING_TO_DEPOT
            and vehicle.resume_target_node == self.depot.node_id
        ):
            if self.pathfinder.can_reach(
                vehicle,
                start=vehicle.current_node,
                end=self.depot.node_id,
                safety_margin=self.config.safety_energy_margin,
            ):
                self._route_vehicle_to_depot(vehicle)
                self.logger.log_vehicle_event(self.current_time, vehicle, "resume_to_depot")
                return

        vehicle.clear_resume_intent()
        if self._should_charge(vehicle):
            self._redirect_to_charge(vehicle)

    def _recover_vehicle_after_task_expired(self, vehicle: Vehicle) -> None:
        if self.config.auto_return_to_depot and vehicle.current_node != self.depot.node_id:
            if self.pathfinder.can_reach(
                vehicle,
                start=vehicle.current_node,
                end=self.depot.node_id,
                safety_margin=self.config.safety_energy_margin,
            ):
                self._route_vehicle_to_depot(vehicle)
            else:
                self._redirect_to_charge(
                    vehicle,
                    resume_status=VehicleStatus.MOVING_TO_DEPOT,
                    resume_target_node=self.depot.node_id,
                )
            return

        vehicle.status = VehicleStatus.IDLE
        if self._should_charge(vehicle):
            self._redirect_to_charge(vehicle)

    @staticmethod
    def _to_dict(items: Iterable | dict[int, object]) -> dict[int, object]:
        if isinstance(items, dict):
            return items
        return {item.id: item for item in items}

    @staticmethod
    def _vehicle_to_dict(vehicle: Vehicle) -> dict:
        return {
            "id": vehicle.id,
            "vehicle_type": vehicle.vehicle_type,
            "current_node": vehicle.current_node,
            "battery": round(vehicle.battery, 4),
            "battery_capacity": vehicle.battery_capacity,
            "load_capacity": vehicle.load_capacity,
            "speed": vehicle.speed,
            "energy_per_km": vehicle.energy_per_km,
            "status": vehicle.status.value,
            "assigned_task": vehicle.assigned_task,
            "task_load": round(vehicle.task_load, 4),
            "task_start_distance": vehicle.task_start_distance,
            "target_node": vehicle.target_node,
            "target_station": vehicle.target_station,
            "resume_status": vehicle.resume_status.value if vehicle.resume_status else None,
            "resume_target_node": vehicle.resume_target_node,
            "total_distance": round(vehicle.total_distance, 4),
            "total_score": round(vehicle.total_score, 4),
            "route": list(vehicle.route),
            "route_index": vehicle.route_index,
            "distance_to_next": round(vehicle.distance_to_next, 4),
        }

    @staticmethod
    def _task_to_dict(task: Task) -> dict:
        return {
            "id": task.id,
            "status": task.status.value,
            "collaborative": task.collaborative,
            "release_time": task.release_time,
            "deadline": task.deadline,
            "origin_node": task.origin_node,
            "weight": task.weight,
            "delivered_weight": round(task.delivered_weight, 4),
            "remaining_weight": round(task.remaining_weight, 4),
            "assigned_vehicles": dict(task.assigned_vehicles),
            "delivered_by_vehicle": dict(task.delivered_by_vehicle),
            "assigned_vehicle": task.assigned_vehicle,
            "assigned_from_node": task.assigned_from_node,
            "assigned_time": task.assigned_time,
            "assigned_vehicle_distance": task.assigned_vehicle_distance,
            "service_distance": round(task.service_distance, 4),
            "service_duration": task.service_duration,
            "complete_time": task.complete_time,
        }

    @staticmethod
    def _station_to_dict(station: ChargingStation) -> dict:
        return {
            "id": station.id,
            "node_id": station.node_id,
            "num_piles": station.num_piles,
            "charge_rate": station.charge_rate,
            "queue_length": station.queue_length,
            "occupied_piles": station.occupied_piles,
            "queue": list(station.queue),
            "charging_slots": list(station.charging_slots),
        }

    def _build_metrics_summary(self) -> dict:
        total_distance = sum(vehicle.total_distance for vehicle in self.vehicles.values())

        step_vehicle_logs = [
            log for log in self.logger.vehicle_logs if log.get("event_type") == "step"
        ]
        if step_vehicle_logs:
            busy_count = sum(1 for log in step_vehicle_logs if log.get("status") != VehicleStatus.IDLE.value)
            avg_vehicle_utilization = busy_count / len(step_vehicle_logs)
        else:
            avg_vehicle_utilization = 0.0

        if self.logger.station_logs:
            avg_station_queue_length = sum(
                log.get("queue_length", 0) for log in self.logger.station_logs
            ) / len(self.logger.station_logs)
        else:
            avg_station_queue_length = 0.0

        completion_durations = [
            (task.complete_time - task.release_time)
            for task in self.tasks.values()
            if task.status == TaskStatus.COMPLETED and task.complete_time is not None
        ]
        if completion_durations:
            avg_task_completion_time = sum(completion_durations) / len(completion_durations)
        else:
            avg_task_completion_time = 0.0

        charge_waiting_times = self._collect_charge_waiting_times()
        if charge_waiting_times:
            avg_charge_waiting_time = sum(charge_waiting_times) / len(charge_waiting_times)
        else:
            avg_charge_waiting_time = 0.0

        charge_sessions = sum(
            1 for log in self.logger.vehicle_logs if log.get("event_type") == "charge_start"
        )

        return {
            "run_steps": len(self.logger.step_logs),
            "total_distance": round(total_distance, 4),
            "avg_vehicle_utilization": round(avg_vehicle_utilization, 4),
            "avg_station_queue_length": round(avg_station_queue_length, 4),
            "avg_task_completion_time": round(avg_task_completion_time, 4),
            "avg_charge_waiting_time": round(avg_charge_waiting_time, 4),
            "charge_sessions": charge_sessions,
        }

    def _collect_charge_waiting_times(self) -> list[float]:
        waiting_times: list[float] = []
        queue_starts: dict[int, deque[int]] = defaultdict(deque)

        ordered_logs = sorted(
            self.logger.vehicle_logs,
            key=lambda log: (log.get("time", 0), log.get("vehicle_id", -1)),
        )
        for log in ordered_logs:
            vehicle_id = log.get("vehicle_id")
            if vehicle_id is None:
                continue
            event_type = log.get("event_type")
            if event_type == "queue_charge":
                queue_starts[vehicle_id].append(log.get("time", 0))
            elif event_type == "charge_start" and queue_starts[vehicle_id]:
                wait = log.get("time", 0) - queue_starts[vehicle_id].popleft()
                waiting_times.append(max(0.0, float(wait)))

        return waiting_times
