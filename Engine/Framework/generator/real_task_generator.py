from __future__ import annotations

import random

from ..core.config import ScenarioConfig
from ..core.entities import Task


def generate_real_tasks(
    config: ScenarioConfig,
    candidate_node_ids: list[int],
    mode: str = "uniform_nodes",
    hotspot_node_ids: list[int] | None = None,
    hotspot_ratio: float = 0.7,
) -> list[Task]:
    """Generate dynamic tasks on real road-network nodes.

    mode:
    - uniform_nodes: uniformly sample from all candidate nodes.
    - hotspot_nodes: sample from hotspot nodes with a given ratio.
    """
    if not candidate_node_ids:
        raise ValueError("candidate_node_ids is empty")

    random.seed(config.random_seed + 11)
    tasks: list[Task] = []

    use_hotspot = mode == "hotspot_nodes" and hotspot_node_ids
    hotspots = hotspot_node_ids or []

    for task_id in range(config.num_tasks):
        release_time = random.randint(0, max(0, config.horizon - 1))
        ttl = random.randint(config.task_ttl_min, config.task_ttl_max)
        deadline = release_time + ttl
        collaborative = (
            config.collaborative_task_ratio > 0
            and random.random() < config.collaborative_task_ratio
        )

        if use_hotspot and random.random() < hotspot_ratio:
            origin_node = random.choice(hotspots)
        else:
            origin_node = random.choice(candidate_node_ids)

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
                origin_node=origin_node,
                weight=task_weight,
                collaborative=collaborative,
            )
        )

    tasks.sort(key=lambda x: x.release_time)
    return tasks
