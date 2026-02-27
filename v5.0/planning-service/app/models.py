from typing import List, Literal, Optional

from pydantic import BaseModel, Field


MAX_SCHEMA_POINTS = 10_000_000
SECURE_MAX_POINTS = 100_000
CHUNK_SIZE = 1_000


class CoordinatePoint(BaseModel):
    id: int
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class BatchUploadRequest(BaseModel):
    coordinates: List[CoordinatePoint] = Field(min_length=1, max_length=MAX_SCHEMA_POINTS)


class BatchUploadResponse(BaseModel):
    total_points: int
    total_chunks: int
    chunk_sizes: List[int]


JobState = Literal["queued", "processing", "completed", "failed"]


class BatchUploadAccepted(BaseModel):
    job_id: str
    status: JobState
    total_points: int
    total_chunks: int
    chunk_sizes: List[int]


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobState
    total_points: int
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error_message: Optional[str] = None


class JobResultResponse(BaseModel):
    job_id: str
    status: JobState
    total_points: int
    total_chunks: int
    chunk_sizes: List[int]
    processed_chunks: int
    failed_chunks: int
    results: List[dict]
    error_message: Optional[str] = None


class JobMetricsResponse(BaseModel):
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_jobs: int
    max_active_jobs: int
    executor_max_workers: int
    average_chunk_duration_ms: float
    average_job_duration_ms: float
