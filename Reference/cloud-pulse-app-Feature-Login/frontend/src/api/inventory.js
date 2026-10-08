import { apiClient } from './api';

// --- Raw Backend API Calls ---
const getInventorySummary = async (account) => {
  const response = await apiClient.get('/inventory/summary', { params: { account } });
  return response.data;
};

// Note: These functions return the axios response directly, which contains { data: ... }
// This matches what the components expect.

const getInventoryTrend = async (account, resourceType, days) => {
  const params = { account };
  if (resourceType) params.resource_type = resourceType;
  if (days) params.days = days;
  const response = await apiClient.get('/inventory/trend', { params });
  return response.data;
};

const getInventoryChanges = async (account, days, change_type, search, region, linked_account, tag, limit, offset) => {
  const params = { account };
  if (days) params.days = days;
  if (change_type && change_type !== 'All') params.change_type = change_type;
  if (search) params.search = search;
  if (region && region !== 'All Regions') params.region = region;
  if (linked_account && linked_account !== 'All Accounts') params.linked_account = linked_account;
  if (tag && tag !== 'All') params.tag = tag;
  if (limit) params.limit = limit;
  if (offset !== undefined) params.offset = offset;
  const response = await apiClient.get('/inventory/changes', { params });
  return response.data;
};



export const getHeatmapActivity = async (account, resourceType) => {
  const params = { account };
  if (resourceType) params.resource_type = resourceType;
  const response = await apiClient.get('/inventory/activity-heatmap', { params });
  return response.data;
};

export const wipeDatabase = async (account, provider) => {
  const params = {};
  if (account) params.account = account;
  if (provider) params.provider = provider;
  const response = await apiClient.delete('/inventory/wipe', { params });
  return response.data;
};

const clientTriggerSync = async (provider, configId) => {
  const response = await apiClient.post(`/inventory/sync?provider=${provider}&config_id=${configId}`);
  return response.data;
};

export const getInventorySyncStatus = async (account) => {
  const response = await apiClient.get('/inventory/sync-status', { params: { account_name: account } });
  return response.data;
};

// --- Frontend UI Adapters ---

export const getSummary = async (provider, account) => {
  const raw = await getInventorySummary(account);
  const data = {
    total: raw.total_active || 0,
    billable: raw.billable || 0,
    non_billable: raw.non_billable || 0,
    new_today: raw.new_today || 0,
    deleted_today: raw.deleted_today || 0,
    type_breakdown: Object.keys(raw.by_type || {}).map(k => ({ type: k, count: raw.by_type[k] })),
    region_breakdown: Object.keys(raw.by_region || {}).map(k => ({ region: k, count: raw.by_region[k] }))
  };
  return { data };
};

export const getAdvancedSummary = async (account, provider, region, linked_account, tag, resourceType) => {
  const params = { account, provider };
  if (region && region !== 'All Regions') params.region = region;
  if (linked_account && linked_account !== 'All Accounts') params.linked_account = linked_account;
  if (tag && tag !== 'All') params.tag = tag;
  if (resourceType) params.resource_type = resourceType;

  const response = await apiClient.get('/inventory/summary/advanced', { params });
  return { data: response.data };
};

export const getFilterOptions = async (account, provider) => {
  const response = await apiClient.get('/inventory/filter-options', {
    params: { account, provider }
  });
  return { data: response.data };
};

export const getChanges = async (provider, configId, days, account, change_type, search, region, linked_account, tag, limit = 50, offset = 0) => {
  const raw = await getInventoryChanges(account, days, change_type, search, region, linked_account, tag, limit, offset);
  const changes = (raw.changes || raw).map(c => ({
    change_type: c.change_type,
    resource_name: c.name || c.native_id,
    native_id: c.native_id,
    resource_type: c.resource_type || 'unknown',
    region: c.region || 'unknown',
    provider: provider,
    details: c.details,
    detected_at: c.detected_at || c.timestamp
  }));
  return { data: { ...raw, changes } };
};

export const getTrend = async (provider, configId, days, account, resourceType = null) => {
  const raw = await getInventoryTrend(account, resourceType, days);

  const trend = raw.map(t => {
    return {
      raw_date: t.snapshot_date,
      date: t.snapshot_date, // Kept for backwards compatibility with useMemo filtering
      total: t.total_active_count
    };
  });

  return { data: { trend } };
};

export const getResources = async (provider, configId, type, region, billable, account, status = 'active', limit = 50, offset = 0, linked_account, tag, time_filter) => {
  const params = { status, limit, offset };
  if (account) params.account = account;
  if (provider) params.provider = provider;
  if (type && type !== 'All') params.resource_type = type;
  if (region && region !== 'All' && region !== 'All Regions') params.region = region;
  if (billable && billable !== 'All') params.billable = billable === 'true';
  if (linked_account && linked_account !== 'All Accounts') params.linked_account = linked_account;
  if (tag && tag !== 'All') params.tag = tag;
  if (time_filter && time_filter !== 'All') params.time_filter = time_filter;

  const response = await apiClient.get('/inventory/resources', { params });
  const raw = response.data;

  // The backend now returns { total, page, resources }
  const resourcesList = raw.resources || raw; // fallback for backwards compat if needed

  const resources = resourcesList.map(r => ({
    native_id: r.native_id,
    name: r.name,
    tags: typeof r.tags === 'string' ? (() => { try { return JSON.parse(r.tags) } catch (e) { return {} } })() : (r.tags || {}),
    resource_type: r.resource_type,
    region: r.region,
    billable: r.billable,
    provider: provider,
    first_seen_date: r.first_seen_date,
    deleted_at: r.deleted_at
  }));

  return { 
    data: { 
      resources, 
      total: raw.total || resources.length, 
      page: raw.page || 1,
      region_breakdown: raw.region_breakdown,
      type_breakdown: raw.type_breakdown 
    } 
  };
};

export const triggerSync = async (provider, configId) => {
  if (!configId) {
    const err = new Error("No config ID provided for sync.");
    err.response = { data: { detail: "No config ID provided for sync." } };
    throw err;
  }

  const raw = await clientTriggerSync(provider, configId);
  return {
    data: {
      metrics: {
        total_active: raw.metrics?.total_active || 0,
        created: raw.metrics?.created || 0,
        deleted: raw.metrics?.deleted || 0,
        updated: raw.metrics?.updated || 0
      }
    }
  };
};
