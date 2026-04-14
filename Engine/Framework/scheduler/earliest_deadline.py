from __future__ import annotations

import math

from ..core.entities import TaskStatus
from .base import SchedulerBase


class EarliestDeadlineScheduler(SchedulerBase):
    """Greedy baseline: choose the feasible pending task with earliest deadline first."""

    def select_actions(self, env) -> list[tuple[int, int]]:
        actions: list[tuple[int, int]] = []
        idle_vehicles = env.get_idle_vehicle_ids()
        used_vehicles: set[int] = set()

        remaining_tasks = [
            task
            for task in env.tasks.values()
            if task.status == TaskStatus.PENDING and task.id in env.pending_task_ids
        ]
        remaining_tasks.sort(key=lambda t: (t.deadline, t.release_time, t.weight, t.id))

        for task in remaining_tasks:
            chosen_vehicle: int | None = None
            best_dist = math.inf

            for vehicle_id in idle_vehicles:
                if vehicle_id in used_vehicles:
                    continue

                vehicle = env.vehicles[vehicle_id]
                if task.weight > vehicle.load_capacity:
                    continue

                if not env.pathfinder.can_finish_task_and_return(
                    vehicle=vehicle,
                    current_node=vehicle.current_node,
                    task_node=task.origin_node,
                    depot_node=env.depot.node_id,
                    safety_margin=env.config.safety_energy_margin,
                ):
                    continue

                dist = env.pathfinder.shortest_distance(vehicle.current_node, task.origin_node)
                if dist < best_dist:
                    best_dist = dist
                    chosen_vehicle = vehicle_id

            if chosen_vehicle is not None:
                actions.append((chosen_vehicle, task.id))
                used_vehicles.add(chosen_vehicle)

        return actions
