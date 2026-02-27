from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_db
from app.schemas import DistrictSummary, FranchiseSummary, SystemSummary
from app.services.planning_service import PlanningService

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/summary", response_model=SystemSummary)
def system_summary():
    try:
        with get_db() as conn:
            return PlanningService(conn).system_summary()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "summary_fetch_failed", "message": "Failed to fetch summary."},
        ) from exc


@router.get("/districts", response_model=List[DistrictSummary])
def districts():
    try:
        with get_db() as conn:
            return PlanningService(conn).list_districts()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "districts_fetch_failed", "message": "Failed to fetch districts."},
        ) from exc


@router.get("/franchises", response_model=List[FranchiseSummary])
def franchises(district_id: Optional[str] = Query(default=None)):
    try:
        with get_db() as conn:
            return PlanningService(conn).list_franchises(district_id=district_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "franchises_fetch_failed", "message": "Failed to fetch franchises."},
        ) from exc
