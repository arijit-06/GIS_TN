from concurrent.futures import ThreadPoolExecutor

from app.config import settings

# Global executors created once at module load.
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=settings.executor_max_workers, thread_name_prefix="job-worker")
CHUNK_EXECUTOR = ThreadPoolExecutor(max_workers=settings.chunk_executor_max_workers, thread_name_prefix="chunk-worker")


def shutdown_executors() -> None:
    JOB_EXECUTOR.shutdown(wait=True, cancel_futures=True)
    CHUNK_EXECUTOR.shutdown(wait=True, cancel_futures=True)
