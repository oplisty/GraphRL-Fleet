from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import osmium


TARGET_NAMES = {"番禺区", "Panyu District"}


@dataclass
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class BoundaryRelationFinder(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.relation_id: int | None = None
        self.relation_tags: dict[str, str] = {}
        self.member_way_ids: set[int] = set()

    def relation(self, r: osmium.osm.Relation) -> None:
        if self.relation_id is not None:
            return

        tags = {k: v for k, v in r.tags}
        name = tags.get("name", "")
        name_en = tags.get("name:en", "")

        if tags.get("boundary") != "administrative":
            return
        if name not in TARGET_NAMES and name_en not in TARGET_NAMES:
            return

        self.relation_id = r.id
        self.relation_tags = tags
        for m in r.members:
            if m.type == "w":
                self.member_way_ids.add(m.ref)


class BoundaryWayNodeCollector(osmium.SimpleHandler):
    def __init__(self, target_way_ids: set[int]) -> None:
        super().__init__()
        self.target_way_ids = target_way_ids
        self.node_ids: set[int] = set()

    def way(self, w: osmium.osm.Way) -> None:
        if w.id not in self.target_way_ids:
            return
        for n in w.nodes:
            self.node_ids.add(n.ref)


class NodeBBoxCollector(osmium.SimpleHandler):
    def __init__(self, target_node_ids: set[int]) -> None:
        super().__init__()
        self.target_node_ids = target_node_ids
        self.min_lat = float("inf")
        self.min_lon = float("inf")
        self.max_lat = float("-inf")
        self.max_lon = float("-inf")
        self.found_nodes = 0

    def node(self, n: osmium.osm.Node) -> None:
        if n.id not in self.target_node_ids or not n.location.valid():
            return
        lat = n.location.lat
        lon = n.location.lon
        self.found_nodes += 1
        self.min_lat = min(self.min_lat, lat)
        self.min_lon = min(self.min_lon, lon)
        self.max_lat = max(self.max_lat, lat)
        self.max_lon = max(self.max_lon, lon)

    def to_bbox(self) -> BBox:
        return BBox(self.min_lat, self.min_lon, self.max_lat, self.max_lon)


class PanyuStatsCollector(osmium.SimpleHandler):
    def __init__(self, bbox: BBox) -> None:
        super().__init__()
        self.bbox = bbox

        self.total_nodes_in_bbox = 0
        self.total_ways_intersect_bbox = 0

        self.road_way_count = 0
        self.road_node_ids_in_bbox: set[int] = set()
        self.road_edge_count_approx = 0
        self.road_total_length_km = 0.0
        self.road_length_by_type_km: Counter[str] = Counter()
        self.road_count_by_type: Counter[str] = Counter()

        self.charging_station_node_count = 0
        self.charging_station_way_count = 0

    def _in_bbox(self, lat: float, lon: float) -> bool:
        return self.bbox.contains(lat, lon)

    def node(self, n: osmium.osm.Node) -> None:
        if not n.location.valid():
            return
        lat = n.location.lat
        lon = n.location.lon
        if not self._in_bbox(lat, lon):
            return

        self.total_nodes_in_bbox += 1
        tags = {k: v for k, v in n.tags}
        if tags.get("amenity") == "charging_station":
            self.charging_station_node_count += 1

    def way(self, w: osmium.osm.Way) -> None:
        coords: list[tuple[float, float, int]] = []
        for n in w.nodes:
            if n.location.valid():
                coords.append((n.location.lat, n.location.lon, n.ref))

        if len(coords) < 2:
            return

        inside = [self._in_bbox(lat, lon) for lat, lon, _ in coords]
        if not any(inside):
            return

        self.total_ways_intersect_bbox += 1
        tags = {k: v for k, v in w.tags}

        if tags.get("amenity") == "charging_station":
            self.charging_station_way_count += 1

        htype = tags.get("highway")
        if not htype:
            return

        self.road_way_count += 1
        self.road_count_by_type[htype] += 1

        for (lat, lon, node_id), ok in zip(coords, inside):
            if ok:
                self.road_node_ids_in_bbox.add(node_id)

        for i in range(len(coords) - 1):
            lat1, lon1, _ = coords[i]
            lat2, lon2, _ = coords[i + 1]
            if self._in_bbox(lat1, lon1) or self._in_bbox(lat2, lon2):
                seg = haversine_km(lat1, lon1, lat2, lon2)
                self.road_total_length_km += seg
                self.road_length_by_type_km[htype] += seg
                self.road_edge_count_approx += 1


def run_analysis(pbf: Path) -> dict:
    rf = BoundaryRelationFinder()
    rf.apply_file(str(pbf), locations=False)
    if rf.relation_id is None:
        raise RuntimeError("番禺区行政边界 relation 未在 PBF 中找到")

    wc = BoundaryWayNodeCollector(rf.member_way_ids)
    wc.apply_file(str(pbf), locations=False)

    nc = NodeBBoxCollector(wc.node_ids)
    nc.apply_file(str(pbf), locations=False)
    bbox = nc.to_bbox()

    sc = PanyuStatsCollector(bbox)
    sc.apply_file(str(pbf), locations=True)

    top_types = [
        {
            "highway": t,
            "way_count": c,
            "length_km": round(sc.road_length_by_type_km.get(t, 0.0), 3),
        }
        for t, c in sc.road_count_by_type.most_common(15)
    ]

    return {
        "pbf_file": str(pbf),
        "relation": {
            "id": rf.relation_id,
            "name": rf.relation_tags.get("name"),
            "name_en": rf.relation_tags.get("name:en"),
            "admin_level": rf.relation_tags.get("admin_level"),
            "boundary": rf.relation_tags.get("boundary"),
        },
        "bbox": {
            "min_lat": round(bbox.min_lat, 6),
            "min_lon": round(bbox.min_lon, 6),
            "max_lat": round(bbox.max_lat, 6),
            "max_lon": round(bbox.max_lon, 6),
        },
        "boundary_nodes": {
            "way_count": len(rf.member_way_ids),
            "node_count": len(wc.node_ids),
            "node_found_in_file": nc.found_nodes,
        },
        "stats": {
            "total_nodes_in_bbox": sc.total_nodes_in_bbox,
            "total_ways_intersect_bbox": sc.total_ways_intersect_bbox,
            "road_way_count": sc.road_way_count,
            "road_node_count_in_bbox": len(sc.road_node_ids_in_bbox),
            "road_edge_count_approx": sc.road_edge_count_approx,
            "road_total_length_km_approx": round(sc.road_total_length_km, 3),
            "charging_station_node_count": sc.charging_station_node_count,
            "charging_station_way_count": sc.charging_station_way_count,
        },
        "road_count_by_type_all": dict(sc.road_count_by_type),
        "road_length_by_type_km_all": {
            k: round(v, 3) for k, v in sc.road_length_by_type_km.items()
        },
        "top_road_types": top_types,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", default="Map Resource/guangdong-260309.osm.pbf")
    parser.add_argument("--out", default="Map Resource/analysis/panyu_initial_stats.json")
    args = parser.parse_args()

    result = run_analysis(Path(args.pbf))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
