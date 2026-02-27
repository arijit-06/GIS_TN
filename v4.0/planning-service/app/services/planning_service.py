import json
from typing import Dict, List, Optional

from psycopg import Connection

from app.config import settings
from app.errors import AppError


class PlanningService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def health(self) -> Dict[str, bool]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            db_ok = cur.fetchone()["ok"] == 1

            cur.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis') AS ok")
            postgis_ok = bool(cur.fetchone()["ok"])

            cur.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pgrouting') AS ok")
            pgrouting_ok = bool(cur.fetchone()["ok"])

        return {
            "db_ok": db_ok,
            "postgis_ok": postgis_ok,
            "pgrouting_ok": pgrouting_ok,
        }

    def system_summary(self) -> Dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM districts) AS district_count,
                    (SELECT COUNT(*) FROM franchise_zones) AS franchise_count,
                    (SELECT COUNT(*) FROM fiber_nodes) AS fiber_node_count,
                    (SELECT COUNT(*) FROM road_edges) AS road_edge_count,
                    (SELECT COUNT(*) FROM road_nodes) AS road_node_count
                """
            )
            row = cur.fetchone()
        return row

    def list_districts(self) -> List[Dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.district_id,
                    d.name,
                    COUNT(f.franchise_id)::int AS franchise_count
                FROM districts d
                LEFT JOIN franchise_zones f ON d.district_id = f.district_id
                GROUP BY d.district_id, d.name
                ORDER BY d.name
                """
            )
            return cur.fetchall()

    def list_franchises(self, district_id: Optional[str]) -> List[Dict]:
        with self.conn.cursor() as cur:
            if district_id:
                cur.execute(
                    """
                    SELECT
                        f.franchise_id,
                        f.district_id,
                        COUNT(n.node_id)::int AS node_count
                    FROM franchise_zones f
                    LEFT JOIN fiber_nodes n ON n.franchise_id = f.franchise_id
                    WHERE f.district_id = %s
                    GROUP BY f.franchise_id, f.district_id
                    ORDER BY f.franchise_id
                    """,
                    (district_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        f.franchise_id,
                        f.district_id,
                        COUNT(n.node_id)::int AS node_count
                    FROM franchise_zones f
                    LEFT JOIN fiber_nodes n ON n.franchise_id = f.franchise_id
                    GROUP BY f.franchise_id, f.district_id
                    ORDER BY f.franchise_id
                    """
                )
            return cur.fetchall()

    def resolve_franchise(self, longitude: float, latitude: float) -> Optional[str]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH consumer AS (
                    SELECT ST_SetSRID(ST_Point(%s, %s), 4326) AS geom
                )
                SELECT f.franchise_id
                FROM franchise_zones f
                CROSS JOIN consumer c
                WHERE ST_Contains(f.geom, c.geom)
                LIMIT 1
                """,
                (longitude, latitude),
            )
            row = cur.fetchone()
        return row["franchise_id"] if row else None

    def nearest_fiber_node(self, franchise_id: str, longitude: float, latitude: float) -> Optional[Dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH consumer AS (
                    SELECT ST_SetSRID(ST_Point(%s, %s), 4326) AS geom
                )
                SELECT
                    fn.node_id,
                    ST_Distance(fn.geom::geography, c.geom::geography) AS distance_meters
                FROM fiber_nodes fn
                CROSS JOIN consumer c
                WHERE fn.franchise_id = %s
                ORDER BY fn.geom <-> c.geom
                LIMIT 1
                """,
                (longitude, latitude, franchise_id),
            )
            return cur.fetchone()

    def nearest_road_node(self, franchise_id: str, longitude: float, latitude: float) -> Optional[int]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH p AS (
                    SELECT ST_SetSRID(ST_Point(%s, %s), 4326) AS geom
                )
                SELECT rn.node_id
                FROM road_nodes rn
                CROSS JOIN p
                WHERE rn.franchise_id = %s
                ORDER BY rn.geom <-> p.geom
                LIMIT 1
                """,
                (longitude, latitude, franchise_id),
            )
            row = cur.fetchone()
        return row["node_id"] if row else None

    def fiber_node_coordinates(self, node_id: str) -> Optional[Dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ST_X(geom) AS longitude,
                    ST_Y(geom) AS latitude
                FROM fiber_nodes
                WHERE node_id = %s
                LIMIT 1
                """,
                (node_id,),
            )
            return cur.fetchone()

    def road_node_coordinates(self, franchise_id: str, node_id: int) -> Optional[Dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT ST_X(geom) AS longitude, ST_Y(geom) AS latitude
                FROM road_nodes
                WHERE franchise_id = %s AND node_id = %s
                LIMIT 1
                """,
                (franchise_id, node_id),
            )
            return cur.fetchone()

    def compute_route(self, longitude: float, latitude: float) -> Dict:
        franchise_id = self.resolve_franchise(longitude, latitude)
        if not franchise_id:
            raise AppError("outside_franchise", "Consumer point is outside configured franchise zones.", 400)

        nearest_node = self.nearest_fiber_node(franchise_id, longitude, latitude)
        if not nearest_node:
            raise AppError("no_fiber_node", "No fiber nodes available in resolved franchise.", 400)

        fiber_coords = self.fiber_node_coordinates(nearest_node["node_id"])
        if not fiber_coords:
            raise AppError("fiber_node_geometry_missing", "Nearest fiber node geometry could not be resolved.", 500)

        source_road_node = self.nearest_road_node(franchise_id, longitude, latitude)
        target_road_node = self.nearest_road_node(franchise_id, fiber_coords["longitude"], fiber_coords["latitude"])
        if source_road_node is None or target_road_node is None:
            raise AppError("road_snap_failed", "Road-node snapping failed for franchise subgraph.", 400)

        if source_road_node == target_road_node:
            rn = self.road_node_coordinates(franchise_id, source_road_node)
            if not rn:
                raise AppError("road_snap_failed", "Road-node snapping failed for franchise subgraph.", 400)
            line = {
                "type": "LineString",
                "coordinates": [[rn["longitude"], rn["latitude"]], [rn["longitude"], rn["latitude"]]],
            }
            return {
                "franchise_id": franchise_id,
                "nearest_node_id": nearest_node["node_id"],
                "source_road_node_id": source_road_node,
                "target_road_node_id": target_road_node,
                "distance_meters": 0.0,
                "estimated_cost": 0.0,
                "edge_count": 0,
                "route_geojson": line,
            }

        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH route AS (
                    SELECT *
                    FROM pgr_dijkstra(
                        format(
                            'SELECT edge_id AS id, source, target, cost FROM road_edges WHERE franchise_id = %%L',
                            %s::text
                        ),
                        %s,
                        %s,
                        directed := false
                    )
                )
                SELECT
                    COALESCE(SUM(e.length_m), 0) AS distance_meters,
                    COALESCE(SUM(e.cost), 0) AS deployment_cost,
                    COUNT(*)::int AS edge_count,
                    ST_AsGeoJSON(ST_LineMerge(ST_Collect(e.geom))) AS route_geojson
                FROM route r
                JOIN road_edges e ON e.edge_id = r.edge
                WHERE r.edge <> -1
                """,
                (franchise_id, source_road_node, target_road_node),
            )
            route_row = cur.fetchone()

        if not route_row or route_row["edge_count"] == 0 or not route_row["route_geojson"]:
            raise AppError("route_not_found", "No route could be computed inside the franchise road subgraph.", 400)

        return {
            "franchise_id": franchise_id,
            "nearest_node_id": nearest_node["node_id"],
            "source_road_node_id": source_road_node,
            "target_road_node_id": target_road_node,
            "distance_meters": float(route_row["distance_meters"]),
            "estimated_cost": float(route_row["deployment_cost"] or (route_row["distance_meters"] * settings.default_cost_per_meter)),
            "edge_count": route_row["edge_count"],
            "route_geojson": json.loads(route_row["route_geojson"]),
        }

    def _resolve_chunk(self, points_chunk: List[Dict]) -> List[Dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH input_points AS (
                    SELECT *
                    FROM jsonb_to_recordset(%s::jsonb)
                    AS t(input_index int, input_id text, latitude double precision, longitude double precision)
                ),
                points AS (
                    SELECT
                        input_index,
                        input_id,
                        latitude,
                        longitude,
                        ST_SetSRID(ST_Point(longitude, latitude), 4326) AS geom
                    FROM input_points
                ),
                franchise_match AS (
                    SELECT
                        p.*,
                        f.franchise_id
                    FROM points p
                    LEFT JOIN LATERAL (
                        SELECT franchise_id
                        FROM franchise_zones
                        WHERE ST_Contains(geom, p.geom)
                        LIMIT 1
                    ) f ON TRUE
                ),
                fiber_match AS (
                    SELECT
                        fm.*,
                        fn.node_id AS nearest_node_id,
                        fn.geom AS nearest_node_geom
                    FROM franchise_match fm
                    LEFT JOIN LATERAL (
                        SELECT node_id, geom
                        FROM fiber_nodes
                        WHERE franchise_id = fm.franchise_id
                        ORDER BY geom <-> fm.geom
                        LIMIT 1
                    ) fn ON fm.franchise_id IS NOT NULL
                ),
                snap_match AS (
                    SELECT
                        fb.*,
                        src.node_id AS source_road_node_id,
                        tgt.node_id AS target_road_node_id
                    FROM fiber_match fb
                    LEFT JOIN LATERAL (
                        SELECT node_id
                        FROM road_nodes rn
                        WHERE rn.franchise_id = fb.franchise_id
                        ORDER BY rn.geom <-> fb.geom
                        LIMIT 1
                    ) src ON fb.franchise_id IS NOT NULL
                    LEFT JOIN LATERAL (
                        SELECT node_id
                        FROM road_nodes rn
                        WHERE rn.franchise_id = fb.franchise_id
                        ORDER BY rn.geom <-> fb.nearest_node_geom
                        LIMIT 1
                    ) tgt ON fb.franchise_id IS NOT NULL AND fb.nearest_node_id IS NOT NULL
                ),
                valid_pairs AS (
                    SELECT DISTINCT
                        franchise_id,
                        source_road_node_id,
                        target_road_node_id
                    FROM snap_match
                    WHERE franchise_id IS NOT NULL
                      AND nearest_node_id IS NOT NULL
                      AND source_road_node_id IS NOT NULL
                      AND target_road_node_id IS NOT NULL
                ),
                pair_costs AS (
                    SELECT
                        vp.franchise_id,
                        vp.source_road_node_id,
                        vp.target_road_node_id,
                        pc.agg_cost AS distance_meters
                    FROM valid_pairs vp
                    LEFT JOIN LATERAL (
                        SELECT agg_cost
                        FROM pgr_dijkstraCost(
                            format(
                                'SELECT edge_id AS id, source, target, cost FROM road_edges WHERE franchise_id = %%L',
                                vp.franchise_id::text
                            ),
                            vp.source_road_node_id,
                            vp.target_road_node_id,
                            directed := false
                        )
                        LIMIT 1
                    ) pc ON TRUE
                )
                SELECT
                    sm.input_index,
                    sm.input_id,
                    sm.latitude,
                    sm.longitude,
                    sm.franchise_id,
                    sm.nearest_node_id,
                    sm.source_road_node_id,
                    sm.target_road_node_id,
                    CASE
                        WHEN sm.source_road_node_id = sm.target_road_node_id THEN 0
                        ELSE pair_costs.distance_meters
                    END AS distance_meters,
                    CASE
                        WHEN sm.franchise_id IS NULL THEN 'outside_franchise'
                        WHEN sm.nearest_node_id IS NULL THEN 'no_fiber_node'
                        WHEN sm.source_road_node_id IS NULL OR sm.target_road_node_id IS NULL THEN 'road_snap_failed'
                        WHEN sm.source_road_node_id = sm.target_road_node_id THEN NULL
                        WHEN pair_costs.distance_meters IS NULL THEN 'route_not_found'
                        ELSE NULL
                    END AS error_code
                FROM snap_match sm
                LEFT JOIN pair_costs
                  ON pair_costs.franchise_id = sm.franchise_id
                 AND pair_costs.source_road_node_id = sm.source_road_node_id
                 AND pair_costs.target_road_node_id = sm.target_road_node_id
                ORDER BY sm.input_index
                """,
                (json.dumps(points_chunk),),
            )
            rows = cur.fetchall()
        return rows

    def compute_batch(self, coordinates: List[Dict], include_geometry: bool = False) -> Dict:
        if include_geometry:
            raise AppError("unsupported_option", "Geometry output is disabled for batch mode.", 400)

        all_rows: List[Dict] = []
        chunk_size = max(1, settings.batch_chunk_size)

        for start in range(0, len(coordinates), chunk_size):
            chunk = coordinates[start : start + chunk_size]
            chunk_payload = [
                {
                    "input_index": start + idx,
                    "input_id": item.get("id"),
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                }
                for idx, item in enumerate(chunk)
            ]
            all_rows.extend(self._resolve_chunk(chunk_payload))

        results = []
        success_count = 0

        for row in all_rows:
            if row["error_code"] is None:
                success_count += 1
                distance_meters = float(row["distance_meters"])
                results.append(
                    {
                        "input_index": row["input_index"],
                        "input_id": row["input_id"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "status": "ok",
                        "franchise_id": row["franchise_id"],
                        "nearest_node_id": row["nearest_node_id"],
                        "source_road_node_id": row["source_road_node_id"],
                        "target_road_node_id": row["target_road_node_id"],
                        "distance_meters": distance_meters,
                        "estimated_cost": round(distance_meters * settings.default_cost_per_meter, 2),
                        "edge_count": None,
                        "route_geojson": None,
                        "error_code": None,
                        "error_message": None,
                    }
                )
            else:
                results.append(
                    {
                        "input_index": row["input_index"],
                        "input_id": row["input_id"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "status": "error",
                        "franchise_id": row["franchise_id"],
                        "nearest_node_id": row["nearest_node_id"],
                        "source_road_node_id": row["source_road_node_id"],
                        "target_road_node_id": row["target_road_node_id"],
                        "distance_meters": None,
                        "estimated_cost": None,
                        "edge_count": None,
                        "route_geojson": None,
                        "error_code": row["error_code"],
                        "error_message": row["error_code"].replace("_", " "),
                    }
                )

        failed_count = len(results) - success_count
        return {
            "total": len(results),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }
