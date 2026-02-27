import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger("planning-service")


class InMemoryJobStore:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _new_job_record(self, total_points: int, chunk_sizes: list[int]) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = time.time()
        return {
            "job_id": job_id,
            "status": "queued",
            "total_points": total_points,
            "total_chunks": len(chunk_sizes),
            "chunk_sizes": chunk_sizes,
            "processed_chunks": 0,
            "failed_chunks": 0,
            "results": [],
            "error_message": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "last_updated_at": now,
            "average_chunk_duration": 0.0,
            "max_chunk_duration": 0,
            "total_processing_time": 0,
        }

    def create_job(self, total_points: int, chunk_sizes: list[int]) -> Dict[str, Any]:
        record = self._new_job_record(total_points=total_points, chunk_sizes=chunk_sizes)
        with self._lock:
            self._jobs[record["job_id"]] = record
            self._enforce_memory_limit_locked()
        return dict(record)

    def create_job_if_capacity(self, total_points: int, chunk_sizes: list[int], max_active_jobs: int) -> Optional[Dict[str, Any]]:
        record = self._new_job_record(total_points=total_points, chunk_sizes=chunk_sizes)
        with self._lock:
            active = sum(1 for job in self._jobs.values() if job["status"] in {"queued", "processing"})
            if active >= max_active_jobs:
                return None
            self._jobs[record["job_id"]] = record
            self._enforce_memory_limit_locked()
        return dict(record)

    def set_job(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._jobs[record["job_id"]] = dict(record)
            self._enforce_memory_limit_locked()
            return dict(self._jobs[record["job_id"]])

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def update_job(self, job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.update(kwargs)
            job["last_updated_at"] = time.time()
            self._enforce_memory_limit_locked()
            return dict(job)

    def append_result(self, job_id: str, item: Dict[str, Any], failed: bool = False) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job["results"].append(item)
            job["processed_chunks"] += 1
            if failed:
                job["failed_chunks"] += 1

            duration = int(item.get("duration_ms") or 0)
            processed = int(job["processed_chunks"])
            prev_avg = float(job.get("average_chunk_duration") or 0.0)
            job["average_chunk_duration"] = ((prev_avg * (processed - 1)) + duration) / max(processed, 1)
            job["max_chunk_duration"] = max(int(job.get("max_chunk_duration") or 0), duration)
            job["total_processing_time"] = int(job.get("total_processing_time") or 0) + duration

            job["last_updated_at"] = time.time()
            self._enforce_memory_limit_locked()
            return dict(job)

    def pop_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._jobs.pop(job_id, None)

    def active_job_count(self) -> int:
        with self._lock:
            return sum(1 for job in self._jobs.values() if job["status"] in {"queued", "processing"})

    def metrics(self) -> Dict[str, int]:
        with self._lock:
            total = len(self._jobs)
            active = sum(1 for job in self._jobs.values() if job["status"] in {"queued", "processing"})
            completed = sum(1 for job in self._jobs.values() if job["status"] == "completed")
            failed = sum(1 for job in self._jobs.values() if job["status"] == "failed")
            return {
                "active_jobs": active,
                "completed_jobs": completed,
                "failed_jobs": failed,
                "total_jobs": total,
            }

    def cleanup_finished(self) -> int:
        now = time.time()
        ttl = settings.job_retention_seconds
        removed = 0
        with self._lock:
            to_delete = []
            for job_id, job in self._jobs.items():
                if job["status"] not in {"completed", "failed"}:
                    continue
                finished_at = job.get("finished_at") or job.get("last_updated_at") or job.get("created_at")
                if finished_at is None:
                    continue
                if (now - finished_at) > ttl:
                    to_delete.append(job_id)
            for job_id in to_delete:
                self._jobs.pop(job_id, None)
                removed += 1

            # Enforce memory pressure guard after TTL cleanup.
            removed += self._enforce_memory_limit_locked()
        return removed

    def _approx_job_size_bytes(self, job: Dict[str, Any]) -> int:
        try:
            return len(json.dumps(job, default=str).encode("utf-8"))
        except Exception:
            return 0

    def _memory_usage_bytes_locked(self) -> int:
        return sum(self._approx_job_size_bytes(job) for job in self._jobs.values())

    def _enforce_memory_limit_locked(self) -> int:
        max_bytes = int(settings.max_stored_results_memory_mb * 1024 * 1024)
        if max_bytes <= 0:
            return 0
        removed = 0
        while self._memory_usage_bytes_locked() > max_bytes:
            candidates = [
                (job_id, job)
                for job_id, job in self._jobs.items()
                if job.get("status") in {"completed", "failed"}
            ]
            if not candidates:
                break
            oldest_id, _ = min(
                candidates,
                key=lambda item: (
                    item[1].get("finished_at")
                    or item[1].get("last_updated_at")
                    or item[1].get("created_at")
                    or 0
                ),
            )
            self._jobs.pop(oldest_id, None)
            removed += 1
        if removed:
            logger.warning(
                "job_cache_eviction",
                extra={
                    "evicted_jobs": removed,
                    "memory_limit_mb": settings.max_stored_results_memory_mb,
                },
            )
        return removed

    def enforce_memory_limit(self) -> int:
        with self._lock:
            return self._enforce_memory_limit_locked()


job_store = InMemoryJobStore()
