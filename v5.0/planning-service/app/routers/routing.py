from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.errors import AppError
from app.schemas import BatchRouteRequest, BatchRouteResponse, ConsumerRouteRequest, ConsumerRouteResponse
from app.services.planning_service import PlanningService

router = APIRouter(prefix="/routing", tags=["routing"])


@router.post("/compute", response_model=ConsumerRouteResponse)
def compute_route(payload: ConsumerRouteRequest):
    try:
        with get_db() as conn:
            service = PlanningService(conn)
            result = service.compute_route(
                longitude=payload.longitude,
                latitude=payload.latitude,
            )
        return result
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


@router.post("/compute-batch", response_model=BatchRouteResponse)
def compute_batch_route(payload: BatchRouteRequest):
    try:
        with get_db() as conn:
            service = PlanningService(conn)
            result = service.compute_batch(
                coordinates=[item.model_dump() for item in payload.coordinates],
                include_geometry=payload.include_geometry,
            )
        return result
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
