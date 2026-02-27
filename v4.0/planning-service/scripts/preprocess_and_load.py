import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import psycopg

from app.config import settings


def load_geojson(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_features(geojson: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    features = geojson.get("features", [])
    for feature in features:
        if feature and feature.get("geometry"):
            yield feature


def run_schema(conn: psycopg.Connection, schema_path: Path) -> None:
    sql_text = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()


def load_districts(conn: psycopg.Connection, districts_geojson: Path) -> None:
    payload = load_geojson(districts_geojson)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE districts CASCADE")
        for feature in iter_features(payload):
            props = feature.get("properties", {})
            district_id = props.get("district_id") or props.get("id") or props.get("name")
            name = props.get("name") or district_id
            geom = json.dumps(feature["geometry"])
            cur.execute(
                """
                INSERT INTO districts (district_id, name, geom)
                VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                """,
                (district_id, name, geom),
            )
    conn.commit()


def load_franchises(conn: psycopg.Connection, franchises_geojson: Path) -> None:
    payload = load_geojson(franchises_geojson)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE franchise_zones CASCADE")
        for feature in iter_features(payload):
            props = feature.get("properties", {})
            franchise_id = props.get("franchise_id") or props.get("id")
            district_id = props.get("district_id")
            if not franchise_id or not district_id:
                raise ValueError("Each franchise feature needs franchise_id and district_id.")
            assigned_node_ids = props.get("assigned_node_ids", [])
            if not isinstance(assigned_node_ids, list):
                assigned_node_ids = []
            geom = json.dumps(feature["geometry"])
            cur.execute(
                """
                INSERT INTO franchise_zones (franchise_id, district_id, assigned_node_ids, geom)
                VALUES (
                    %s,
                    %s,
                    %s,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                            3
                        )
                    )
                )
                """,
                (franchise_id, district_id, assigned_node_ids, geom),
            )
    conn.commit()


def load_fiber_nodes(conn: psycopg.Connection, nodes_geojson: Path) -> None:
    payload = load_geojson(nodes_geojson)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE fiber_nodes CASCADE")
        for feature in iter_features(payload):
            props = feature.get("properties", {})
            node_id = props.get("node_id") or props.get("id")
            franchise_id = props.get("franchise_id")
            if not node_id or not franchise_id:
                raise ValueError("Each fiber node feature needs node_id and franchise_id.")
            capacity = props.get("capacity")
            status = props.get("status", "active")
            geom = json.dumps(feature["geometry"])
            cur.execute(
                """
                INSERT INTO fiber_nodes (node_id, franchise_id, capacity, status, geom)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """,
                (node_id, franchise_id, capacity, status, geom),
            )
    conn.commit()


def load_and_clip_roads(conn: psycopg.Connection, roads_geojson: Path) -> None:
    payload = load_geojson(roads_geojson)
    with conn.cursor() as cur:
        cur.execute(
            """
            DROP TABLE IF EXISTS _road_edges_raw;
            CREATE TEMP TABLE _road_edges_raw (
                geom geometry(Geometry, 4326)
            ) ON COMMIT DROP;
            """
        )
        for feature in iter_features(payload):
            geom = json.dumps(feature["geometry"])
            cur.execute(
                """
                INSERT INTO _road_edges_raw (geom)
                VALUES (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """,
                (geom,),
            )

        cur.execute("TRUNCATE road_edges CASCADE")
        cur.execute(
            """
            INSERT INTO road_edges (source, target, length_m, cost, franchise_id, geom)
            SELECT
                NULL::bigint AS source,
                NULL::bigint AS target,
                ST_Length(clipped.geom::geography) AS length_m,
                ST_Length(clipped.geom::geography) AS cost,
                f.franchise_id,
                clipped.geom
            FROM franchise_zones f
            JOIN _road_edges_raw r ON ST_Intersects(r.geom, f.geom)
            CROSS JOIN LATERAL (
                SELECT (
                    ST_Dump(
                        ST_CollectionExtract(
                            ST_Intersection(
                                ST_CollectionExtract(r.geom, 2),
                                f.geom
                            ),
                            2
                        )
                    )
                ).geom::geometry(LineString, 4326) AS geom
            ) AS clipped
            WHERE ST_Length(clipped.geom::geography) > 0.5
            """
        )
    conn.commit()


def build_topology(conn: psycopg.Connection, tolerance: float) -> None:
    with conn.cursor() as cur:
        # pgRouting 4.x no longer exposes pgr_createTopology.
        # Build graph topology by snapping edge endpoints to a tolerance grid,
        # creating unique vertex ids, and backfilling source/target.
        cur.execute("DROP TABLE IF EXISTS _vertices")
        cur.execute(
            """
            CREATE TEMP TABLE _vertices AS
            SELECT
                ROW_NUMBER() OVER (ORDER BY ST_AsBinary(geom))::bigint AS node_id,
                geom
            FROM (
                SELECT DISTINCT ST_SnapToGrid(ST_StartPoint(geom), %s) AS geom
                FROM road_edges
                UNION
                SELECT DISTINCT ST_SnapToGrid(ST_EndPoint(geom), %s) AS geom
                FROM road_edges
            ) v
            """,
            (tolerance, tolerance),
        )
        cur.execute("CREATE INDEX ON _vertices USING GIST (geom)")
        cur.execute(
            """
            UPDATE road_edges e
            SET source = v.node_id
            FROM _vertices v
            WHERE ST_SnapToGrid(ST_StartPoint(e.geom), %s) = v.geom
            """,
            (tolerance,),
        )
        cur.execute(
            """
            UPDATE road_edges e
            SET target = v.node_id
            FROM _vertices v
            WHERE ST_SnapToGrid(ST_EndPoint(e.geom), %s) = v.geom
            """,
            (tolerance,),
        )
        cur.execute("TRUNCATE road_nodes")
        cur.execute(
            """
            INSERT INTO road_nodes (node_id, franchise_id, geom)
            SELECT DISTINCT e.source AS node_id, e.franchise_id, v.geom::geometry(Point, 4326) AS geom
            FROM road_edges e
            JOIN _vertices v ON v.node_id = e.source
            WHERE e.source IS NOT NULL
            UNION
            SELECT DISTINCT e.target AS node_id, e.franchise_id, v.geom::geometry(Point, 4326) AS geom
            FROM road_edges e
            JOIN _vertices v ON v.node_id = e.target
            WHERE e.target IS NOT NULL
            """
        )
    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load and preprocess Tamil Nadu planning data into PostGIS.")
    parser.add_argument("--districts", required=True, help="Path to districts GeoJSON")
    parser.add_argument("--franchises", required=True, help="Path to franchise zones GeoJSON")
    parser.add_argument("--fiber-nodes", required=True, help="Path to fiber nodes GeoJSON")
    parser.add_argument("--roads", required=True, help="Path to roads GeoJSON")
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).resolve().parents[1] / "sql" / "001_core_schema.sql"),
        help="Path to schema SQL file",
    )
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--topology-tolerance",
        default=settings.pgrouting_tolerance_degrees,
        type=float,
        help="Tolerance used by pgr_createTopology in degrees",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    schema_path = Path(args.schema)
    districts_path = Path(args.districts)
    franchises_path = Path(args.franchises)
    fiber_nodes_path = Path(args.fiber_nodes)
    roads_path = Path(args.roads)

    with psycopg.connect(args.database_url) as conn:
        run_schema(conn, schema_path)
        load_districts(conn, districts_path)
        load_franchises(conn, franchises_path)
        load_fiber_nodes(conn, fiber_nodes_path)
        load_and_clip_roads(conn, roads_path)
        build_topology(conn, args.topology_tolerance)

    print("Data load and preprocessing completed.")


if __name__ == "__main__":
    main()
