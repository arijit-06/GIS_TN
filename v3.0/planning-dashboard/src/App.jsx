import React, { useState, useEffect } from "react";
import MapView from "./components/MapView";
import ControlPanel from "./components/ControlPanel";
import { computeLocalRoute, loadPlannerData } from "./services/localPlanner";

function App() {
    const [gpBoundary, setGpBoundary] = useState(null);
    const [roads, setRoads] = useState(null);
    const [infraNodes, setInfraNodes] = useState([]);
    const [graph, setGraph] = useState(null);
    const [selectedInfra, setSelectedInfra] = useState(null);
    const [customerLocation, setCustomerLocation] = useState(null);
    const [routeInfo, setRouteInfo] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isBootstrapping, setIsBootstrapping] = useState(true);
    const [errorMsg, setErrorMsg] = useState(null);
    const [systemStats, setSystemStats] = useState({
        nodeCount: 0,
        edgeCount: 0,
        roadFeatureCount: 0,
    });

    useEffect(() => {
        const loadInitialData = async () => {
            try {
                setIsBootstrapping(true);
                const { gpBoundary, roads, infraNodes, graph } = await loadPlannerData();
                setGpBoundary(gpBoundary);
                setRoads(roads);
                setInfraNodes(infraNodes);
                setGraph(graph);
                setSystemStats({
                    nodeCount: graph.nodes.size,
                    edgeCount: graph.edgeCount,
                    roadFeatureCount: roads?.features?.length || 0,
                });
            } catch (err) {
                console.error("Failed to load local planner data", err);
                setErrorMsg("Failed to load /data files. Check gp_boundary.geojson, infra_nodes.json, and roads.geojson.");
            } finally {
                setIsBootstrapping(false);
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
        if (!graph) {
            handleError("Road graph not ready yet. Please wait for data loading to complete.");
            return;
        }
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

            const computed = computeLocalRoute({
                graph,
                infraNode: selectedInfra,
                customerLocation,
            });
            if (computed.error) {
                handleError(computed.error);
                setRouteInfo(null);
                return;
            }
            setRouteInfo(computed);
        } catch (err) {
            handleError("An error occurred while computing the route.");
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
                    <h1>Unified Fiber Planning Dashboard</h1>
                    <p>Standalone GIS planner (local data + local routing engine)</p>
                </div>
            </header>
            <div className="dashboard-container">
                <div className="map-panel">
                    <MapView
                        gpBoundary={gpBoundary}
                        roads={roads}
                        infraNodes={infraNodes}
                        selectedInfra={selectedInfra}
                        setSelectedInfra={setSelectedInfra}
                        customerLocation={customerLocation}
                        setCustomerLocation={setCustomerLocation}
                        routeInfo={routeInfo}
                        isLoading={isLoading || isBootstrapping}
                    />
                </div>
                <div className="control-panel">
                    <ControlPanel
                        systemStats={systemStats}
                        selectedInfra={selectedInfra}
                        customerLocation={customerLocation}
                        onComputeRoute={handleComputeRoute}
                        onResetRoute={handleResetRoute}
                        isLoading={isLoading || isBootstrapping}
                        errorMsg={errorMsg}
                        routeInfo={routeInfo}
                    />
                </div>
            </div>
        </div>
    );
}

export default App;
