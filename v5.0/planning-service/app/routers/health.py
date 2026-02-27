from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.schemas import HealthResponse
from app.services.planning_service import PlanningService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    try:
        with get_db() as conn:
            service = PlanningService(conn)
            db_checks = service.health()
        return {"status": "ok", **db_checks}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "health_check_failed", "message": "Health check failed."},
        ) from exc
