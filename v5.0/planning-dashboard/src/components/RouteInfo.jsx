import React from "react";

const RouteInfo = ({ routeInfo }) => {
    if (!routeInfo) return null;

    // Format the estimated cost nicely with commas
    const formattedCost = new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2
    }).format(routeInfo.estimatedCost);

    return (
        <div className="route-info-card">
            <div className="info-row">
                <span className="label">Total Distance</span>
                <span className="value">{(routeInfo.distanceMeters).toFixed(2)} meters</span>
            </div>
            <div className="info-row">
                <span className="label">Estimated Cost</span>
                <span className="value cost-value">{formattedCost}</span>
            </div>
            <div className="info-row">
                <span className="label">Execution Time</span>
                <span className="value">{routeInfo.executionTimeSeconds}s</span>
            </div>
            <div className="info-row">
                <span className="label">Infra Snap Distance</span>
                <span className="value">{routeInfo.startSnapMeters} m</span>
            </div>
            <div className="info-row">
                <span className="label">Customer Snap Distance</span>
                <span className="value">{routeInfo.endSnapMeters} m</span>
            </div>
        </div>
    );
};

export default RouteInfo;
