from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.db import get_db


CREATE_JOBS_SQL = """
CREATE TABLE IF NOT EXISTS batch_jobs (
    job_id UUID PRIMARY KEY,
    total_points INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    processed_chunks INTEGER DEFAULT 0,
    failed_chunks INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    error_message TEXT
);
"""

CREATE_CHUNK_RESULTS_SQL = """
CREATE TABLE IF NOT EXISTS batch_chunk_results (
    id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES batch_jobs(job_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    processed_points INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_ms INTEGER
);
"""

CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_batch_chunk_results_job_id ON batch_chunk_results(job_id);
"""


class JobRepository:
    def ensure_schema(self) -> None:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_JOBS_SQL)
                cur.execute(CREATE_CHUNK_RESULTS_SQL)
                cur.execute(CREATE_INDEXES_SQL)
            conn.commit()

    def create_job(self, job_id: str, total_points: int, total_chunks: int, status: str = "queued") -> None:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO batch_jobs (
                        job_id, total_points, total_chunks, processed_chunks, failed_chunks, status
                    )
                    VALUES (%s::uuid, %s, %s, 0, 0, %s)
                    """,
                    (job_id, total_points, total_chunks, status),
                )
            conn.commit()

    def update_job_status(
        self,
        job_id: str,
        status: str,
        started_at_now: bool = False,
        finished_at_now: bool = False,
        error_message: Optional[str] = None,
    ) -> None:
        set_parts = ["status = %s"]
        params: list[Any] = [status]
        if started_at_now:
            set_parts.append("started_at = NOW()")
        if finished_at_now:
            set_parts.append("finished_at = NOW()")
        if error_message is not None:
            set_parts.append("error_message = %s")
            params.append(error_message)

        params.append(job_id)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE batch_jobs SET {', '.join(set_parts)} WHERE job_id = %s::uuid",
                    tuple(params),
                )
            conn.commit()

    def persist_chunk_result(
        self,
        job_id: str,
        chunk_index: int,
        processed_points: int,
        status: str,
        error_message: Optional[str],
        duration_ms: int,
    ) -> None:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO batch_chunk_results (
                        job_id, chunk_index, processed_points, status, error_message, duration_ms
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s)
                    """,
                    (job_id, chunk_index, processed_points, status, error_message, duration_ms),
                )
                cur.execute(
                    """
                    UPDATE batch_jobs
                    SET
                        processed_chunks = processed_chunks + 1,
                        failed_chunks = failed_chunks + CASE WHEN %s = 'failed' THEN 1 ELSE 0 END
                    WHERE job_id = %s::uuid
                    """,
                    (status, job_id),
                )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        job_id::text AS job_id,
                        total_points,
                        total_chunks,
                        processed_chunks,
                        failed_chunks,
                        status,
                        EXTRACT(EPOCH FROM created_at) AS created_at,
                        EXTRACT(EPOCH FROM started_at) AS started_at,
                        EXTRACT(EPOCH FROM finished_at) AS finished_at,
                        error_message
                    FROM batch_jobs
                    WHERE job_id = %s::uuid
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
        return row

    def get_chunk_results(self, job_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        chunk_index,
                        processed_points,
                        status,
                        error_message,
                        duration_ms
                    FROM batch_chunk_results
                    WHERE job_id = %s::uuid
                    ORDER BY chunk_index
                    """,
                    (job_id,),
                )
                rows = cur.fetchall()
        return rows

    def active_job_count(self) -> int:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM batch_jobs WHERE status IN ('queued', 'processing')")
                row = cur.fetchone()
        return int(row["c"])

    def mark_incomplete_jobs_failed(self) -> int:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE batch_jobs
                    SET
                        status = 'failed',
                        finished_at = NOW(),
                        error_message = 'Server restarted during execution.'
                    WHERE status IN ('queued', 'processing')
                    """
                )
                updated = cur.rowcount
            conn.commit()
        return updated

    def metrics(self) -> Dict[str, Any]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status IN ('queued', 'processing'))::int AS active_jobs,
                        COUNT(*) FILTER (WHERE status = 'completed')::int AS completed_jobs,
                        COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_jobs,
                        COUNT(*)::int AS total_jobs
                    FROM batch_jobs
                    """
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    SELECT COALESCE(AVG(duration_ms), 0)::float8 AS average_chunk_duration_ms
                    FROM batch_chunk_results
                    """
                )
                row_chunk = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                        COALESCE(
                            AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000),
                            0
                        )::float8 AS average_job_duration_ms
                    FROM batch_jobs
                    WHERE started_at IS NOT NULL AND finished_at IS NOT NULL
                    """
                )
                row2 = cur.fetchone()
        return {
            **row,
            "average_chunk_duration_ms": float(row_chunk["average_chunk_duration_ms"]),
            "average_job_duration_ms": float(row2["average_job_duration_ms"]),
        }


job_repository = JobRepository()
