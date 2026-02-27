import React, { useState, useEffect } from 'react';
import MapView from './components/MapView';
import ControlPanel from './components/ControlPanel';
import { getGPBoundary, getInfraNodes, computeRoute } from './services/api';

function App() {
    const [gpBoundary, setGpBoundary] = useState(null);
    const [infraNodes, setInfraNodes] = useState([]);
    const [selectedInfra, setSelectedInfra] = useState(null);
    const [customerLocation, setCustomerLocation] = useState(null);
    const [routeInfo, setRouteInfo] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [errorMsg, setErrorMsg] = useState(null);

    useEffect(() => {
        // Load initial map elements: GP Boundary and Infra nodes
        const loadInitialData = async () => {
            try {
                const boundaryRes = await getGPBoundary();
                if (boundaryRes.data) {
                    setGpBoundary(boundaryRes.data);
                }

                const infraRes = await getInfraNodes();
                if (infraRes.data) {
                    setInfraNodes(infraRes.data);
                }
            } catch (err) {
                console.error("Failed to load initial map data", err);
            }
        };

        loadInitialData();
    }, []);

    const handleError = (msg) => {
        setErrorMsg(msg);
        const panel = document.querySelector('.panel-content');
        if (panel) panel.scrollTop = 0;

        setTimeout(() => {
            setErrorMsg(null);
        }, 5000);
    };

    const handleComputeRoute = async () => {
        if (!selectedInfra) {
            handleError("Please select an infrastructure node first.");
            return;
        }
        if (!customerLocation) {
            handleError("Please click on the map to place a customer location.");
            return;
        }

        try {
            setIsLoading(true);
            setErrorMsg(null);

            const payload = {
                infra_id: selectedInfra.id,
                customer_lat: customerLocation.lat,
                customer_lng: customerLocation.lng
            };

            const response = await computeRoute(payload);
            setRouteInfo(response.data);
        } catch (err) {
            if (err.response && err.response.data && err.response.data.error) {
                handleError(err.response.data.error);
            } else if (err.response && err.response.status === 404) {
                handleError("No path could be computed between these points.");
            } else {
                handleError("An error occurred while computing the route.");
            }
            setRouteInfo(null);
        } finally {
            setIsLoading(false);
        }
    };

    const handleResetRoute = () => {
        setRouteInfo(null);
        setCustomerLocation(null);
        setErrorMsg(null);
    };

    return (
        <div className="app-wrapper">
            <header className="top-header">
                <div>
                    <h1>AI-Powered GIS Last-Mile Connectivity Planner</h1>
                    <p>GP-Constrained Fiber Route Optimization System</p>
                </div>
            </header>
            <div className="dashboard-container">
                <div className="map-panel">
                    <MapView
                        gpBoundary={gpBoundary}
                        infraNodes={infraNodes}
                        selectedInfra={selectedInfra}
                        setSelectedInfra={setSelectedInfra}
                        customerLocation={customerLocation}
                        setCustomerLocation={setCustomerLocation}
                        routeInfo={routeInfo}
                        isLoading={isLoading}
                    />
                </div>
                <div className="control-panel">
                    <ControlPanel
                        selectedInfra={selectedInfra}
                        customerLocation={customerLocation}
                        onComputeRoute={handleComputeRoute}
                        onResetRoute={handleResetRoute}
                        isLoading={isLoading}
                        errorMsg={errorMsg}
                        routeInfo={routeInfo}
                    />
                </div>
            </div>
        </div>
    );
}

export default App;
