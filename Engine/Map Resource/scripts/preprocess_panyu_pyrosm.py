from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _parse_maxspeed(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    # common formats: "60", "60 km/h", "40;60"
    buf = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            buf += ch
        elif buf:
            break
    if not buf:
        return None
    try:
        return float(buf)
    except ValueError:
        return None


def _default_speed_by_highway(highway: str) -> float:
    mapping = {
        "motorway": 80,
        "motorway_link": 50,
        "trunk": 70,
        "trunk_link": 45,
        "primary": 60,
        "primary_link": 40,
        "secondary": 50,
        "secondary_link": 35,
        "tertiary": 40,
        "tertiary_link": 30,
        "residential": 30,
        "unclassified": 30,
        "service": 20,
        "living_street": 15,
    }
    return mapping.get(str(highway), 30)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def preprocess(
    pbf_path: Path,
    out_dir: Path,
    network_type: str = "driving",
    station_num_piles: int = 2,
    station_charge_rate: float = 6.0,
    keep_directed: bool = False,
) -> dict:
    try:
        import geopandas as gpd
        import pandas as pd
        from pyrosm import OSM
    except ImportError as exc:
        raise RuntimeError(
            "Missing required packages for pyrosm pipeline. "
            "Install with: conda install -n DSHW -c conda-forge pyrosm geopandas pyarrow"
        ) from exc

    osm = OSM(str(pbf_path))
    nodes_gdf, edges_gdf = osm.get_network(network_type=network_type, nodes=True)
    pois = osm.get_pois(custom_filter={"amenity": ["charging_station"]})

    if nodes_gdf.empty or edges_gdf.empty:
        raise RuntimeError("Road network extraction returned empty data")

    nodes_gdf = nodes_gdf[["id", "lon", "lat", "geometry"]].copy()
    nodes_gdf = nodes_gdf.rename(columns={"id": "node_id"})
    nodes_gdf["node_id"] = nodes_gdf["node_id"].astype("int64")
    nodes_gdf = nodes_gdf.drop_duplicates(subset=["node_id"])
    nodes_gdf = nodes_gdf.set_crs("EPSG:4326", allow_override=True)

    edges = edges_gdf[["u", "v", "length", "highway", "maxspeed", "oneway"]].copy()
    edges = edges.dropna(subset=["u", "v", "length"])
    edges["u"] = edges["u"].astype("int64")
    edges["v"] = edges["v"].astype("int64")
    edges["distance_km"] = edges["length"].astype(float) / 1000.0
    edges["speed_kmh"] = edges.apply(
        lambda r: _parse_maxspeed(r.get("maxspeed")) or _default_speed_by_highway(r.get("highway")), axis=1
    )
    edges["travel_time"] = edges["distance_km"] / edges["speed_kmh"].clip(lower=1e-3)

    if keep_directed:
        edges["bidirectional"] = False
        edges_out = edges[["u", "v", "distance_km", "travel_time", "speed_kmh", "highway", "bidirectional"]].copy()
    else:
        # Build undirected edges for robust routing in current framework.
        edges["uu"] = edges[["u", "v"]].min(axis=1)
        edges["vv"] = edges[["u", "v"]].max(axis=1)
        edges_out = (
            edges.groupby(["uu", "vv"], as_index=False)
            .agg(
                {
                    "distance_km": "min",
                    "travel_time": "min",
                    "speed_kmh": "mean",
                    "highway": "first",
                }
            )
            .rename(columns={"uu": "u", "vv": "v"})
        )
        edges_out["bidirectional"] = True

    # Keep only nodes that are referenced by edges.
    edge_nodes = set(edges_out["u"].tolist()) | set(edges_out["v"].tolist())
    nodes_gdf = nodes_gdf[nodes_gdf["node_id"].isin(edge_nodes)].copy()

    # Station mapping (nearest node).
    if pois is None or pois.empty:
        stations = pd.DataFrame(columns=["station_id", "node_id", "lon", "lat", "source_osm_id", "source_osm_type"])
    else:
        pois = pois.set_crs("EPSG:4326", allow_override=True)

        nodes_for_join = nodes_gdf[["node_id", "geometry"]].copy()
        join = gpd.sjoin_nearest(
            pois.to_crs("EPSG:3857"),
            nodes_for_join.to_crs("EPSG:3857"),
            how="left",
            distance_col="nn_distance_m",
        ).to_crs("EPSG:4326")

        join = join.dropna(subset=["node_id"]).copy()
        join["node_id"] = join["node_id"].astype("int64")

        # Deduplicate by mapped node.
        dedup = join.sort_values("nn_distance_m").drop_duplicates(subset=["node_id"], keep="first")

        dedup_metric = dedup.to_crs("EPSG:3857")
        centroids = dedup_metric.geometry.centroid.to_crs("EPSG:4326")

        stations = pd.DataFrame(
            {
                "station_id": range(len(dedup)),
                "node_id": dedup["node_id"].astype("int64").tolist(),
                "lon": centroids.x.tolist(),
                "lat": centroids.y.tolist(),
                "source_osm_id": dedup.get("id", None),
                "source_osm_type": dedup.get("osm_type", None),
            }
        )

    # Depot at geometric center mapped to nearest node.
    center_lat = float(nodes_gdf["lat"].mean())
    center_lon = float(nodes_gdf["lon"].mean())

    def nn_node(lat: float, lon: float) -> int:
        best_id = -1
        best = float("inf")
        for _, r in nodes_gdf.iterrows():
            d = (lat - float(r["lat"])) ** 2 + (lon - float(r["lon"])) ** 2
            if d < best:
                best = d
                best_id = int(r["node_id"])
        return best_id

    depot_node = nn_node(center_lat, center_lon)

    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_out = nodes_gdf[["node_id", "lon", "lat"]].copy()
    nodes_out.to_parquet(out_dir / "nodes.parquet", index=False)

    edges_out = edges_out[["u", "v", "distance_km", "travel_time", "speed_kmh", "highway", "bidirectional"]].copy()
    edges_out.to_parquet(out_dir / "edges.parquet", index=False)

    stations.to_parquet(out_dir / "stations.parquet", index=False)

    meta = {
        "source_pbf": str(pbf_path),
        "network_type": network_type,
        "depot_node": depot_node,
        "node_count": int(len(nodes_out)),
        "edge_count": int(len(edges_out)),
        "station_count": int(len(stations)),
        "station_defaults": {
            "num_piles": station_num_piles,
            "charge_rate": station_charge_rate,
        },
        "keep_directed": keep_directed,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess Panyu OSM PBF with pyrosm into framework-ready tables")
    parser.add_argument("--pbf", default="Map Resource/panyu.osm.pbf")
    parser.add_argument("--out-dir", default="Map Resource/processed/panyu")
    parser.add_argument("--network-type", default="driving")
    parser.add_argument("--station-piles", type=int, default=2)
    parser.add_argument("--station-rate", type=float, default=6.0)
    parser.add_argument("--keep-directed", action="store_true")
    args = parser.parse_args()

    meta = preprocess(
        pbf_path=Path(args.pbf),
        out_dir=Path(args.out_dir),
        network_type=args.network_type,
        station_num_piles=args.station_piles,
        station_charge_rate=args.station_rate,
        keep_directed=args.keep_directed,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
