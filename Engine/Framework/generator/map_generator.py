from __future__ import annotations

from dataclasses import dataclass
import random

from ..core.config import ScenarioConfig
from ..core.entities import ChargingStation, Depot
from ..core.graph import Graph, Node


@dataclass(slots=True)
class MapBuildResult:
    graph: Graph
    depot: Depot
    stations: dict[int, ChargingStation]
    task_candidate_nodes: list[int]


def generate_random_map(config: ScenarioConfig, k_neighbors: int = 4) -> MapBuildResult:
    random.seed(config.random_seed)

    graph = Graph()

    depot_node_id = 0
    graph.add_node(
        Node(
            id=depot_node_id,
            x=config.map_width / 2,
            y=config.map_height / 2,
            node_type="depot",
        )
    )
    depot = Depot(id=0, node_id=depot_node_id)

    road_node_ids: list[int] = []
    for i in range(config.num_road_nodes):
        node_id = i + 1
        road_node_ids.append(node_id)
        graph.add_node(
            Node(
                id=node_id,
                x=random.uniform(0, config.map_width),
                y=random.uniform(0, config.map_height),
                node_type="road",
            )
        )

    stations: dict[int, ChargingStation] = {}
    station_start_id = config.num_road_nodes + 1
    for i in range(config.num_stations):
        node_id = station_start_id + i
        graph.add_node(
            Node(
                id=node_id,
                x=random.uniform(0, config.map_width),
                y=random.uniform(0, config.map_height),
                node_type="station",
            )
        )
        stations[i] = ChargingStation(
            id=i,
            node_id=node_id,
            num_piles=config.station_num_piles,
            charge_rate=config.station_charge_rate,
        )

    _build_sparse_connections(graph, k_neighbors=max(2, k_neighbors))

    return MapBuildResult(
        graph=graph,
        depot=depot,
        stations=stations,
        task_candidate_nodes=road_node_ids,
    )


def _build_sparse_connections(graph: Graph, k_neighbors: int) -> None:
    node_ids = list(graph.nodes)

    # First connect each node to one nearest previous node to guarantee connectivity.
    for idx in range(1, len(node_ids)):
        current = node_ids[idx]
        best_prev = min(
            node_ids[:idx],
            key=lambda other: graph.euclidean_distance(current, other),
        )
        distance = graph.euclidean_distance(current, best_prev)
        _connect_if_absent(graph, current, best_prev, distance)

    # Then add extra nearest-neighbor edges for richer routes.
    for node_id in node_ids:
        candidates = [other for other in node_ids if other != node_id]
        candidates.sort(key=lambda other: graph.euclidean_distance(node_id, other))
        for other in candidates[:k_neighbors]:
            distance = graph.euclidean_distance(node_id, other)
            _connect_if_absent(graph, node_id, other, distance)


def _connect_if_absent(graph: Graph, u: int, v: int, distance: float) -> None:
    if graph.edge_distance(u, v) is not None:
        return
    graph.add_edge(u, v, distance=distance, travel_time=distance, bidirectional=True)
