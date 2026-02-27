import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
});

export const getGPBoundary = () => api.get('/gp-boundary');
export const getInfraNodes = () => api.get('/infra-nodes');
export const computeRoute = (data) => api.post('/compute-route', data);
