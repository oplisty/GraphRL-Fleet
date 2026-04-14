from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Framework.core import Environment


@dataclass(frozen=True, slots=True)
class DiscreteState:
    idle_level: int
    backlog_level: int
    urgency_level: int
    low_battery_level: int
    charge_congestion_level: int

    def as_tuple(self) -> tuple[int, int, int, int, int]:
        return (
            self.idle_level,
            self.backlog_level,
            self.urgency_level,
            self.low_battery_level,
            self.charge_congestion_level,
        )


class StateEncoder:
    """Encode the simulation state into a small discrete tuple for tabular Q-learning."""

    def encode(self, env: Environment) -> DiscreteState:
        vehicle_count = max(1, len(env.vehicles))
        pending_tasks = [env.tasks[task_id] for task_id in env.pending_task_ids if task_id in env.tasks]

        idle_ratio = len(env.get_idle_vehicle_ids()) / vehicle_count
        backlog_ratio = len(pending_tasks) / vehicle_count

        urgent_count = sum(
            1
            for task in pending_tasks
            if task.deadline - env.current_time <= max(10, env.config.time_step)
        )
        urgency_ratio = urgent_count / max(1, len(pending_tasks))

        low_battery_ratio = sum(
            1
            for vehicle in env.vehicles.values()
            if vehicle.battery <= vehicle.battery_capacity * env.config.low_battery_ratio
        ) / vehicle_count

        avg_queue = (
            sum(station.queue_length for station in env.stations.values()) / max(1, len(env.stations))
            if env.stations
            else 0.0
        )

        return DiscreteState(
            idle_level=self._three_level(idle_ratio, thresholds=(0.3, 0.7)),
            backlog_level=self._three_level(backlog_ratio, thresholds=(1.0, 2.5)),
            urgency_level=self._three_level(urgency_ratio, thresholds=(0.2, 0.5)),
            low_battery_level=self._three_level(low_battery_ratio, thresholds=(0.2, 0.5)),
            charge_congestion_level=self._three_level(avg_queue, thresholds=(0.5, 1.5)),
        )

    @staticmethod
    def _three_level(value: float, thresholds: tuple[float, float]) -> int:
        low, high = thresholds
        if value < low:
            return 0
        if value < high:
            return 1
        return 2
