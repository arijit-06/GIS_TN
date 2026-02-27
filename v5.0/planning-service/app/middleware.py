import logging
import time
import uuid
import asyncio
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger("planning-service")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        request_size = None
        length_header = request.headers.get("content-length")
        if length_header is not None:
            try:
                request_size = int(length_header)
            except ValueError:
                request_size = None

        response = await call_next(request)
        response.headers["x-request-id"] = request_id

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else "unknown",
                "request_size_bytes": request_size,
            },
        )
        return response


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length_header = request.headers.get("content-length")
        if length_header is not None:
            try:
                length = int(length_header)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "invalid_content_length",
                            "message": "Invalid Content-Length header.",
                        }
                    },
                )
            if length > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": f"Request body exceeds {settings.max_request_body_bytes} bytes.",
                        }
                    },
                )
        else:
            # For chunked uploads without Content-Length, enforce limit on actual body size.
            body = await request.body()
            if len(body) > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": f"Request body exceeds {settings.max_request_body_bytes} bytes.",
                        }
                    },
                )
        return await call_next(request)


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.window_seconds = settings.rate_limit_window_seconds
        self.max_requests = settings.rate_limit_requests_per_window
        self._lock = Lock()
        self._requests_by_ip: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        with self._lock:
            queue = self._requests_by_ip.setdefault(client_ip, deque())
            while queue and (now - queue[0]) > self.window_seconds:
                queue.popleft()

            if len(queue) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests. Please retry later.",
                        }
                    },
                    headers={"retry-after": str(self.window_seconds)},
                )

            queue.append(now)

        return await call_next(request)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_seconds)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "request_timeout",
                        "message": f"Request exceeded {settings.request_timeout_seconds} seconds.",
                    }
                },
            )
