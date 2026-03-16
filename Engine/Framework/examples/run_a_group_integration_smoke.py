from __future__ import annotations

import math

from Framework.examples.run_baseline import build_environment
from Framework.scheduler.base import SchedulerBase


class IntegrationSmokeScheduler(SchedulerBase):
    """Smoke scheduler for A/B group interface integration."""

    def select_actions(self, env) -> list[tuple[int, int] | dict]:
        actions: list[tuple[int, int] | dict] = []
        idle_vehicle_ids = env.get_idle_vehicle_ids()
        if not idle_vehicle_ids:
            return actions

        idle_vehicles = [env.vehicles[vid] for vid in idle_vehicle_ids]
        max_single_load = max((v.load_capacity for v in idle_vehicles), default=0.0)

        for task in env.get_available_tasks():
            if task.weight <= max_single_load:
                for vehicle in idle_vehicles:
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
                    return [(vehicle.id, task.id)]
                continue

            # Collaborative action for overweight tasks.
            candidates: list[tuple[float, int, float]] = []
            for vehicle in idle_vehicles:
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
                candidates.append((dist, vehicle.id, vehicle.load_capacity))

            if not candidates:
                continue
            candidates.sort(key=lambda x: (x[0], -x[2]))
            remaining = task.weight
            alloc: dict[int, float] = {}
            for _, vid, cap in candidates:
                if remaining <= 1e-9:
                    break
                load = min(cap, remaining)
                alloc[vid] = load
                remaining -= load
            if remaining <= 1e-9 and len(alloc) >= 2:
                return [{"task_id": task.id, "vehicle_allocations": alloc}]

        return actions


def main() -> None:
    # Use a non-zero collaborative ratio to ensure collaborative path is exercised.
    env = build_environment(
        scale="small",
        scheduler_name="nearest",
        collaborative_task_ratio=0.3,
        enable_collaborative_tasks=True,
        auto_collaborative_dispatch=False,
    )
    summary = env.run(end_time=80, scheduler=IntegrationSmokeScheduler())
    print("A/B Integration Smoke Summary")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    print("PASS: scheduler can use Environment APIs with single + collaborative dispatch formats.")


if __name__ == "__main__":
    main()
