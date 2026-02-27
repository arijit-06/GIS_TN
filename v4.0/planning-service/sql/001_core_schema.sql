CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE TABLE IF NOT EXISTS districts (
    district_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS franchise_zones (
    franchise_id TEXT PRIMARY KEY,
    district_id TEXT NOT NULL REFERENCES districts(district_id) ON DELETE CASCADE,
    assigned_node_ids TEXT[] DEFAULT '{}',
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS fiber_nodes (
    node_id TEXT PRIMARY KEY,
    franchise_id TEXT NOT NULL REFERENCES franchise_zones(franchise_id) ON DELETE CASCADE,
    capacity NUMERIC,
    status TEXT DEFAULT 'active',
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS road_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    source BIGINT,
    target BIGINT,
    length_m DOUBLE PRECISION NOT NULL,
    cost DOUBLE PRECISION NOT NULL,
    franchise_id TEXT NOT NULL REFERENCES franchise_zones(franchise_id) ON DELETE CASCADE,
    geom geometry(LineString, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS road_nodes (
    node_id BIGINT NOT NULL,
    franchise_id TEXT NOT NULL REFERENCES franchise_zones(franchise_id) ON DELETE CASCADE,
    geom geometry(Point, 4326) NOT NULL,
    PRIMARY KEY (node_id, franchise_id)
);

CREATE INDEX IF NOT EXISTS idx_districts_geom ON districts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_franchise_geom ON franchise_zones USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_fiber_nodes_geom ON fiber_nodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_road_edges_geom ON road_edges USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_road_nodes_geom ON road_nodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_road_edges_franchise ON road_edges (franchise_id);
CREATE INDEX IF NOT EXISTS idx_road_nodes_franchise ON road_nodes (franchise_id);
