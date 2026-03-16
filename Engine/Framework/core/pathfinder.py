from __future__ import annotations

import heapq
import math
from typing import Protocol

from .graph import Graph


class EnergyVehicle(Protocol):
    battery: float
    energy_per_km: float


class PathFinder:
    """Shortest path utility with distance/path caching for repeated queries."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.distance_cache: dict[tuple[int, int], float] = {}
        self.path_cache: dict[tuple[int, int], list[int]] = {}
        self.source_dist_cache: dict[int, dict[int, float]] = {}
        self.source_prev_cache: dict[int, dict[int, int]] = {}

    def clear_cache(self) -> None:
        self.distance_cache.clear()
        self.path_cache.clear()
        self.source_dist_cache.clear()
        self.source_prev_cache.clear()

    def shortest_distance(self, start: int, end: int) -> float:
        key = (start, end)
        if key in self.distance_cache:
            return self.distance_cache[key]

        dist, _ = self._get_source_shortest_tree(start)
        value = dist.get(end, math.inf)
        self.distance_cache[key] = value
        return value

    def shortest_path(self, start: int, end: int) -> list[int]:
        key = (start, end)
        if key in self.path_cache:
            return self.path_cache[key]

        dist, prev = self._get_source_shortest_tree(start)
        if end not in dist or math.isinf(dist[end]):
            self.path_cache[key] = []
            self.distance_cache[key] = math.inf
            return []

        path = [end]
        cur = end
        while cur != start:
            cur = prev[cur]
            path.append(cur)
        path.reverse()

        self.path_cache[key] = path
        self.distance_cache[key] = dist[end]
        return path

    def _get_source_shortest_tree(self, start: int) -> tuple[dict[int, float], dict[int, int]]:
        if start not in self.source_dist_cache:
            dist, prev = self._run_dijkstra(start)
            self.source_dist_cache[start] = dist
            self.source_prev_cache[start] = prev
        return self.source_dist_cache[start], self.source_prev_cache[start]

    def can_reach(
        self,
        vehicle: EnergyVehicle,
        start: int,
        end: int,
        safety_margin: float = 0.0,
    ) -> bool:
        distance = self.shortest_distance(start, end)
        if math.isinf(distance):
            return False
        needed = distance * vehicle.energy_per_km + safety_margin
        return vehicle.battery >= needed

    def can_finish_task_and_return(
        self,
        vehicle: EnergyVehicle,
        current_node: int,
        task_node: int,
        depot_node: int,
        safety_margin: float = 0.0,
    ) -> bool:
        d1 = self.shortest_distance(current_node, task_node)
        d2 = self.shortest_distance(task_node, depot_node)
        if math.isinf(d1) or math.isinf(d2):
            return False
        needed = (d1 + d2) * vehicle.energy_per_km + safety_margin
        return vehicle.battery >= needed

    def nearest_reachable_station(
        self,
        vehicle: EnergyVehicle,
        start: int,
        station_node_ids: list[int],
        safety_margin: float = 0.0,
    ) -> int | None:
        best_station: int | None = None
        best_distance = math.inf

        for station_node in station_node_ids:
            distance = self.shortest_distance(start, station_node)
            if math.isinf(distance):
                continue
            needed = distance * vehicle.energy_per_km + safety_margin
            if vehicle.battery >= needed and distance < best_distance:
                best_distance = distance
                best_station = station_node

        return best_station

    def _run_dijkstra(self, start: int) -> tuple[dict[int, float], dict[int, int]]:
        distances = {node_id: math.inf for node_id in self.graph.nodes}
        previous: dict[int, int] = {}

        if start not in distances:
            return distances, previous

        distances[start] = 0.0
        heap: list[tuple[float, int]] = [(0.0, start)]

        while heap:
            cur_dist, node = heapq.heappop(heap)
            if cur_dist > distances[node]:
                continue

            for edge in self.graph.neighbors(node):
                alt = cur_dist + edge.distance
                if alt < distances[edge.to]:
                    distances[edge.to] = alt
                    previous[edge.to] = node
                    heapq.heappush(heap, (alt, edge.to))

        return distances, previous
