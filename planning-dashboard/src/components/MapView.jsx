import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, Polyline, useMap, useMapEvents, CircleMarker, Popup } from 'react-leaflet';
import L from 'leaflet';

// Fix for default Leaflet icon paths
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Create custom colored icons using divIcon for easy styling without external images
const createCustomIcon = (color) => {
    return new L.DivIcon({
        className: 'custom-icon',
        html: `<div style="background-color: ${color}; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });
};

const redIcon = createCustomIcon('#ef4444');
const greenIcon = createCustomIcon('#22c55e');

// Component to handle map clicks for customer location
const MapEvents = ({ setCustomerLocation }) => {
    useMapEvents({
        click(e) {
            setCustomerLocation({ lat: e.latlng.lat, lng: e.latlng.lng });
        },
    });
    return null;
};


// Component to fit map to boundary
const FitBounds = ({ data }) => {
    const map = useMap();
    useEffect(() => {
        if (data && data.features && data.features.length > 0) {
            const geoJsonLayer = L.geoJSON(data);
            map.fitBounds(geoJsonLayer.getBounds(), { padding: [50, 50] });
        }
    }, [data, map]);
    return null;
};

// Component to fit map to computed route
const FitRouteBounds = ({ routeInfo }) => {
    const map = useMap();
    useEffect(() => {
        if (routeInfo && routeInfo.route && routeInfo.route.length > 0) {
            const bounds = L.latLngBounds(routeInfo.route);
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    }, [routeInfo, map]);
    return null;
};

const MapView = ({
    gpBoundary,
    infraNodes,
    selectedInfra,
    setSelectedInfra,
    customerLocation,
    setCustomerLocation,
    routeInfo,
    isLoading,

}) => {

    const boundaryStyle = {
        color: '#334155',
        weight: 2,
        opacity: 0.8,
        fillColor: '#cbd5e1',
        fillOpacity: 0.2,
        dashArray: '5, 5'
    };

    useEffect(() => {
        console.log("Infra nodes:", infraNodes);
    }, [infraNodes]);

    return (
        <div className="map-wrapper">
            {isLoading && (
                <div className="map-loading-overlay">
                    <div className="spinner"></div>
                </div>
            )}

            <MapContainer
                center={[20.5937, 78.9629]}
                zoom={5}
                style={{ height: '100%', width: '100%' }}
                zoomControl={false}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                    attribution="&copy; OpenStreetMap contributors &copy; CARTO"
                />

                {gpBoundary && (
                    <>
                        <GeoJSON data={gpBoundary} style={boundaryStyle} />
                        <FitBounds data={gpBoundary} />
                    </>
                )}

                {Array.isArray(infraNodes) && infraNodes.map((node, idx) => {
                    if (!node || typeof node.lat !== "number" || typeof node.lng !== "number") {
                        return null;
                    }

                    return (
                        <Marker
                            key={node.id || idx}
                            position={[node.lat, node.lng]}
                            icon={redIcon}
                            eventHandlers={{
                                click: () => setSelectedInfra(node),
                            }}
                        >
                            <Popup>
                                <strong>Infrastructure Node</strong><br />
                                ID: {node.id}
                            </Popup>
                        </Marker>
                    );
                })}

                {customerLocation && (
                    <Marker
                        position={[customerLocation.lat, customerLocation.lng]}
                        icon={greenIcon}
                    >
                        <Popup>
                            <strong>Customer Location</strong><br />
                            {customerLocation.lat.toFixed(5)}, {customerLocation.lng.toFixed(5)}
                        </Popup>
                    </Marker>
                )}

                {routeInfo &&
                    Array.isArray(routeInfo.route) &&
                    routeInfo.route.length > 0 &&
                    routeInfo.route.every(pt => Array.isArray(pt) && pt.length === 2) && (
                        <>
                            <Polyline
                                positions={routeInfo.route}
                                pathOptions={{ color: '#0ea5e9', weight: 4, opacity: 0.8 }}
                            />
                            <FitRouteBounds routeInfo={routeInfo} />
                        </>
                    )}

                <MapEvents setCustomerLocation={setCustomerLocation} />
            </MapContainer>

            <div className="map-legend">
                <div className="legend-item">
                    <span className="legend-color" style={{ backgroundColor: '#ef4444' }}></span>
                    Infra Node
                </div>
                <div className="legend-item">
                    <span className="legend-color" style={{ backgroundColor: '#22c55e' }}></span>
                    Customer
                </div>
                <div className="legend-item">
                    <span className="legend-line"></span>
                    Route
                </div>
                <div className="legend-item">
                    <span className="legend-border"></span>
                    GP Boundary
                </div>
            </div>
        </div>
    );
};

export default MapView;
