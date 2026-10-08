import { apiClient } from './api';

export const listSchedules = async () => {
  const response = await apiClient.get('/control/schedules');
  return response.data;
};

export const syncResources = async (accountName, region = 'all') => {
  const params = {};
  if (accountName && accountName !== 'All Accounts') params.account_name = accountName;
  if (region && region !== 'all') params.region = region;
  
  const response = await apiClient.post('/control/sync', null, { params });
  return response.data;
};

export const getControlSyncStatus = async (accountName) => {
  const params = accountName && accountName !== 'All Accounts' ? { account_name: accountName } : {};
  const response = await apiClient.get('/control/sync-status', { params });
  return response.data;
};

export const listResources = async (filters = {}, limit = 50, offset = 0, showHidden = false) => {
  const params = { limit, offset };
  if (showHidden) params.show_hidden = true;
  if (filters.account && filters.account !== 'All Accounts') params.account_name = filters.account;
  if (filters.provider && filters.provider !== 'All Providers') params.provider = filters.provider;
  if (filters.region && filters.region !== 'All Regions') params.region = filters.region;
  if (filters.tag && filters.tag !== 'All Tags') params.tag = filters.tag;
  
  const response = await apiClient.get('/control/resources', { params });
  return response.data;
};

export const getControlSummary = async (filters = {}) => {
  const params = {};
  if (filters.account && filters.account !== 'All Accounts') params.account_name = filters.account;
  if (filters.provider && filters.provider !== 'All Providers') params.provider = filters.provider;
  if (filters.region && filters.region !== 'All Regions') params.region = filters.region;
  if (filters.tag && filters.tag !== 'All Tags') params.tag = filters.tag;
  if (filters.serviceType) params.service_type = filters.serviceType;
  if (filters.status && filters.status !== 'All') params.status = filters.status;
  
  const response = await apiClient.get('/control/summary', { params });
  return response.data;
};

export const saveSchedule = async (payload) => {
  const response = await apiClient.post('/control/schedule', payload);
  return response.data;
};

export const getFilterOptions = async (filters = {}) => {
  const params = {};
  if (filters.account && filters.account !== 'All Accounts') params.account_name = filters.account;
  if (filters.provider && filters.provider !== 'All Providers') params.provider = filters.provider;
  
  const response = await apiClient.get('/control/filter-options', { params });
  return response.data;
};

export const togglePower = async (payload) => {
  const response = await apiClient.post('/control/toggle-power', payload);
  return response.data;
};

export const logAction = async (payload) => {
  const response = await apiClient.post('/control/log-action', payload);
  return response.data;
};

export const listAuditLogs = async (filters = {}, limit = 50, offset = 0) => {
  const params = { limit, offset };
  if (filters.account && filters.account !== 'All Accounts') params.account_name = filters.account;
  if (filters.eventType && filters.eventType !== 'All') params.event_type = filters.eventType;
  if (filters.search) params.search = filters.search;

  const response = await apiClient.get('/control/audit-logs', { params });
  return response.data;
};

export const getDbState = async (resourceId) => {
  const response = await apiClient.get('/control/db-state/' + encodeURIComponent(resourceId));
  return response.data;
};

export const toggleVisibility = async (resourceIds, isVisible) => {
  const response = await apiClient.post('/control/toggle-visibility', {
    resource_ids: resourceIds,
    is_visible: isVisible
  });
  return response.data;
};
