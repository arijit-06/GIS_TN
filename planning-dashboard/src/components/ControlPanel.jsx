import React from 'react';
import RouteInfo from './RouteInfo';

const ControlPanel = ({
    selectedInfra,
    customerLocation,
    onComputeRoute,
    onResetRoute,
    isLoading,
    errorMsg,
    routeInfo
}) => {
    return (
        <>
            <div className="panel-header">
                <h1>Route Planning Dashboard</h1>
            </div>

            <div className="panel-content">
                <div className="section">
                    <h2>Infrastructure Node</h2>
                    <div className={`status-badge ${selectedInfra ? 'selected' : ''}`}>
                        {selectedInfra ? `Selected: ${selectedInfra.id}` : 'None Selected'}
                    </div>
                </div>

                <div className="section">
                    <h2>Customer Location</h2>
                    <div className={`status-badge ${customerLocation ? 'selected' : ''}`}>
                        {customerLocation
                            ? `${customerLocation.lat.toFixed(6)}, ${customerLocation.lng.toFixed(6)}`
                            : 'Click map to place target'}
                    </div>
                </div>

                {errorMsg && (
                    <div className="error-message">
                        {errorMsg}
                    </div>
                )}

                <div className="section action-buttons">
                    <button
                        className="compute-btn"
                        onClick={onComputeRoute}
                        disabled={isLoading || !selectedInfra || !customerLocation}
                    >
                        {isLoading ? <div className="spinner"></div> : 'Compute Route'}
                    </button>
                    <button
                        className="reset-btn"
                        onClick={onResetRoute}
                        disabled={isLoading || (!routeInfo && !customerLocation && !errorMsg)}
                    >
                        Reset Route
                    </button>
                </div>

                {routeInfo && (
                    <div className="section">
                        <h2>Route Details</h2>
                        <RouteInfo routeInfo={routeInfo} />
                    </div>
                )}
            </div>
        </>
    );
};

export default ControlPanel;
