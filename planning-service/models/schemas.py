from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class RouteResponse(BaseModel):
    route: List[List[float]]
    distance_meters: float
    estimated_cost: float
    execution_time_seconds: float

class ComputeRouteRequest(BaseModel):
    infra_id: str
    customer_lat: float
    customer_lng: float
