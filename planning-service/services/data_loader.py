import json
import os
import geopandas as gpd
from shapely.geometry import Point, LineString
import networkx as nx
from math import radians, sin, cos, sqrt, atan2

def haversine(lon1, lat1, lon2, lat2):
    # Calculate distance between two points in meters using Haversine formula
    R = 6371000  # radius of Earth in meters
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = sin(delta_phi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2.0) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

class DataLoader:
    def __init__(self):
        self.gp_boundary = None
        self.roads = None
        self.infra_nodes = None
        
        self.gp_gdf = None
        self.roads_gdf = None
        self.graph = None

    def load_data(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        
        # Load gp_boundary
        gp_path = os.path.join(data_dir, "gp_boundary.geojson")
        try:
            with open(gp_path, "r") as f:
                self.gp_boundary = json.load(f)
            self.gp_gdf = gpd.read_file(gp_path)
            if self.gp_gdf.crs is None or self.gp_gdf.crs.to_epsg() != 4326:
                self.gp_gdf = self.gp_gdf.to_crs(epsg=4326)
        except Exception:
            self.gp_boundary = {"type": "FeatureCollection", "features": []}

        # Load roads
        roads_path = os.path.join(data_dir, "roads.geojson")
        try:
            with open(roads_path, "r") as f:
                self.roads_raw = json.load(f) # keeping raw if needed
            roads_gdf = gpd.read_file(roads_path)
            if roads_gdf.crs is None or roads_gdf.crs.to_epsg() != 4326:
                roads_gdf = roads_gdf.to_crs(epsg=4326)
            
            # Clip roads to GP boundary
            if self.gp_gdf is not None and not self.gp_gdf.empty:
                gp_polygon = self.gp_gdf.geometry.iloc[0]
                self.roads_gdf = gpd.clip(roads_gdf, gp_polygon)
            else:
                self.roads_gdf = roads_gdf
                
            # Update roads geojson to clipped version
            self.roads = json.loads(self.roads_gdf.to_json())
            
        except Exception:
            self.roads = {"type": "FeatureCollection", "features": []}

        # Load infra_nodes
        try:
            with open(os.path.join(data_dir, "infra_nodes.json"), "r") as f:
                self.infra_nodes = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.infra_nodes = []
            
        self.build_graph()

    def build_graph(self):
        self.graph = nx.Graph()
        if self.roads_gdf is None or self.roads_gdf.empty:
            return
            
        for _, row in self.roads_gdf.iterrows():
            geom = row.geometry
            if geom.geom_type == 'LineString':
                lines = [geom]
            elif geom.geom_type == 'MultiLineString':
                lines = list(geom.geoms)
            else:
                continue
                
            for line in lines:
                coords = list(line.coords)
                for i in range(len(coords) - 1):
                    u = (round(coords[i][0], 6), round(coords[i][1], 6))
                    v = (round(coords[i+1][0], 6), round(coords[i+1][1], 6))
                    # Edge weight = segment length. We use geographic distance.
                    # For simplicity, calculating euclidean distance on lat/lon or simple length.
                    # For real apps we should project to metric system like EPSG:3857, calculate length, then revert.
                    
                    segment = LineString([u, v])
                    # simple length proxy for weight
                    weight = segment.length 
                    self.graph.add_edge(u, v, weight=weight)
                    
        if len(self.graph.nodes) > 0:
            components = list(nx.connected_components(self.graph))
            print(f"Connected components before filtering: {len(components)}")
            if components:
                largest_cc = max(components, key=len)
                self.graph = self.graph.subgraph(largest_cc).copy()
                print(f"Using largest connected component. Nodes: {self.graph.number_of_nodes()}")
                    
    def snap_to_graph(self, lon, lat):
        if not self.graph or len(self.graph.nodes) == 0:
            return None
            
        nearest_node = None
        min_dist = float('inf')
        
        for node in self.graph.nodes:
            n_lon, n_lat = node
            dist = haversine(lon, lat, n_lon, n_lat)
            if dist < min_dist:
                min_dist = dist
                nearest_node = node
                
        if min_dist > 1000: # 1 km threshold
            print(f"Point ({lon}, {lat}) too far from road network: {min_dist}m")
            return None
            
        return nearest_node

data_store = DataLoader()
