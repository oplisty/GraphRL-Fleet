from __future__ import annotations

import json
from pathlib import Path

from ..core.entities import ChargingStation, Depot
from ..core.graph import Graph, Node
from .map_generator import MapBuildResult


def load_real_map_from_processed(
    processed_dir: str | Path,
    station_num_piles: int = 2,
    station_charge_rate: float = 6.0,
) -> MapBuildResult:
    """Load preprocessed real map data (parquet/json) into framework objects.

    Expected files in processed_dir:
    - nodes.parquet: node_id, lon, lat
    - edges.parquet: u, v, distance_km, travel_time
    - stations.parquet: station_id, node_id, lon, lat
    - meta.json (optional): depot_node
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required for loading processed real map files. "
            "Install in conda env."
        ) from exc

    processed_dir = Path(processed_dir)
    nodes_path = processed_dir / "nodes.parquet"
    edges_path = processed_dir / "edges.parquet"
    stations_path = processed_dir / "stations.parquet"
    meta_path = processed_dir / "meta.json"

    try:
        nodes_df = pd.read_parquet(nodes_path)
        edges_df = pd.read_parquet(edges_path)
        stations_df = pd.read_parquet(stations_path) if stations_path.exists() else pd.DataFrame()
    except Exception as exc:
        raise RuntimeError(
            "Failed to read parquet files in processed_dir. "
            "Please install parquet engine dependencies: pyarrow or fastparquet."
        ) from exc

    graph = Graph()

    station_node_ids = set()
    if not stations_df.empty and "node_id" in stations_df.columns:
        station_node_ids = {int(x) for x in stations_df["node_id"].tolist()}

    depot_node = None
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        depot_node = meta.get("depot_node")

    if depot_node is None:
        # fallback: pick first node
        depot_node = int(nodes_df.iloc[0]["node_id"])

    for _, row in nodes_df.iterrows():
        nid = int(row["node_id"])
        lon = float(row["lon"])
        lat = float(row["lat"])
        if nid == depot_node:
            ntype = "depot"
        elif nid in station_node_ids:
            ntype = "station"
        else:
            ntype = "road"

        graph.add_node(Node(id=nid, x=lon, y=lat, node_type=ntype))

    for _, row in edges_df.iterrows():
        u = int(row["u"])
        v = int(row["v"])
        dist = float(row["distance_km"])
        travel_time = float(row["travel_time"])
        bidirectional = bool(row["bidirectional"]) if "bidirectional" in edges_df.columns else True
        graph.add_edge(u, v, distance=dist, travel_time=travel_time, bidirectional=bidirectional)

    depot = Depot(id=0, node_id=int(depot_node))

    stations: dict[int, ChargingStation] = {}
    if not stations_df.empty:
        for _, row in stations_df.iterrows():
            sid = int(row["station_id"])
            stations[sid] = ChargingStation(
                id=sid,
                node_id=int(row["node_id"]),
                num_piles=station_num_piles,
                charge_rate=station_charge_rate,
            )

    task_candidate_nodes = [
        node_id
        for node_id in graph.nodes
        if node_id != depot.node_id and node_id not in station_node_ids
    ]

    return MapBuildResult(
        graph=graph,
        depot=depot,
        stations=stations,
        task_candidate_nodes=task_candidate_nodes,
    )
