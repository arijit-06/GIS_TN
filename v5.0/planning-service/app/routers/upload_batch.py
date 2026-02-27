import logging
import time
from concurrent.futures import TimeoutError
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.status import HTTP_202_ACCEPTED

from app.config import settings
from app.executor_pool import CHUNK_EXECUTOR, JOB_EXECUTOR
from app.job_repository import job_repository
from app.job_store import job_store
from app.models import (
    BatchUploadAccepted,
    BatchUploadRequest,
    CHUNK_SIZE,
    JobMetricsResponse,
    JobResultResponse,
    JobStatusResponse,
    SECURE_MAX_POINTS,
)
from app.preprocessing import chunk_generator, get_chunk_processor

logger = logging.getLogger("planning-service")

router = APIRouter(tags=["preprocessing"])


def _hydrate_job_record_from_db(job_id: str) -> Optional[Dict[str, Any]]:
    job = job_repository.get_job(job_id)
    if not job:
        return None
    chunk_rows = job_repository.get_chunk_results(job_id)
    chunk_sizes = [CHUNK_SIZE] * (job["total_chunks"] - 1) + (
        [job["total_points"] - (CHUNK_SIZE * (job["total_chunks"] - 1))] if job["total_chunks"] > 0 else []
    )
    if job["total_chunks"] == 1:
        chunk_sizes = [job["total_points"]]
    avg_chunk = 0.0
    max_chunk = 0
    if chunk_rows:
        durations = [int(r.get("duration_ms") or 0) for r in chunk_rows]
        avg_chunk = float(sum(durations) / len(durations))
        max_chunk = max(durations)
    total_processing_time = int(sum(int(r.get("duration_ms") or 0) for r in chunk_rows))
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_points": job["total_points"],
        "total_chunks": job["total_chunks"],
        "chunk_sizes": chunk_sizes,
        "processed_chunks": job["processed_chunks"],
        "failed_chunks": job["failed_chunks"],
        "results": [
            {
                "chunk_index": r["chunk_index"],
                "processed_points": r["processed_points"],
                "status": r["status"],
                "error_message": r["error_message"],
                "duration_ms": r["duration_ms"],
            }
            for r in chunk_rows
        ],
        "error_message": job["error_message"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "last_updated_at": job["finished_at"] or job["started_at"] or job["created_at"],
        "average_chunk_duration": avg_chunk,
        "max_chunk_duration": max_chunk,
        "total_processing_time": total_processing_time,
    }


def _get_job_from_cache_or_db(job_id: str) -> Optional[Dict[str, Any]]:
    cached = job_store.get_job(job_id)
    if cached:
        return cached
    hydrated = _hydrate_job_record_from_db(job_id)
    if hydrated:
        job_store.set_job(hydrated)
        return hydrated
    return None


def _process_job_in_background(job_id: str, coordinates: list):
    processor = get_chunk_processor()
    try:
        job_store.update_job(job_id, status="processing", started_at=time.time(), error_message=None)
        job_repository.update_job_status(job_id, status="processing", started_at_now=True, error_message=None)

        had_failures = False
        for idx, chunk in enumerate(chunk_generator(coordinates, CHUNK_SIZE)):
            chunk_started = time.perf_counter()
            try:
                future = CHUNK_EXECUTOR.submit(processor, chunk, idx)
                result = future.result(timeout=settings.chunk_timeout_seconds)
                duration_ms = int((time.perf_counter() - chunk_started) * 1000)

                if not isinstance(result, dict):
                    raise ValueError("Chunk processor must return a dictionary.")
                result.setdefault("chunk_index", idx)
                result.setdefault("processed_points", len(chunk))
                result.setdefault("status", "ok")
                result.setdefault("duration_ms", duration_ms)
                failed = result.get("status") != "ok"
                if failed:
                    had_failures = True

                job_store.append_result(job_id, result, failed=failed)
                job_repository.persist_chunk_result(
                    job_id=job_id,
                    chunk_index=result["chunk_index"],
                    processed_points=result["processed_points"],
                    status="failed" if failed else "ok",
                    error_message=result.get("error_message"),
                    duration_ms=int(result.get("duration_ms") or duration_ms),
                )
            except TimeoutError:
                had_failures = True
                duration_ms = int((time.perf_counter() - chunk_started) * 1000)
                timeout_result = {
                    "chunk_index": idx,
                    "processed_points": len(chunk),
                    "status": "failed",
                    "error_message": f"Chunk timeout after {settings.chunk_timeout_seconds} seconds.",
                    "duration_ms": duration_ms,
                }
                job_store.append_result(job_id, timeout_result, failed=True)
                job_repository.persist_chunk_result(
                    job_id=job_id,
                    chunk_index=idx,
                    processed_points=len(chunk),
                    status="failed",
                    error_message=timeout_result["error_message"],
                    duration_ms=duration_ms,
                )
            except Exception as exc:
                had_failures = True
                duration_ms = int((time.perf_counter() - chunk_started) * 1000)
                failed_result = {
                    "chunk_index": idx,
                    "processed_points": len(chunk),
                    "status": "failed",
                    "error_message": str(exc),
                    "duration_ms": duration_ms,
                }
                job_store.append_result(job_id, failed_result, failed=True)
                job_repository.persist_chunk_result(
                    job_id=job_id,
                    chunk_index=idx,
                    processed_points=len(chunk),
                    status="failed",
                    error_message=str(exc),
                    duration_ms=duration_ms,
                )

        final_status = "failed" if had_failures else "completed"
        final_error = "One or more chunks failed." if had_failures else None
        finished_at = time.time()
        job_store.update_job(job_id, status=final_status, finished_at=finished_at, error_message=final_error)
        job_repository.update_job_status(
            job_id,
            status=final_status,
            finished_at_now=True,
            error_message=final_error,
        )
        job_store.enforce_memory_limit()
    except Exception as exc:
        finished_at = time.time()
        job_store.update_job(
            job_id,
            status="failed",
            finished_at=finished_at,
            error_message=f"Background processing failed: {exc}",
        )
        job_repository.update_job_status(
            job_id,
            status="failed",
            finished_at_now=True,
            error_message=f"Background processing failed: {exc}",
        )


@router.post("/upload-batch", response_model=BatchUploadAccepted, status_code=HTTP_202_ACCEPTED)
def upload_batch(payload: BatchUploadRequest, request: Request):
    job_store.cleanup_finished()
    total_points = len(payload.coordinates)
    if total_points > SECURE_MAX_POINTS:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "batch_too_large",
                "message": f"Batch contains {total_points} points; maximum allowed is {SECURE_MAX_POINTS}.",
            },
        )

    chunk_sizes = [len(chunk) for chunk in chunk_generator(payload.coordinates, CHUNK_SIZE)]
    total_chunks = len(chunk_sizes)

    # Thread-safe admission against local active queue/load.
    job = job_store.create_job_if_capacity(
        total_points=total_points,
        chunk_sizes=chunk_sizes,
        max_active_jobs=settings.max_active_jobs,
    )
    if job is None:
        raise HTTPException(
            status_code=429,
            detail={"code": "server_busy", "message": "Server busy. Try again later."},
        )

    # Persist metadata before execution starts.
    try:
        job_repository.create_job(job["job_id"], total_points=total_points, total_chunks=total_chunks, status="queued")
    except Exception as exc:
        job_store.pop_job(job["job_id"])
        raise HTTPException(
            status_code=503,
            detail={"code": "persistence_error", "message": "Server busy. Try again later."},
        ) from exc

    try:
        JOB_EXECUTOR.submit(_process_job_in_background, job["job_id"], payload.coordinates)
    except Exception as exc:
        failed_at = time.time()
        job_store.update_job(
            job["job_id"],
            status="failed",
            finished_at=failed_at,
            error_message="Failed to submit job to executor.",
        )
        job_repository.update_job_status(
            job["job_id"],
            status="failed",
            finished_at_now=True,
            error_message="Failed to submit job to executor.",
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "executor_unavailable", "message": "Server busy. Try again later."},
        ) from exc

    logger.info(
        "batch_queued",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "job_id": job["job_id"],
            "total_points": total_points,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total_chunks,
        },
    )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_points": total_points,
        "total_chunks": total_chunks,
        "chunk_sizes": chunk_sizes,
    }


@router.get("/job-status/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    job_store.cleanup_finished()
    job = _get_job_from_cache_or_db(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"code": "job_not_found", "message": "Job ID not found or already cleaned up."},
        )
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_points": job["total_points"],
        "total_chunks": job["total_chunks"],
        "processed_chunks": job["processed_chunks"],
        "failed_chunks": job["failed_chunks"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "error_message": job["error_message"],
    }


@router.get("/job-result/{job_id}", response_model=JobResultResponse)
def job_result(job_id: str):
    job_store.cleanup_finished()
    job = _get_job_from_cache_or_db(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"code": "job_not_found", "message": "Job ID not found or already cleaned up."},
        )
    if job["status"] in {"queued", "processing"}:
        raise HTTPException(
            status_code=409,
            detail={"code": "job_not_ready", "message": f"Job is currently {job['status']}."},
        )

    # Only evict cache copy; DB records remain durable.
    job_store.pop_job(job_id)
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_points": job["total_points"],
        "total_chunks": job["total_chunks"],
        "chunk_sizes": job["chunk_sizes"],
        "processed_chunks": job["processed_chunks"],
        "failed_chunks": job["failed_chunks"],
        "results": job["results"],
        "error_message": job["error_message"],
    }


@router.get("/jobs/metrics", response_model=JobMetricsResponse)
def jobs_metrics():
    job_store.cleanup_finished()
    metrics = job_repository.metrics()
    return {
        "active_jobs": int(metrics["active_jobs"]),
        "completed_jobs": int(metrics["completed_jobs"]),
        "failed_jobs": int(metrics["failed_jobs"]),
        "total_jobs": int(metrics["total_jobs"]),
        "max_active_jobs": settings.max_active_jobs,
        "executor_max_workers": settings.executor_max_workers,
        "average_chunk_duration_ms": float(metrics["average_chunk_duration_ms"]),
        "average_job_duration_ms": float(metrics["average_job_duration_ms"]),
    }
