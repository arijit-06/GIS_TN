import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import MultiPoint, Point, shape
from shapely.ops import unary_union, voronoi_diagram


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "planning-service" / "data"

DISTRICTS_SRC = ROOT / "Districts_new.geojson"
FRANCHISE_POINTS_SRC = ROOT / "Franchise_new.geojson"
FIBER_NODES_SRC = DATA_DIR / "infra_nodes.geojson"
ROADS_SRC = ROOT / "roads_new.geojson"

DISTRICTS_OUT = DATA_DIR / "districts.geojson"
FRANCHISE_ZONES_OUT = DATA_DIR / "franchise_zones.geojson"
FIBER_NODES_OUT = DATA_DIR / "fiber_nodes.geojson"
ROADS_OUT = DATA_DIR / "roads.geojson"


def read_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_geojson(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_districts(src: dict) -> dict:
    features = []
    for feat in src.get("features", []):
        props = feat.get("properties", {})
        district_id = props.get("district_id") or props.get("GID_2") or props.get("id")
        name = props.get("name") or props.get("NAME_2") or district_id
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "district_id": district_id,
                    "name": name,
                },
                "geometry": feat.get("geometry"),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def normalize_fiber_nodes(src: dict) -> dict:
    features = []
    for feat in src.get("features", []):
        props = feat.get("properties", {})
        node_id = props.get("node_id") or props.get("id") or props.get("infra_id")
        franchise_id = props.get("franchise_id")
        if not node_id or not franchise_id:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "node_id": node_id,
                    "franchise_id": franchise_id,
                    "capacity": props.get("capacity", 1000),
                    "status": props.get("status", "active"),
                },
                "geometry": feat.get("geometry"),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def build_franchise_zones(districts: dict, franchise_points: dict, fiber_nodes: dict) -> dict:
    district_geoms = {}
    for feat in districts.get("features", []):
        district_id = feat.get("properties", {}).get("district_id")
        if not district_id:
            continue
        district_geoms[district_id] = shape(feat.get("geometry"))

    district_points = defaultdict(list)
    for feat in franchise_points.get("features", []):
        props = feat.get("properties", {})
        district_id = props.get("district_id") or props.get("GID_2")
        if district_id not in district_geoms:
            continue
        coords = feat.get("geometry", {}).get("coordinates", [])
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        point = Point(coords[0], coords[1])
        # Keep franchise ids aligned with infra file (FRA_001..).
        # If missing, synthesize stable ID from rand_point_id.
        idx = props.get("rand_point_id")
        franchise_id = props.get("franchise_id")
        if not franchise_id:
            if isinstance(idx, int):
                franchise_id = f"FRA_{idx + 1:03d}"
            else:
                franchise_id = f"FRA_{len(district_points[district_id]) + 1:03d}"
        district_points[district_id].append((franchise_id, point))

    assigned = defaultdict(list)
    for feat in fiber_nodes.get("features", []):
        props = feat.get("properties", {})
        fid = props.get("franchise_id")
        nid = props.get("node_id")
        if fid and nid:
            assigned[fid].append(nid)

    out_features = []

    for district_id, dgeom in district_geoms.items():
        points = district_points.get(district_id, [])
        if not points:
            continue

        if len(points) == 1:
            fid, _ = points[0]
            poly = dgeom
            if poly.is_empty:
                continue
            out_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "franchise_id": fid,
                        "district_id": district_id,
                        "assigned_node_ids": sorted(assigned.get(fid, [])),
                    },
                    "geometry": json.loads(json.dumps(poly.__geo_interface__)),
                }
            )
            continue

        multi = MultiPoint([p for _, p in points])
        vor = voronoi_diagram(multi, envelope=dgeom.envelope, edges=False)
        cells = [g for g in vor.geoms if not g.is_empty]

        used = set()
        for fid, pt in points:
            # choose the cell that contains the point; fallback to nearest by centroid.
            cell = next((c for c in cells if c.contains(pt) or c.touches(pt)), None)
            if cell is None:
                cell = min(cells, key=lambda c: c.centroid.distance(pt))

            clipped = cell.intersection(dgeom)
            if clipped.is_empty:
                continue

            # Avoid duplicate assignment of identical geometry object.
            key = clipped.wkt
            if key in used:
                continue
            used.add(key)

            out_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "franchise_id": fid,
                        "district_id": district_id,
                        "assigned_node_ids": sorted(assigned.get(fid, [])),
                    },
                    "geometry": json.loads(json.dumps(clipped.__geo_interface__)),
                }
            )

    return {"type": "FeatureCollection", "features": out_features}


def normalize_roads(src: dict) -> dict:
    # Keep as-is; ingestion now supports LineString and MultiLineString.
    clean_features = []
    for feat in src.get("features", []):
        geom = feat.get("geometry", {})
        if geom.get("type") not in {"LineString", "MultiLineString"}:
            continue
        clean_features.append(
            {
                "type": "Feature",
                "properties": feat.get("properties", {}),
                "geometry": geom,
            }
        )
    return {"type": "FeatureCollection", "features": clean_features}


def main() -> None:
    districts_raw = read_geojson(DISTRICTS_SRC)
    franchise_points_raw = read_geojson(FRANCHISE_POINTS_SRC)
    fiber_nodes_raw = read_geojson(FIBER_NODES_SRC)
    roads_raw = read_geojson(ROADS_SRC)

    districts = normalize_districts(districts_raw)
    fiber_nodes = normalize_fiber_nodes(fiber_nodes_raw)
    franchise_zones = build_franchise_zones(districts, franchise_points_raw, fiber_nodes)
    roads = normalize_roads(roads_raw)

    write_geojson(DISTRICTS_OUT, districts)
    write_geojson(FIBER_NODES_OUT, fiber_nodes)
    write_geojson(FRANCHISE_ZONES_OUT, franchise_zones)
    write_geojson(ROADS_OUT, roads)

    print(f"Wrote {DISTRICTS_OUT} ({len(districts['features'])} features)")
    print(f"Wrote {FIBER_NODES_OUT} ({len(fiber_nodes['features'])} features)")
    print(f"Wrote {FRANCHISE_ZONES_OUT} ({len(franchise_zones['features'])} features)")
    print(f"Wrote {ROADS_OUT} ({len(roads['features'])} features)")


if __name__ == "__main__":
    main()
