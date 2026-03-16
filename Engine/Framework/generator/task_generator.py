from __future__ import annotations

import random

from ..core.config import ScenarioConfig
from ..core.entities import Task


def generate_dynamic_tasks(config: ScenarioConfig, candidate_nodes: list[int]) -> list[Task]:
    random.seed(config.random_seed + 1)

    tasks: list[Task] = []
    for task_id in range(config.num_tasks):
        release_time = random.randint(0, max(0, config.horizon - 1))
        ttl = random.randint(config.task_ttl_min, config.task_ttl_max)
        deadline = release_time + ttl
        collaborative = (
            config.collaborative_task_ratio > 0
            and random.random() < config.collaborative_task_ratio
        )
        if collaborative:
            min_w = config.vehicle_load_capacity * config.collaborative_weight_min_scale
            max_w = config.vehicle_load_capacity * config.collaborative_weight_max_scale
            task_weight = round(random.uniform(min_w, max_w), 2)
        else:
            task_weight = round(random.uniform(1, config.task_max_weight), 2)

        tasks.append(
            Task(
                id=task_id,
                release_time=release_time,
                deadline=deadline,
                origin_node=random.choice(candidate_nodes),
                weight=task_weight,
                collaborative=collaborative,
            )
        )

    tasks.sort(key=lambda t: t.release_time)
    return tasks
