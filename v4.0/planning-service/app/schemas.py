from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings


class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    postgis_ok: bool
    pgrouting_ok: bool


class ConsumerRouteRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ConsumerRouteResponse(BaseModel):
    franchise_id: str
    nearest_node_id: str
    source_road_node_id: int
    target_road_node_id: int
    distance_meters: float
    estimated_cost: float
    route_geojson: Dict[str, Any]
    edge_count: int


class CoordinateInput(BaseModel):
    id: Optional[str] = Field(default=None, max_length=128)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class BatchRouteRequest(BaseModel):
    coordinates: List[CoordinateInput] = Field(min_length=1, max_length=settings.max_batch_coordinates)
    include_geometry: bool = False


class BatchRouteItem(BaseModel):
    input_index: int
    input_id: Optional[str] = None
    latitude: float
    longitude: float
    status: str
    franchise_id: Optional[str] = None
    nearest_node_id: Optional[str] = None
    source_road_node_id: Optional[int] = None
    target_road_node_id: Optional[int] = None
    distance_meters: Optional[float] = None
    estimated_cost: Optional[float] = None
    edge_count: Optional[int] = None
    route_geojson: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BatchRouteResponse(BaseModel):
    total: int
    success_count: int
    failed_count: int
    results: List[BatchRouteItem]


class DistrictSummary(BaseModel):
    district_id: str
    name: str
    franchise_count: int


class FranchiseSummary(BaseModel):
    franchise_id: str
    district_id: str
    node_count: int


class SystemSummary(BaseModel):
    district_count: int
    franchise_count: int
    fiber_node_count: int
    road_edge_count: int
    road_node_count: int
