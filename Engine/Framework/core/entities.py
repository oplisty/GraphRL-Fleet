from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    FUTURE = "future"
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    EXPIRED = "expired"


class VehicleStatus(str, Enum):
    IDLE = "idle"
    MOVING_TO_TASK = "moving_to_task"
    MOVING_TO_DEPOT = "moving_to_depot"
    MOVING_TO_CHARGE = "moving_to_charge"
    WAITING_CHARGE = "waiting_charge"
    CHARGING = "charging"


@dataclass(slots=True)
class Task:
    id: int
    release_time: int
    deadline: int
    origin_node: int
    weight: float
    status: TaskStatus = TaskStatus.FUTURE
    collaborative: bool = False
    delivered_weight: float = 0.0
    assigned_vehicles: dict[int, float] = field(default_factory=dict)
    delivered_by_vehicle: dict[int, float] = field(default_factory=dict)
    assigned_vehicle: int | None = None
    assigned_from_node: int | None = None
    assigned_time: int | None = None
    assigned_vehicle_distance: float | None = None
    service_distance: float = 0.0
    service_duration: int = 0
    complete_time: int | None = None

    def mark_released(self) -> None:
        self.status = TaskStatus.PENDING

    def mark_assigned(
        self,
        vehicle_id: int,
        from_node: int,
        time_now: int,
        vehicle_distance: float,
        assigned_load: float | None = None,
        collaborative: bool = False,
    ) -> None:
        load = self.weight if assigned_load is None else assigned_load
        self.assign_vehicle(
            vehicle_id=vehicle_id,
            assigned_load=load,
            from_node=from_node,
            time_now=time_now,
            vehicle_distance=vehicle_distance,
            collaborative=collaborative,
        )

    @property
    def remaining_weight(self) -> float:
        return max(0.0, self.weight - self.delivered_weight)

    def assign_vehicle(
        self,
        vehicle_id: int,
        assigned_load: float,
        from_node: int,
        time_now: int,
        vehicle_distance: float,
        collaborative: bool,
    ) -> None:
        self.status = TaskStatus.ASSIGNED
        self.collaborative = self.collaborative or collaborative
        self.assigned_vehicles[vehicle_id] = assigned_load
        if self.assigned_time is None:
            self.assigned_time = time_now
            self.assigned_from_node = from_node
            self.assigned_vehicle_distance = vehicle_distance
        if not self.collaborative:
            self.assigned_vehicle = vehicle_id
        else:
            self.assigned_vehicle = None

    def record_delivery(
        self,
        vehicle_id: int,
        delivered_load: float,
        trip_distance: float,
        time_now: int,
    ) -> None:
        if delivered_load > 0:
            self.delivered_weight += delivered_load
            self.delivered_by_vehicle[vehicle_id] = self.delivered_by_vehicle.get(vehicle_id, 0.0) + delivered_load
        self.service_distance += max(0.0, trip_distance)
        self.assigned_vehicles.pop(vehicle_id, None)
        if self.assigned_time is not None:
            self.service_duration = max(0, time_now - self.assigned_time)

    def mark_completed(self, time_now: int, service_distance: float = 0.0) -> None:
        self.status = TaskStatus.COMPLETED
        self.complete_time = time_now
        self.delivered_weight = max(self.delivered_weight, self.weight)
        if service_distance > 0:
            self.service_distance = max(0.0, service_distance)
        if self.assigned_time is not None:
            self.service_duration = max(0, time_now - self.assigned_time)

    def mark_expired(self, time_now: int) -> None:
        self.status = TaskStatus.EXPIRED
        self.complete_time = time_now


@dataclass(slots=True)
class Vehicle:
    id: int
    vehicle_type: str
    current_node: int
    battery: float
    battery_capacity: float
    load_capacity: float
    speed: float
    energy_per_km: float

    status: VehicleStatus = VehicleStatus.IDLE
    assigned_task: int | None = None
    task_load: float = 0.0
    task_start_distance: float | None = None

    route: list[int] = field(default_factory=list)
    route_index: int = 0
    distance_to_next: float = 0.0

    target_node: int | None = None
    target_station: int | None = None
    resume_status: VehicleStatus | None = None
    resume_target_node: int | None = None

    total_distance: float = 0.0
    total_score: float = 0.0

    def is_idle(self) -> bool:
        return self.status == VehicleStatus.IDLE and self.assigned_task is None

    def plan_route(self, route: list[int], target_node: int, status: VehicleStatus) -> None:
        if len(route) < 2:
            raise ValueError("Route must contain at least start and target node")
        self.route = route
        self.route_index = 0
        self.distance_to_next = 0.0
        self.target_node = target_node
        self.status = status

    def assign_task(self, task_id: int, route: list[int], target_node: int, task_load: float) -> None:
        self.assigned_task = task_id
        self.task_load = max(0.0, task_load)
        self.task_start_distance = self.total_distance
        self.plan_route(route=route, target_node=target_node, status=VehicleStatus.MOVING_TO_TASK)

    def clear_route(self) -> None:
        self.route = []
        self.route_index = 0
        self.distance_to_next = 0.0
        self.target_node = None

    def start_waiting_charge(self, station_id: int) -> None:
        self.clear_route()
        self.target_station = station_id
        self.status = VehicleStatus.WAITING_CHARGE

    def start_charging(self, station_id: int) -> None:
        self.target_station = station_id
        self.status = VehicleStatus.CHARGING

    def finish_charging(self) -> None:
        self.target_station = None
        self.status = VehicleStatus.IDLE

    def set_resume_intent(self, status: VehicleStatus, target_node: int) -> None:
        self.resume_status = status
        self.resume_target_node = target_node

    def clear_resume_intent(self) -> None:
        self.resume_status = None
        self.resume_target_node = None

    def clear_task_assignment(self) -> None:
        self.assigned_task = None
        self.task_load = 0.0
        self.task_start_distance = None


@dataclass(slots=True)
class ChargingStation:
    id: int
    node_id: int
    num_piles: int
    charge_rate: float

    queue: deque[int] = field(default_factory=deque)
    charging_slots: list[int | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.charging_slots:
            self.charging_slots = [None for _ in range(self.num_piles)]

    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def occupied_piles(self) -> int:
        return sum(1 for v in self.charging_slots if v is not None)

    def enqueue(self, vehicle_id: int) -> None:
        if vehicle_id not in self.queue and vehicle_id not in self.charging_slots:
            self.queue.append(vehicle_id)


@dataclass(slots=True)
class Depot:
    id: int
    node_id: int
