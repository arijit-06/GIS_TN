import json
import os
import geopandas as gpd
from shapely.geometry import Point, LineString
import networkx as nx

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
                    u = coords[i]
                    v = coords[i+1]
                    # Edge weight = segment length. We use geographic distance.
                    # For simplicity, calculating euclidean distance on lat/lon or simple length.
                    # For real apps we should project to metric system like EPSG:3857, calculate length, then revert.
                    
                    segment = LineString([u, v])
                    # simple length proxy for weight
                    weight = segment.length 
                    self.graph.add_edge(u, v, weight=weight)
                    
    def snap_to_graph(self, lon, lat):
        if not self.graph or len(self.graph.nodes) == 0:
            return (lon, lat)
            
        point = Point(lon, lat)
        
        # Find nearest node
        # A simple linear scan. For larger graphs, use a spatial index (e.g. STRtree)
        nearest_node = None
        min_dist = float('inf')
        
        for node in self.graph.nodes:
            n_point = Point(node[0], node[1])
            dist = point.distance(n_point)
            if dist < min_dist:
                min_dist = dist
                nearest_node = node
                
        return nearest_node

data_store = DataLoader()
