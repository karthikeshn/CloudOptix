import axios from 'axios';
import { toast } from 'sonner';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || `http://${window.location.hostname}:8000/api/v1`;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0'
  },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('cloud_pulse_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Intercept responses to cleanly handle backend downtime
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // If the backend is not running, Axios throws a 'Network Error' without a response object
    if (error.message === 'Network Error' || !error.response) {
      toast.error('Backend service is unreachable. Please check your connection or restart the server.', {
        id: 'global-network-error', // prevents spamming multiple toasts
        duration: 5000,
      });
      // Return a clean error instead of the raw Axios trace
      return Promise.reject(new Error('Backend connection offline.'));
    }
    // Handle Unauthorized
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('cloud_pulse_token');
      // We can emit an event or dispatch if using Redux, but for now reload is simplest
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    
    // Pass through other standard HTTP errors (like 400s or 500s)
    return Promise.reject(error);
  }
);

export const login = async (username, password) => {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);
  return axios.post(`${API_BASE_URL}/auth/login`, formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  });
};
