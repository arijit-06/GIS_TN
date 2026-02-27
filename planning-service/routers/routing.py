import time
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from models.schemas import RouteResponse, ComputeRouteRequest
from services.data_loader import data_store
from services.cost_service import calculate_cost

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("planning-service")

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/system-status")
def get_system_status():
    graph = data_store.graph
    return {
        "graph_nodes": len(graph.nodes) if graph else 0,
        "graph_edges": len(graph.edges) if graph else 0,
        "roads_loaded": len(data_store.roads_gdf) if data_store.roads_gdf is not None else 0,
        "gp_loaded": data_store.gp_boundary is not None and "features" in data_store.gp_boundary
    }

@router.get("/gp-boundary")
def get_gp_boundary():
    return data_store.gp_boundary

@router.get("/infra-nodes")
def get_infra_nodes():
    return data_store.infra_nodes

import networkx as nx
from math import radians, sin, cos, sqrt, atan2

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000  # radius of Earth in meters
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = sin(delta_phi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2.0) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

@router.post("/compute-route", response_model=RouteResponse)
def compute_route(request: ComputeRouteRequest):
    start_time = time.time()
    logger.info(f"Compute route requested: infra_id={request.infra_id}, customer_lat={request.customer_lat}, customer_lng={request.customer_lng}")
    
    # Input validation
    if not (-90 <= request.customer_lat <= 90):
        logger.error("Invalid customer_lat")
        return JSONResponse(status_code=400, content={"error": "customer_lat must be between -90 and 90"})
        
    if not (-180 <= request.customer_lng <= 180):
        logger.error("Invalid customer_lng")
        return JSONResponse(status_code=400, content={"error": "customer_lng must be between -180 and 180"})
        
    if not data_store.graph or len(data_store.graph.nodes) == 0:
        logger.error("Network graph is empty")
        return JSONResponse(status_code=500, content={"error": "Road network graph is not available"})

    infra = next((i for i in data_store.infra_nodes if i.get("id") == request.infra_id), None)
    if not infra:
        logger.error(f"Infrastructure node not found: {request.infra_id}")
        return JSONResponse(status_code=404, content={"error": "Infrastructure node not found"})
        
    infra_lon, infra_lat = infra["longitude"], infra["latitude"]
    cust_lon, cust_lat = request.customer_lng, request.customer_lat
    
    start_node = data_store.snap_to_graph(infra_lon, infra_lat)
    end_node = data_store.snap_to_graph(cust_lon, cust_lat)
    
    if not start_node or not end_node:
        logger.error("Could not snap points to road network graph")
        return JSONResponse(status_code=404, content={"error": "Could not snap points to road network graph"})
        
    try:
        path = nx.shortest_path(data_store.graph, source=start_node, target=end_node, weight='weight')
    except nx.NetworkXNoPath:
        logger.error("No path found between the points")
        return JSONResponse(status_code=404, content={"error": "No path found between the points"})
    except Exception as e:
        logger.error(f"Internal calculation error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Internal server error occurred while computing route"})
        
    # calculate exact metric length using haversine on the path segments
    total_dist = 0.0
    for i in range(len(path) - 1):
        u = path[i]
        v = path[i+1]
        total_dist += haversine(u[0], u[1], v[0], v[1])
        
    # Route response format: route: [ [lat, lng], ... ] we stored (lon, lat) in nodes
    formatted_route = [[node[1], node[0]] for node in path]
    
    estimated_cost = calculate_cost(total_dist)
    execution_time = round(time.time() - start_time, 3)
    
    logger.info(f"Route computed successfully. Distance: {total_dist:.2f}m, Cost: {estimated_cost}, Execution Time: {execution_time}s")
    
    return {
        "route": formatted_route,
        "distance_meters": total_dist,
        "estimated_cost": estimated_cost,
        "execution_time_seconds": execution_time
    }
