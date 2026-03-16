from __future__ import annotations

import json
from pathlib import Path

from ..core.entities import ChargingStation, Depot
from ..core.graph import Graph, Node
from .map_generator import MapBuildResult


def load_panyu_map(
    graph_json_path: str | Path,
    station_num_piles: int = 2,
    station_charge_rate: float = 6.0,
) -> MapBuildResult:
    """Load pre-built Panyu graph JSON into framework Graph/Depot/Station objects."""
    path = Path(graph_json_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    graph = Graph()

    station_node_ids = {s["node_id"] for s in payload.get("stations", [])}
    depot_node = payload["meta"]["depot_node"]

    for nd in payload["nodes"]:
        nid = nd["id"]
        if nid == depot_node:
            node_type = "depot"
        elif nid in station_node_ids:
            node_type = "station"
        else:
            node_type = "road"
        graph.add_node(
            Node(
                id=nid,
                x=float(nd["lon"]),
                y=float(nd["lat"]),
                node_type=node_type,
            )
        )

    for e in payload["edges"]:
        u = int(e["u"])
        v = int(e["v"])
        dist = float(e["distance_km"])
        t = float(e.get("travel_time", dist))
        graph.add_edge(u, v, distance=dist, travel_time=t, bidirectional=True)

    depot = Depot(id=0, node_id=depot_node)

    stations: dict[int, ChargingStation] = {}
    for s in payload.get("stations", []):
        sid = int(s["id"])
        stations[sid] = ChargingStation(
            id=sid,
            node_id=int(s["node_id"]),
            num_piles=station_num_piles,
            charge_rate=station_charge_rate,
        )

    task_candidate_nodes = [
        nid
        for nid in graph.nodes
        if nid != depot.node_id and nid not in station_node_ids
    ]

    return MapBuildResult(
        graph=graph,
        depot=depot,
        stations=stations,
        task_candidate_nodes=task_candidate_nodes,
    )
