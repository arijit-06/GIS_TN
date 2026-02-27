const EARTH_RADIUS_M = 6371000;
const DEFAULT_COST_PER_METER = 700;

const toRadians = (value) => (value * Math.PI) / 180;

export const haversineMeters = (lon1, lat1, lon2, lat2) => {
    const phi1 = toRadians(lat1);
    const phi2 = toRadians(lat2);
    const deltaPhi = toRadians(lat2 - lat1);
    const deltaLambda = toRadians(lon2 - lon1);

    const a = Math.sin(deltaPhi / 2) ** 2
        + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return EARTH_RADIUS_M * c;
};

const nodeKey = (lon, lat) => `${lon.toFixed(6)},${lat.toFixed(6)}`;

const parseNodeKey = (key) => {
    const [lon, lat] = key.split(",").map(Number);
    return { lon, lat };
};

class MinHeap {
    constructor() {
        this.data = [];
    }

    push(item) {
        this.data.push(item);
        this.bubbleUp(this.data.length - 1);
    }

    pop() {
        if (this.data.length === 0) return null;
        const min = this.data[0];
        const end = this.data.pop();
        if (this.data.length > 0) {
            this.data[0] = end;
            this.bubbleDown(0);
        }
        return min;
    }

    get size() {
        return this.data.length;
    }

    bubbleUp(index) {
        let i = index;
        while (i > 0) {
            const parent = Math.floor((i - 1) / 2);
            if (this.data[parent].priority <= this.data[i].priority) break;
            [this.data[parent], this.data[i]] = [this.data[i], this.data[parent]];
            i = parent;
        }
    }

    bubbleDown(index) {
        let i = index;
        const length = this.data.length;
        while (true) {
            const left = (2 * i) + 1;
            const right = (2 * i) + 2;
            let smallest = i;

            if (left < length && this.data[left].priority < this.data[smallest].priority) {
                smallest = left;
            }
            if (right < length && this.data[right].priority < this.data[smallest].priority) {
                smallest = right;
            }
            if (smallest === i) break;
            [this.data[i], this.data[smallest]] = [this.data[smallest], this.data[i]];
            i = smallest;
        }
    }
}

const extractLineCoordinates = (roadsGeoJson) => {
    if (!roadsGeoJson?.features) return [];
    const lines = [];
    for (const feature of roadsGeoJson.features) {
        const geometry = feature?.geometry;
        if (!geometry) continue;

        if (geometry.type === "LineString" && Array.isArray(geometry.coordinates)) {
            lines.push(geometry.coordinates);
        }
        if (geometry.type === "MultiLineString" && Array.isArray(geometry.coordinates)) {
            for (const line of geometry.coordinates) {
                if (Array.isArray(line)) lines.push(line);
            }
        }
    }
    return lines;
};

export const normalizeInfraNodes = (raw) => {
    if (Array.isArray(raw)) {
        return raw
            .map((node, idx) => ({
                id: node.id || `infra_${idx + 1}`,
                lat: Number(node.lat ?? node.latitude),
                lng: Number(node.lng ?? node.longitude),
            }))
            .filter((node) => Number.isFinite(node.lat) && Number.isFinite(node.lng));
    }

    if (raw?.type === "FeatureCollection" && Array.isArray(raw.features)) {
        return raw.features
            .map((feature, idx) => ({
                id: feature?.properties?.infra_id || feature?.properties?.id || `infra_${idx + 1}`,
                lat: Number(feature?.geometry?.coordinates?.[1]),
                lng: Number(feature?.geometry?.coordinates?.[0]),
            }))
            .filter((node) => Number.isFinite(node.lat) && Number.isFinite(node.lng));
    }

    return [];
};

export const buildRoadGraph = (roadsGeoJson) => {
    const lines = extractLineCoordinates(roadsGeoJson);
    const adjacency = new Map();
    const nodes = new Map();
    let edgeCount = 0;

    const ensureNode = (lon, lat) => {
        const key = nodeKey(lon, lat);
        if (!nodes.has(key)) nodes.set(key, { lon, lat });
        if (!adjacency.has(key)) adjacency.set(key, []);
        return key;
    };

    for (const line of lines) {
        for (let i = 0; i < line.length - 1; i += 1) {
            const [lon1, lat1] = line[i];
            const [lon2, lat2] = line[i + 1];
            if (![lon1, lat1, lon2, lat2].every(Number.isFinite)) continue;

            const from = ensureNode(lon1, lat1);
            const to = ensureNode(lon2, lat2);
            const weight = haversineMeters(lon1, lat1, lon2, lat2);

            adjacency.get(from).push({ to, weight });
            adjacency.get(to).push({ to: from, weight });
            edgeCount += 1;
        }
    }

    return {
        adjacency,
        nodes,
        edgeCount,
        lineCount: lines.length,
    };
};

export const snapToGraph = (graph, lon, lat, maxDistanceMeters = 8000) => {
    let nearest = null;
    let minDist = Number.POSITIVE_INFINITY;

    for (const node of graph.nodes.values()) {
        const distance = haversineMeters(lon, lat, node.lon, node.lat);
        if (distance < minDist) {
            minDist = distance;
            nearest = nodeKey(node.lon, node.lat);
        }
    }

    if (!nearest || minDist > maxDistanceMeters) {
        return { nodeKey: null, distanceMeters: minDist };
    }
    return { nodeKey: nearest, distanceMeters: minDist };
};

export const shortestPath = (graph, start, end) => {
    if (start === end) return [start];
    const distances = new Map();
    const previous = new Map();
    const visited = new Set();
    const queue = new MinHeap();

    distances.set(start, 0);
    queue.push({ key: start, priority: 0 });

    while (queue.size > 0) {
        const current = queue.pop();
        if (!current || visited.has(current.key)) continue;
        visited.add(current.key);

        if (current.key === end) break;
        const edges = graph.adjacency.get(current.key) || [];
        for (const edge of edges) {
            const alt = distances.get(current.key) + edge.weight;
            if (alt < (distances.get(edge.to) ?? Number.POSITIVE_INFINITY)) {
                distances.set(edge.to, alt);
                previous.set(edge.to, current.key);
                queue.push({ key: edge.to, priority: alt });
            }
        }
    }

    if (!previous.has(end) && start !== end) return null;

    const path = [];
    let current = end;
    while (current) {
        path.unshift(current);
        if (current === start) break;
        current = previous.get(current);
    }
    return path.length > 0 && path[0] === start ? path : null;
};

export const pathDistanceMeters = (pathKeys) => {
    if (!Array.isArray(pathKeys) || pathKeys.length < 2) return 0;
    let total = 0;
    for (let i = 0; i < pathKeys.length - 1; i += 1) {
        const a = parseNodeKey(pathKeys[i]);
        const b = parseNodeKey(pathKeys[i + 1]);
        total += haversineMeters(a.lon, a.lat, b.lon, b.lat);
    }
    return total;
};

export const pathToLatLng = (pathKeys) =>
    pathKeys.map((key) => {
        const parsed = parseNodeKey(key);
        return [parsed.lat, parsed.lon];
    });

export const estimateCost = (distanceMeters, costPerMeter = DEFAULT_COST_PER_METER) =>
    Math.round(distanceMeters * costPerMeter * 100) / 100;

const fetchJson = async (url) => {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to load ${url}`);
    }
    return response.json();
};

const loadInfraGeoJson = async () => {
    // GeoJSON is the primary format; fallback keeps older local snapshots usable.
    try {
        return await fetchJson("/data/infra_nodes.geojson");
    } catch (_) {
        return fetchJson("/data/infra_nodes.json");
    }
};

export const loadPlannerData = async () => {
    const [gpBoundary, rawInfra, roads] = await Promise.all([
        fetchJson("/data/gp_boundary.geojson"),
        loadInfraGeoJson(),
        fetchJson("/data/roads.geojson"),
    ]);

    const infraNodes = normalizeInfraNodes(rawInfra);
    const graph = buildRoadGraph(roads);
    return { gpBoundary, infraNodes, roads, graph };
};

export const computeLocalRoute = ({
    graph,
    infraNode,
    customerLocation,
    maxSnapDistanceMeters = 8000,
}) => {
    const startedAt = performance.now();
    const startSnap = snapToGraph(graph, infraNode.lng, infraNode.lat, maxSnapDistanceMeters);
    const endSnap = snapToGraph(graph, customerLocation.lng, customerLocation.lat, maxSnapDistanceMeters);

    if (!startSnap.nodeKey || !endSnap.nodeKey) {
        return {
            error: "Selected points are too far from the loaded road network.",
            executionTimeSeconds: ((performance.now() - startedAt) / 1000).toFixed(3),
        };
    }

    const pathKeys = shortestPath(graph, startSnap.nodeKey, endSnap.nodeKey);
    if (!pathKeys) {
        return {
            error: "No connected path found between the selected points on the current road graph.",
            executionTimeSeconds: ((performance.now() - startedAt) / 1000).toFixed(3),
        };
    }

    const networkDistanceMeters = pathDistanceMeters(pathKeys);
    const distanceMeters = networkDistanceMeters + startSnap.distanceMeters + endSnap.distanceMeters;
    const networkLatLng = pathToLatLng(pathKeys);
    const route = [
        [infraNode.lat, infraNode.lng],
        ...networkLatLng,
        [customerLocation.lat, customerLocation.lng],
    ];

    return {
        route,
        distanceMeters,
        estimatedCost: estimateCost(distanceMeters),
        executionTimeSeconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)),
        startSnapMeters: Math.round(startSnap.distanceMeters),
        endSnapMeters: Math.round(endSnap.distanceMeters),
    };
};
