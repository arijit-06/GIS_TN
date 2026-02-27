import json
import math
import random

roads = {
    'type': 'FeatureCollection',
    'features': []
}

# The user's new infra list spans roughly from:
# 12.926, 80.117 (North) down to 11.815, 79.791 (South).
# We will generate a single long 'highway' linestring passing through these infra nodes
# to simulate a dense road network spanning the corridor.

infras = []
try:
    with open('data/infra_nodes.geojson') as f:
        geo = json.load(f)
    for feat in geo.get('features', []):
        if feat.get('geometry', {}).get('type') != 'Point':
            continue
        props = feat.get('properties', {})
        coords = feat.get('geometry', {}).get('coordinates', [None, None])
        infras.append({
            'id': props.get('infra_id') or props.get('node_id') or props.get('id'),
            'lat': coords[1],
            'lng': coords[0],
        })
except FileNotFoundError:
    with open('data/infra_nodes.json') as f:
        infras = json.load(f)

# Sort them North to South
infras.sort(key=lambda x: x['lat'], reverse=True)

# Generate dense points along this route to act as our road nodes
coords = []
for i in range(len(infras) - 1):
    curr = infras[i]
    nxt = infras[i+1]
    
    # Generate 50 points between each infra node
    num_points = 50
    for j in range(num_points):
        frac = j / num_points
        lat = curr['lat'] + (nxt['lat'] - curr['lat']) * frac
        # add a small wiggle to make it look like a road segment
        lng = curr['lng'] + (nxt['lng'] - curr['lng']) * frac + (math.sin(j) * 0.001)
        coords.append([round(lng, 6), round(lat, 6)])

# add the final node
coords.append([round(infras[-1]['lng'], 6), round(infras[-1]['lat'], 6)])

roads['features'].append({
    'type': 'Feature',
    'properties': {'name': 'Mock GST Highway'},
    'geometry': {
        'type': 'LineString',
        'coordinates': coords
    }
})

# Let's add cross-roads for graph diversity
for infra in infras[::3]:  # Every 3rd infra point gets a crossroad
    cross_coords = []
    base_lat = infra['lat']
    base_lng = infra['lng']
    
    # West to East
    for j in range(-20, 21):
        if j == 0: continue
        lat = base_lat + random.uniform(-0.005, 0.005)
        lng = base_lng + (j * 0.0015)
        cross_coords.append([round(lng, 6), round(lat, 6)])
        
    roads['features'].append({
        'type': 'Feature',
        'properties': {'name': f"Crossroad near {infra['id']}"},
        'geometry': {
            'type': 'LineString',
            'coordinates': cross_coords
        }
    })

with open('data/roads.geojson', 'w') as f:
    json.dump(roads, f, indent=2)

print('Generated new roads.geojson with', sum(len(f['geometry']['coordinates']) for f in roads['features']), 'nodes.')
