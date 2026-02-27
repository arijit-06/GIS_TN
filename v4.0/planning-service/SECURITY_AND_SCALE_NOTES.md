# Security and Scale Notes

## Input validation
- Latitude/longitude are range-validated (`[-90, 90]`, `[-180, 180]`).
- Batch coordinate list is bounded by `MAX_BATCH_COORDINATES` (default 50,000).
- Optional input ID is length-limited.

## SQL injection safety
- All user input is passed via query parameters.
- Dynamic pgRouting edge SQL is generated server-side with PostgreSQL `format(... %L ...)`, which safely quotes `franchise_id`.
- No string concatenation from raw external values is used in Python SQL text.

## Error exposure
- Client-facing responses are standardized and sanitized (`code` + user-safe `message`).
- Unhandled exceptions are masked as `internal_error`.
- `x-request-id` is returned for support/debug correlation.

## Rate limiting and payload abuse protection
- Per-IP request throttling via in-memory window limiter.
- Payload size guard via `Content-Length` cap and 413 response.
- Batch geometry output disabled by default to prevent oversized response memory usage.

## Batch architecture (50k target)
- API accepts one JSON file payload as `coordinates`.
- Processing is chunked (`BATCH_CHUNK_SIZE`, default 1000) to limit in-memory SQL payload size.
- Each chunk executes set-based SQL:
  1. point-in-polygon franchise resolve
  2. nearest fiber node
  3. nearest source/target road nodes
  4. `pgr_dijkstraCost` per unique (franchise, source, target) pair
- Results are joined back to each input row with per-row status.

## Scalability guidance
- In-memory rate limiting is per-process only. For multi-instance deployment, replace with Redis-backed limiter.
- For very large throughput, consider async job mode:
  - accept file
  - enqueue batch task
  - poll results
- Add DB connection pooling (e.g., psycopg pool) and tune chunk size based on DB CPU.
