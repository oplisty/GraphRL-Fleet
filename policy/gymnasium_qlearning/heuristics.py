from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from Framework.core import TaskStatus
from Framework.scheduler import EarliestDeadlineScheduler, HeaviestTaskScheduler, NearestTaskScheduler
from Framework.scheduler.base import SchedulerBase

if TYPE_CHECKING:
    from Framework.core import Environment


class BestScoreScheduler(SchedulerBase):
    """Greedy score-based rule used as a low-level heuristic for Q-learning."""

    def select_actions(self, env: Environment) -> list[tuple[int, int]]:
        actions: list[tuple[int, int]] = []
        used_tasks: set[int] = set()

        for vehicle_id in env.get_idle_vehicle_ids():
            vehicle = env.vehicles[vehicle_id]
            best_task_id: int | None = None
            best_score = -math.inf

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
                if math.isinf(dist):
                    continue

                deadline_left = max(1.0, task.deadline - env.current_time)
                lateness_risk = dist / deadline_left
                energy_risk = 1.0 - min(1.0, vehicle.battery / max(vehicle.battery_capacity, 1e-9))
                score = (
                    task.weight * 2.0
                    + max(0.0, env.config.reward_base - dist * env.config.distance_penalty)
                    - dist
                    - 20.0 * lateness_risk
                    - 10.0 * energy_risk
                )
                if score > best_score:
                    best_score = score
                    best_task_id = task_id

            if best_task_id is not None:
                actions.append((vehicle_id, best_task_id))
                used_tasks.add(best_task_id)

        return actions


@dataclass(frozen=True, slots=True)
class UnifiedRule:
    name: str
    scheduler_factory: Callable[[], SchedulerBase]
    charging_strategy: str = "optimal_station"

    def apply(self, env: Environment) -> list[tuple[int, int] | dict]:
        env.config.charging_strategy = self.charging_strategy
        scheduler = self.scheduler_factory()
        return scheduler.select_actions(env)


RULE_LIBRARY: tuple[UnifiedRule, ...] = (
    UnifiedRule(
        name="nearest_task_with_best_charge",
        scheduler_factory=NearestTaskScheduler,
        charging_strategy="optimal_station",
    ),
    UnifiedRule(
        name="earliest_deadline_with_best_charge",
        scheduler_factory=EarliestDeadlineScheduler,
        charging_strategy="optimal_station",
    ),
    UnifiedRule(
        name="max_weight_with_best_charge",
        scheduler_factory=HeaviestTaskScheduler,
        charging_strategy="optimal_station",
    ),
    UnifiedRule(
        name="best_score_with_best_charge",
        scheduler_factory=BestScoreScheduler,
        charging_strategy="optimal_station",
    ),
    UnifiedRule(
        name="nearest_task_with_nearest_charge",
        scheduler_factory=NearestTaskScheduler,
        charging_strategy="nearest_station",
    ),
    UnifiedRule(
        name="earliest_deadline_with_nearest_charge",
        scheduler_factory=EarliestDeadlineScheduler,
        charging_strategy="nearest_station",
    ),
    UnifiedRule(
        name="max_weight_with_nearest_charge",
        scheduler_factory=HeaviestTaskScheduler,
        charging_strategy="nearest_station",
    ),
    UnifiedRule(
        name="best_score_with_nearest_charge",
        scheduler_factory=BestScoreScheduler,
        charging_strategy="nearest_station",
    ),
)
