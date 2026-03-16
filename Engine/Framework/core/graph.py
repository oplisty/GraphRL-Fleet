from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class Node:
    id: int
    x: float
    y: float
    node_type: str  # depot / station / road / task_point


@dataclass(slots=True)
class Edge:
    to: int
    distance: float
    travel_time: float


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[int, Node] = {}
        self.adj: dict[int, list[Edge]] = {}
        self.edge_lookup: dict[tuple[int, int], Edge] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self.adj.setdefault(node.id, [])

    def add_edge(
        self,
        from_id: int,
        to_id: int,
        distance: float,
        travel_time: float | None = None,
        bidirectional: bool = True,
    ) -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError("Both edge endpoints must exist in graph nodes")

        if travel_time is None:
            travel_time = distance

        self.adj[from_id].append(Edge(to=to_id, distance=distance, travel_time=travel_time))
        self.edge_lookup[(from_id, to_id)] = self.adj[from_id][-1]
        if bidirectional:
            self.adj[to_id].append(Edge(to=from_id, distance=distance, travel_time=travel_time))
            self.edge_lookup[(to_id, from_id)] = self.adj[to_id][-1]

    def neighbors(self, node_id: int) -> list[Edge]:
        return self.adj.get(node_id, [])

    def edge_distance(self, u: int, v: int) -> float | None:
        edge = self.edge_lookup.get((u, v))
        return None if edge is None else edge.distance

    def euclidean_distance(self, u: int, v: int) -> float:
        n1 = self.nodes[u]
        n2 = self.nodes[v]
        return math.hypot(n1.x - n2.x, n1.y - n2.y)

    def __len__(self) -> int:
        return len(self.nodes)
