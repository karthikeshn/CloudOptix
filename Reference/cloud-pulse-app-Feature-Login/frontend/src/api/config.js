import { apiClient } from './api';

export const listConfigs = async () => {
  const response = await apiClient.get('/cloud-config/');
  return { data: { configs: response.data } };
};

export const createConfig = async (payload) => {
  const response = await apiClient.post('/cloud-config/', payload);
  return response.data;
};

export const verifyConfig = async (id) => {
  try {
    const response = await apiClient.post(`/cloud-config/${id}/verify`);
    return { data: { verified: true, message: response.data.message } };
  } catch (error) {
    return { data: { verified: false, message: error.response?.data?.detail || "Verification failed" } };
  }
};

export const deleteConfig = async (id) => {
  const response = await apiClient.delete(`/cloud-config/${id}`);
  return response.data;
};

export const updateAutoSync = async (id, enabled, time, timezone) => {
  const response = await apiClient.patch(`/cloud-config/${id}/auto-sync`, { enabled, time, timezone });
  return response.data;
};

export const editConfig = async (id, payload) => {
  const response = await apiClient.patch(`/cloud-config/${id}`, payload);
  return response.data;
};

export const updateCredentials = async (id, credentials) => {
  const response = await apiClient.patch(`/cloud-config/${id}/credentials`, { credentials });
  return response.data;
};
