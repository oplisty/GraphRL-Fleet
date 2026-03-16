from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import osmium


TARGET_NAMES = {"番禺区", "Panyu District"}
DRIVABLE_HIGHWAY = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "residential",
    "unclassified",
    "service",
    "living_street",
}


@dataclass
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_lat + self.max_lat) / 2, (self.min_lon + self.max_lon) / 2)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_panyu_bbox(pbf: Path) -> tuple[dict, BBox]:
    class RelationFinder(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.relation_id: int | None = None
            self.tags: dict[str, str] = {}
            self.way_ids: set[int] = set()

        def relation(self, r: osmium.osm.Relation) -> None:
            if self.relation_id is not None:
                return
            tags = {k: v for k, v in r.tags}
            if tags.get("boundary") != "administrative":
                return
            name = tags.get("name", "")
            name_en = tags.get("name:en", "")
            if name not in TARGET_NAMES and name_en not in TARGET_NAMES:
                return
            self.relation_id = r.id
            self.tags = tags
            for m in r.members:
                if m.type == "w":
                    self.way_ids.add(m.ref)

    class WayNodes(osmium.SimpleHandler):
        def __init__(self, way_ids: set[int]) -> None:
            super().__init__()
            self.way_ids = way_ids
            self.node_ids: set[int] = set()

        def way(self, w: osmium.osm.Way) -> None:
            if w.id not in self.way_ids:
                return
            for n in w.nodes:
                self.node_ids.add(n.ref)

    class NodeBounds(osmium.SimpleHandler):
        def __init__(self, node_ids: set[int]) -> None:
            super().__init__()
            self.node_ids = node_ids
            self.min_lat = float("inf")
            self.min_lon = float("inf")
            self.max_lat = float("-inf")
            self.max_lon = float("-inf")

        def node(self, n: osmium.osm.Node) -> None:
            if n.id not in self.node_ids or not n.location.valid():
                return
            lat = n.location.lat
            lon = n.location.lon
            self.min_lat = min(self.min_lat, lat)
            self.min_lon = min(self.min_lon, lon)
            self.max_lat = max(self.max_lat, lat)
            self.max_lon = max(self.max_lon, lon)

    rf = RelationFinder()
    rf.apply_file(str(pbf), locations=False)
    if rf.relation_id is None:
        raise RuntimeError("Panyu relation not found")

    wn = WayNodes(rf.way_ids)
    wn.apply_file(str(pbf), locations=False)

    nb = NodeBounds(wn.node_ids)
    nb.apply_file(str(pbf), locations=False)

    relation_info = {
        "id": rf.relation_id,
        "name": rf.tags.get("name"),
        "name_en": rf.tags.get("name:en"),
        "admin_level": rf.tags.get("admin_level"),
        "boundary": rf.tags.get("boundary"),
    }
    bbox = BBox(nb.min_lat, nb.min_lon, nb.max_lat, nb.max_lon)
    return relation_info, bbox


class PanyuGraphBuilder(osmium.SimpleHandler):
    def __init__(self, bbox: BBox) -> None:
        super().__init__()
        self.bbox = bbox
        self.node_coords: dict[int, tuple[float, float]] = {}
        self.road_node_ids: set[int] = set()
        self.edges: dict[tuple[int, int], float] = {}
        self.station_points: list[tuple[float, float, str]] = []

    def _in_bbox(self, lat: float, lon: float) -> bool:
        return self.bbox.contains(lat, lon)

    def node(self, n: osmium.osm.Node) -> None:
        if not n.location.valid():
            return
        lat = n.location.lat
        lon = n.location.lon
        if not self._in_bbox(lat, lon):
            return

        self.node_coords[n.id] = (lat, lon)
        tags = {k: v for k, v in n.tags}
        if tags.get("amenity") == "charging_station":
            self.station_points.append((lat, lon, "node"))

    def way(self, w: osmium.osm.Way) -> None:
        tags = {k: v for k, v in w.tags}

        coords: list[tuple[int, float, float]] = []
        for n in w.nodes:
            if n.location.valid():
                coords.append((n.ref, n.location.lat, n.location.lon))

        if len(coords) < 2:
            return

        inside = [self._in_bbox(lat, lon) for _, lat, lon in coords]
        if not any(inside):
            return

        if tags.get("amenity") == "charging_station":
            in_coords = [(lat, lon) for (_, lat, lon), ok in zip(coords, inside) if ok]
            if in_coords:
                lat = sum(x for x, _ in in_coords) / len(in_coords)
                lon = sum(y for _, y in in_coords) / len(in_coords)
                self.station_points.append((lat, lon, "way"))

        htype = tags.get("highway")
        if htype not in DRIVABLE_HIGHWAY:
            return

        for i in range(len(coords) - 1):
            n1, lat1, lon1 = coords[i]
            n2, lat2, lon2 = coords[i + 1]
            if not (self._in_bbox(lat1, lon1) and self._in_bbox(lat2, lon2)):
                continue
            if n1 == n2:
                continue

            d = haversine_km(lat1, lon1, lat2, lon2)
            if d <= 0:
                continue
            key = (n1, n2) if n1 < n2 else (n2, n1)
            if key not in self.edges or d < self.edges[key]:
                self.edges[key] = d
            self.road_node_ids.add(n1)
            self.road_node_ids.add(n2)


def nearest_node(lat: float, lon: float, node_coords: dict[int, tuple[float, float]]) -> int:
    best_id = -1
    best_d = float("inf")
    for nid, (nlat, nlon) in node_coords.items():
        d = (lat - nlat) ** 2 + (lon - nlon) ** 2
        if d < best_d:
            best_d = d
            best_id = nid
    return best_id


def build_graph_json(pbf: Path, out_json: Path) -> dict:
    relation_info, bbox = find_panyu_bbox(pbf)

    builder = PanyuGraphBuilder(bbox)
    builder.apply_file(str(pbf), locations=True)

    used_nodes = sorted(builder.road_node_ids)
    node_coords = {nid: builder.node_coords[nid] for nid in used_nodes if nid in builder.node_coords}

    stations = []
    station_node_ids = set()
    for i, (lat, lon, source) in enumerate(builder.station_points):
        nid = nearest_node(lat, lon, node_coords)
        if nid == -1 or nid in station_node_ids:
            continue
        station_node_ids.add(nid)
        stations.append(
            {
                "id": len(stations),
                "node_id": nid,
                "lat": lat,
                "lon": lon,
                "source": source,
            }
        )

    center_lat, center_lon = bbox.center
    depot_node = nearest_node(center_lat, center_lon, node_coords)

    edges = []
    for (u, v), d in builder.edges.items():
        if u not in node_coords or v not in node_coords:
            continue
        edges.append({"u": u, "v": v, "distance_km": round(d, 6), "travel_time": round(d, 6)})

    payload = {
        "meta": {
            "source_pbf": str(pbf),
            "relation": relation_info,
            "bbox": {
                "min_lat": round(bbox.min_lat, 6),
                "min_lon": round(bbox.min_lon, 6),
                "max_lat": round(bbox.max_lat, 6),
                "max_lon": round(bbox.max_lon, 6),
            },
            "drivable_highway": sorted(DRIVABLE_HIGHWAY),
            "depot_node": depot_node,
        },
        "nodes": [
            {"id": nid, "lat": round(lat, 7), "lon": round(lon, 7)}
            for nid, (lat, lon) in node_coords.items()
        ],
        "edges": edges,
        "stations": stations,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {
        "nodes": len(payload["nodes"]),
        "edges": len(payload["edges"]),
        "stations": len(payload["stations"]),
        "depot_node": depot_node,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", default="Map Resource/panyu.osm.pbf")
    parser.add_argument("--out", default="Map Resource/analysis/panyu_graph.json")
    args = parser.parse_args()

    summary = build_graph_json(Path(args.pbf), Path(args.out))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
