import React from 'react';

const RouteInfo = ({ routeInfo }) => {
    if (!routeInfo) return null;

    // Format the estimated cost nicely with commas
    const formattedCost = new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2
    }).format(routeInfo.estimated_cost);

    return (
        <div className="route-info-card">
            <div className="info-row">
                <span className="label">Total Distance</span>
                <span className="value">{(routeInfo.distance_meters).toFixed(2)} meters</span>
            </div>
            <div className="info-row">
                <span className="label">Estimated Cost</span>
                <span className="value cost-value">{formattedCost}</span>
            </div>
            <div className="info-row">
                <span className="label">Execution Time</span>
                <span className="value">{routeInfo.execution_time_seconds}s</span>
            </div>
        </div>
    );
};

export default RouteInfo;
