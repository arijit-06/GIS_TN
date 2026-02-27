import uvicorn
import logging
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.executor_pool import shutdown_executors
from app.errors import AppError
from app.job_repository import job_repository
from app.logging_setup import configure_logging
from app.middleware import InMemoryRateLimitMiddleware, PayloadSizeLimitMiddleware, RequestContextMiddleware, RequestTimeoutMiddleware
from app.routers.catalog import router as catalog_router
from app.routers.health import router as health_router
from app.routers.routing import router as routing_router
from app.routers.upload_batch import router as upload_batch_router

configure_logging()
logger = logging.getLogger("planning-service")

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)
app.add_middleware(RequestTimeoutMiddleware)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = exc.errors()
    malformed_json = any(err.get("type") == "json_invalid" for err in details)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "malformed_json" if malformed_json else "validation_error",
                "message": "Malformed JSON request body." if malformed_json else "Request payload validation failed.",
                "details": details,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error = detail
    else:
        error = {"code": "http_error", "message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_exception",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "An internal server error occurred."},
            "request_id": getattr(request.state, "request_id", None),
        },
    )

app.include_router(health_router)
app.include_router(catalog_router)
app.include_router(routing_router)
app.include_router(upload_batch_router)


@app.on_event("startup")
def startup_event():
    job_repository.ensure_schema()
    recovered = job_repository.mark_incomplete_jobs_failed()
    if recovered:
        logger.warning(
            "recovered_incomplete_jobs",
            extra={"recovered_jobs": recovered},
        )


@app.on_event("shutdown")
def shutdown_event():
    shutdown_executors()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
