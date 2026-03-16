from __future__ import annotations

import argparse
import math
from pathlib import Path

import osmium

TARGET_NAMES = {"番禺区", "Panyu District"}


class RelationFinder(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.relation_id: int | None = None
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
        for m in r.members:
            if m.type == "w":
                self.way_ids.add(m.ref)


class BoundaryWayNodeRefCollector(osmium.SimpleHandler):
    def __init__(self, way_ids: set[int]) -> None:
        super().__init__()
        self.way_ids = way_ids
        self.node_ids: set[int] = set()

    def way(self, w: osmium.osm.Way) -> None:
        if w.id not in self.way_ids:
            return
        for n in w.nodes:
            self.node_ids.add(n.ref)


class BoundaryNodeBoundsCollector(osmium.SimpleHandler):
    def __init__(self, node_ids: set[int]) -> None:
        super().__init__()
        self.node_ids = node_ids
        self.min_lat = float("inf")
        self.min_lon = float("inf")
        self.max_lat = float("-inf")
        self.max_lon = float("-inf")

    def node(self, n: osmium.osm.Node) -> None:
        if n.id not in self.node_ids:
            return
        if not n.location.valid():
            return
        lat = n.location.lat
        lon = n.location.lon
        self.min_lat = min(self.min_lat, lat)
        self.min_lon = min(self.min_lon, lon)
        self.max_lat = max(self.max_lat, lat)
        self.max_lon = max(self.max_lon, lon)


class EntityCollector(osmium.SimpleHandler):
    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        super().__init__()
        self.min_lat, self.min_lon, self.max_lat, self.max_lon = bbox

        self.node_ids: set[int] = set()
        self.way_ids: set[int] = set()
        self.relation_ids: set[int] = set()

    def _in_bbox(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon

    def node(self, n: osmium.osm.Node) -> None:
        if not n.location.valid():
            return
        if self._in_bbox(n.location.lat, n.location.lon):
            self.node_ids.add(n.id)

    def way(self, w: osmium.osm.Way) -> None:
        refs = []
        inside = False
        for n in w.nodes:
            refs.append(n.ref)
            if n.location.valid() and self._in_bbox(n.location.lat, n.location.lon):
                inside = True

        if inside:
            self.way_ids.add(w.id)
            for ref in refs:
                self.node_ids.add(ref)

    def relation(self, r: osmium.osm.Relation) -> None:
        for m in r.members:
            if m.type == "w" and m.ref in self.way_ids:
                self.relation_ids.add(r.id)
                return
            if m.type == "n" and m.ref in self.node_ids:
                self.relation_ids.add(r.id)
                return


class EntityWriter(osmium.SimpleHandler):
    def __init__(
        self,
        out_path: Path,
        node_ids: set[int],
        way_ids: set[int],
        relation_ids: set[int],
    ) -> None:
        super().__init__()
        self.writer = osmium.SimpleWriter(str(out_path))
        self.node_ids = node_ids
        self.way_ids = way_ids
        self.relation_ids = relation_ids

    def node(self, n: osmium.osm.Node) -> None:
        if n.id in self.node_ids:
            self.writer.add_node(n)

    def way(self, w: osmium.osm.Way) -> None:
        if w.id in self.way_ids:
            self.writer.add_way(w)

    def relation(self, r: osmium.osm.Relation) -> None:
        if r.id in self.relation_ids:
            self.writer.add_relation(r)

    def close(self) -> None:
        self.writer.close()


def extract_panyu(src_pbf: Path, out_pbf: Path) -> dict:
    rf = RelationFinder()
    rf.apply_file(str(src_pbf), locations=False)
    if rf.relation_id is None:
        raise RuntimeError("番禺行政区 relation 未找到")

    wr = BoundaryWayNodeRefCollector(rf.way_ids)
    wr.apply_file(str(src_pbf), locations=False)
    nb = BoundaryNodeBoundsCollector(wr.node_ids)
    nb.apply_file(str(src_pbf), locations=False)
    bbox = (nb.min_lat, nb.min_lon, nb.max_lat, nb.max_lon)
    if any(math.isinf(v) for v in bbox):
        raise RuntimeError("Panyu bbox calculation failed")

    collector = EntityCollector(bbox)
    collector.apply_file(str(src_pbf), locations=True)

    # Ensure Panyu relation is included.
    collector.relation_ids.add(rf.relation_id)

    out_pbf.parent.mkdir(parents=True, exist_ok=True)
    writer = EntityWriter(out_pbf, collector.node_ids, collector.way_ids, collector.relation_ids)
    writer.apply_file(str(src_pbf), locations=True)
    writer.close()

    return {
        "source": str(src_pbf),
        "output": str(out_pbf),
        "panyu_relation_id": rf.relation_id,
        "bbox": {
            "min_lat": round(bbox[0], 6),
            "min_lon": round(bbox[1], 6),
            "max_lat": round(bbox[2], 6),
            "max_lon": round(bbox[3], 6),
        },
        "counts": {
            "nodes": len(collector.node_ids),
            "ways": len(collector.way_ids),
            "relations": len(collector.relation_ids),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Panyu subset from Guangdong OSM PBF")
    parser.add_argument("--src", default="Map Resource/guangdong-260309.osm.pbf")
    parser.add_argument("--out", default="Map Resource/panyu.osm.pbf")
    args = parser.parse_args()

    src_path = Path(args.src)
    if not src_path.exists():
        raise FileNotFoundError(
            f"Source PBF not found: {src_path}\n"
            "当前仓库默认不再保留广东全量包，请自行提供 --src，"
            "或直接使用现有 Map Resource/panyu.osm.pbf。"
        )

    summary = extract_panyu(src_path, Path(args.out))
    print(summary)


if __name__ == "__main__":
    main()
