# Tamil Nadu Planning Service

PostGIS + pgRouting backend for franchise-constrained fiber routing.

## 1) Start database

```bash
docker compose up -d
```

The DB runs at `localhost:5432` with default credentials from `docker-compose.yml`.

## 2) Install API dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3) Configure environment

Copy `.env.example` to `.env` and update values as needed.

## 4) Load and preprocess data (when datasets are ready)

Run once whenever you update datasets:

```bash
python scripts/preprocess_and_load.py ^
  --districts path\to\districts.geojson ^
  --franchises path\to\franchise_zones.geojson ^
  --fiber-nodes path\to\fiber_nodes.geojson ^
  --roads path\to\roads.geojson
```

This command:
- creates schema + spatial indexes
- loads districts, franchise zones, fiber nodes
- clips roads per franchise boundary
- builds `source/target` topology via pgRouting
- populates `road_nodes` for fast snap queries

## 5) Start API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Key endpoints

- `GET /health`
- `GET /catalog/summary`
- `GET /catalog/districts`
- `GET /catalog/franchises?district_id=<id>`
- `POST /routing/compute`
- `POST /routing/compute-batch`

`/routing/compute` request body:

```json
{
  "latitude": 12.9123,
  "longitude": 80.2111
}
```

The service resolves:
1. franchise via point-in-polygon
2. nearest fiber node in that franchise
3. nearest road graph node for consumer and selected fiber node
4. shortest path on franchise-scoped edges with pgRouting

Returns route geometry, distance, estimated cost, and ownership metadata.

## Bulk JSON API (up to 50,000 coordinates)

`POST /routing/compute-batch`

```json
{
  "include_geometry": false,
  "coordinates": [
    { "id": "row-1", "latitude": 12.9123, "longitude": 80.2111 },
    { "id": "row-2", "latitude": 12.9555, "longitude": 80.1432 }
  ]
}
```

Response shape:

```json
{
  "total": 2,
  "success_count": 2,
  "failed_count": 0,
  "results": [
    {
      "input_index": 0,
      "input_id": "row-1",
      "latitude": 12.9123,
      "longitude": 80.2111,
      "status": "ok",
      "franchise_id": "FRA_01",
      "nearest_node_id": "NODE_91",
      "source_road_node_id": 12345,
      "target_road_node_id": 99123,
      "distance_meters": 3811.2,
      "estimated_cost": 2667840.0,
      "error_code": null
    }
  ]
}
```

Notes:
- `include_geometry` is currently blocked for batch mode to protect memory and response size.
- Batch execution is chunked (`BATCH_CHUNK_SIZE`) and resolved with set-based SQL per chunk.
- Distance uses pgRouting (`pgr_dijkstraCost`) on franchise-constrained road subgraphs.

## Security controls in place

- Request payload size cap (`MAX_REQUEST_BODY_BYTES`) with 413 rejection.
- Per-IP in-memory rate limiting (`RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_REQUESTS_PER_WINDOW`).
- Strong Pydantic validation for coordinate ranges and max array length.
- Structured JSON logging with request ID propagation (`x-request-id`).
- Sanitized errors: no stack trace or raw SQL details returned to clients.
