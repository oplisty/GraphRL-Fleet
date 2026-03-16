from __future__ import annotations

import math

from ..core.entities import TaskStatus
from .base import SchedulerBase


class NearestTaskScheduler(SchedulerBase):
    """Greedy baseline: each idle vehicle picks nearest feasible pending task."""

    def select_actions(self, env) -> list[tuple[int, int]]:
        actions: list[tuple[int, int]] = []
        used_tasks: set[int] = set()

        for vehicle_id in env.get_idle_vehicle_ids():
            vehicle = env.vehicles[vehicle_id]
            best_task_id: int | None = None
            best_dist = math.inf

            for task_id in env.pending_task_ids:
                if task_id in used_tasks:
                    continue
                task = env.tasks[task_id]
                if task.status != TaskStatus.PENDING:
                    continue
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
                    best_task_id = task_id

            if best_task_id is not None:
                actions.append((vehicle_id, best_task_id))
                used_tasks.add(best_task_id)

        return actions
