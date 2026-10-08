import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { DatabaseOff, Search, CheckSquare, RefreshCw , EyeOff, Database } from 'lucide-react';
import { Virtuoso } from 'react-virtuoso';
import { FilterBar } from '../../components/ui/FilterBar';
import { EmptyState } from '../../components/ui/EmptyState';
import { toast } from 'sonner';
import { listResources, toggleVisibility, getFilterOptions } from '../../api/control';
import { listConfigs } from '../../api/config';
import { useControlSync } from '../../utils/syncManager';
import { buildResourceTree, buildResourceMap } from '../../utils/resource-tree';
import { SettingsRow } from './SettingsRow';
import { NotificationBell } from '../../components/ui/NotificationBell';
import { AwsRegionSelect } from '../../components/ui/AwsRegionSelect';
import { ControlResourceDetailModal } from '../control/ControlResourceDetailModal';

export default function AdminPage() {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [detailResource, setDetailResource] = useState(null);
  
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  // Global filters
  const [topFilters, setTopFilters] = useState({
    provider: localStorage.getItem('pulse_admin_provider') || 'AWS',
    account: localStorage.getItem('pulse_admin_account') || '',
    region: 'All Regions',
    tag: 'All Tags'
  });

  const [filter, setFilter] = useState({
    group: 'All'
  });

  const { syncing, startControlSync } = useControlSync(topFilters?.account);
  const [syncRegions, setSyncRegions] = useState(['all']);
  const [verifiedConfigs, setVerifiedConfigs] = useState([]);
  const [availableRegions, setAvailableRegions] = useState(['All Regions']);
  const [availableTags, setAvailableTags] = useState(['All Tags']);
  const [expandedRowIds, setExpandedRowIds] = useState(new Set());

  const availableProviders = ['AWS', 'AZURE', 'GCP'];
  const filteredConfigs = verifiedConfigs.filter(c => (c.provider || '').toUpperCase() === topFilters.provider);
  const availableAccounts = filteredConfigs.map(c => c.account_name);

  useEffect(() => {
    if (topFilters.provider) localStorage.setItem('pulse_admin_provider', topFilters.provider);
    if (topFilters.account) localStorage.setItem('pulse_admin_account', topFilters.account);
  }, [topFilters.provider, topFilters.account]);

  useEffect(() => {
    const handleProviderChange = () => {
      const p = localStorage.getItem('pulse_admin_provider') || 'AWS';
      // Need to re-trigger account logic based on new provider, which handleTopFilterChange does
      handleTopFilterChange('provider', p);
    };
    window.addEventListener('app:provider-change', handleProviderChange);
    return () => window.removeEventListener('app:provider-change', handleProviderChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifiedConfigs, topFilters.account]);

  useEffect(() => {
    loadConfigs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.account, topFilters.provider, topFilters.region, topFilters.tag]);

  const loadConfigs = async () => {
    try {
      const res = await listConfigs();
      const configs = res.data.configs || [];
      const vConfigs = configs.filter(c => c.verified && (c.active_modules ?? 'inventory,control').includes('control'));
      setVerifiedConfigs(vConfigs);

      if (vConfigs.length > 0) {
        const savedAccount = localStorage.getItem('pulse_admin_account');
        const savedMatch = vConfigs.find(c => c.account_name === savedAccount);

        let currentProvider = topFilters.provider;
        let currentAccount = topFilters.account;

        if (savedMatch) {
          currentProvider = savedMatch.provider ? savedMatch.provider.toUpperCase() : 'AWS';
          currentAccount = savedMatch.account_name;
          setTopFilters(prev => ({ ...prev, provider: currentProvider, account: currentAccount }));
        }

        const providerConfigs = vConfigs.filter(c => (c.provider || '').toUpperCase() === currentProvider);

        if (providerConfigs.length > 0) {
          const hasCurrentAccount = providerConfigs.find(c => c.account_name === currentAccount);
          if (!hasCurrentAccount) {
            setTopFilters(prev => ({ ...prev, account: providerConfigs[0].account_name }));
          }
        } else {
          setTopFilters(prev => ({ ...prev, account: '' }));
        }
      } else {
        setTopFilters(prev => ({ ...prev, account: '' }));
      }
    } catch (err) {
      console.error("Failed to load configs", err);
    }
  };

  const loadOptions = async () => {
    try {
      const options = await getFilterOptions({ account: topFilters.account, provider: topFilters.provider });
      if (options) {
        setAvailableRegions(['All Regions', ...(options.regions || [])]);
        setAvailableTags(['All Tags', ...(options.tags || [])]);
      }
    } catch (err) {
      console.error("Failed to load filter options", err);
    }
  };

  const handleTopFilterChange = (key, value) => {
    if (key === 'provider') {
      if (topFilters.provider === value) return; // prevent loop
      
      const filtered = verifiedConfigs.filter(c => (c.provider || '').toUpperCase() === value);
      let newAccount = '';

      const stillValid = filtered.find(c => c.account_name === topFilters.account);
      if (!stillValid && filtered.length > 0) {
        newAccount = filtered[0].account_name;
      } else if (stillValid) {
        newAccount = topFilters.account;
      }

      setTopFilters(prev => ({ ...prev, provider: value, account: newAccount }));
      
      // Update global context so the sidebar updates too if we change provider here
      localStorage.setItem('pulse_admin_provider', value);
      localStorage.setItem('pulse_control_provider', value);
      window.dispatchEvent(new Event('app:provider-change'));
    } else {
      setTopFilters(prev => ({ ...prev, [key]: value }));
    }
  };

  const handleSync = () => {
    const regionParam = syncRegions.includes('all') ? 'all' : syncRegions.join(',');
    startControlSync(topFilters.account, regionParam, () => {
      setHasMore(true);
      setOffset(0);
      loadResources(true);
    });
  };

  const toggleRow = (id) => {
    setExpandedRowIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const loadResources = async (reset = false) => {
    if (loading || (!hasMore && !reset)) return;
    setLoading(true);
    const currentOffset = reset ? 0 : offset;

    try {
      const data = await listResources(topFilters, LIMIT, currentOffset, true);
      const mapped = (data || []).map(s => ({
        ...s,
        name: s.resource_name || s.resource_id,
        cloud_provider: s.cloud_provider || 'aws',
        instance_spec: s.instance_spec || 'unknown',
        status: s.status || 'UNKNOWN',
        schedule: {
          is_automation_enabled: s.is_automation_enabled,
          start_time: s.start_time,
          stop_time: s.stop_time,
          timezone: s.timezone,
          pattern: s.schedule_pattern,
          owner: s.owner_email
        }
      }));

      if (mapped.length < LIMIT) {
        setHasMore(false);
      } else {
        setHasMore(true);
      }

      setResources(prev => {
        if (reset) return mapped;
        const existingIds = new Set(prev.map(r => r.resource_id));
        return [...prev, ...mapped.filter(r => !existingIds.has(r.resource_id))];
      });
      setOffset(currentOffset + mapped.length);
    } catch (error) {
      console.error(error);
      toast.error('Failed to load resources for settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setHasMore(true);
    setOffset(0);
    loadResources(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.account, topFilters.provider, topFilters.region, topFilters.tag]);

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadResources(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, offset, topFilters]);

  const getResourceAndChildrenIds = (resourceId, allResources) => {
    const { resourceMap } = buildResourceMap(allResources);
    const getIds = (node) => {
      let ids = [node.resource_id];
      for (const child of node.children) {
        ids = ids.concat(getIds(child));
      }
      return ids;
    };
    const targetNode = resourceMap.get(resourceId);
    return targetNode ? getIds(targetNode) : [resourceId];
  };

  const handleToggle = async (resource) => {
    const newState = !resource.is_visible;
    const targetIds = getResourceAndChildrenIds(resource.resource_id, resources);
    try {
      await toggleVisibility(targetIds, newState);
      toast.success(`${resource.name} ${targetIds.length > 1 ? `and ${targetIds.length - 1} nested items` : ''} now ${newState ? 'visible' : 'hidden'}`);
      setResources(prev => prev.map(r => 
        targetIds.includes(r.resource_id) ? { ...r, is_visible: newState } : r
      ));
    } catch (error) {
      console.error(error);
      toast.error('Failed to update visibility');
    }
  };

  const handleToggleAll = async (newVisibility) => {
    const allFilteredIds = resources
      .filter(r => filter.group === 'All' || getGroup(r.service_type) === filter.group)
      .filter(r =>
        (r.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.resource_id || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
      .map(r => r.resource_id);

    if (allFilteredIds.length === 0) return;
    try {
      await toggleVisibility(allFilteredIds, newVisibility);
      toast.success(`Updated visibility for ${allFilteredIds.length} resources`);
      setResources(prev => prev.map(r => 
        allFilteredIds.includes(r.resource_id) ? { ...r, is_visible: newVisibility } : r
      ));
    } catch (error) {
      console.error(error);
      toast.error('Failed to update visibility in bulk');
    }
  };

  const getGroup = (type) => {
    const t = (type || '').toUpperCase();
    if (['RDS', 'AURORA'].includes(t)) return 'RDS';
    if (['EC2'].includes(t)) return 'EC2';
    return t;
  };

  const uniqueGroups = Array.from(new Set(resources.map(r => getGroup(r.service_type)))).sort();
  const groupOptions = [
    { label: 'All Groups', value: 'All' },
    ...uniqueGroups.map(g => ({ label: g, value: g }))
  ];

  const filteredResources = resources
    .filter(r => filter.group === 'All' || getGroup(r.service_type) === filter.group)
    .filter(r =>
      (r.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (r.resource_id || '').toLowerCase().includes(searchQuery.toLowerCase())
    );

  const treeData = useMemo(() => buildResourceTree(filteredResources, true, expandedRowIds), [filteredResources, expandedRowIds]);

  return (
    <>
      <div className="sticky -top-6 h-6 -mx-6 -mt-6 bg-[#0a0a0f]/80 backdrop-blur-md z-30 pointer-events-none" />
      <div className="space-y-6 relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            {topFilters.provider && (
              <img src={`/${topFilters.provider.toLowerCase()}-logo.svg`} alt="" className="h-10 w-10 object-contain shrink-0" />
            )}
            <div>
              <h1 className="text-xl font-semibold flex items-center gap-3 text-[#e4e4e7] tracking-tight">
                Control Admin
              </h1>
              <p className="text-[11px] text-[#a1a1aa] mt-1">Manage global resource visibility and run discovery syncs</p>
            </div>
            </div>
            <div className="flex items-center gap-4">
              <NotificationBell />
              <div className="flex items-center gap-2">
                <AwsRegionSelect value={syncRegions} onChange={setSyncRegions} disabled={syncing} />
                <button onClick={handleSync} disabled={syncing} className="flex items-center gap-2 px-3 py-1.5 text-[11px] uppercase tracking-wider font-semibold bg-transparent border border-zinc-700 text-zinc-300 rounded-md hover:bg-zinc-800 disabled:opacity-50 transition-colors">
                  <RefreshCw className={`h-3 w-3 ${syncing ? 'animate-spin' : ''}`} />{syncing ? 'Syncing...' : 'Sync Now'}
                </button>
              </div>
            </div>
          </div>

        <FilterBar
          filters={[
            { label: "Provider:", value: topFilters.provider, onChange: v => handleTopFilterChange('provider', v), options: availableProviders.map(p => ({ label: p, value: p })), width: "max-w-[110px]" },
            { label: "Account:", value: topFilters.account, onChange: v => handleTopFilterChange('account', v), options: availableAccounts.map(a => ({ label: a, value: a })), width: "max-w-[150px]" },
            { label: "Region:", value: topFilters.region, onChange: v => handleTopFilterChange('region', v), options: availableRegions.map(r => ({ label: r, value: r })), width: "max-w-[120px]" },
            { label: "Tag:", value: topFilters.tag, onChange: v => handleTopFilterChange('tag', v), options: availableTags.map(t => ({ label: t, value: t })), width: "max-w-[150px]" }
          ]}
        />

        {['AZURE', 'GCP'].includes(topFilters.provider) ? (
          <div className="flex flex-col items-center justify-center pt-28 pb-16 animate-in fade-in duration-500">
            <div className="w-20 h-20 mb-6 rounded-3xl bg-[#15181e] flex items-center justify-center border border-zinc-800/80 shadow-2xl">
              <img src={`/${topFilters.provider.toLowerCase()}-logo.svg`} alt={topFilters.provider} className="h-10 w-10 object-contain opacity-60 grayscale-[50%]" />
            </div>
            <h2 className="text-2xl font-bold text-[#e4e4e7] tracking-tight mb-3">Discovery for {topFilters.provider === 'AZURE' ? 'Azure' : 'Google Cloud'} is Coming Soon</h2>
            <p className="text-[13px] text-[#8b949e] max-w-md text-center leading-relaxed">
              We are currently building automated resource discovery and sync for {topFilters.provider === 'AZURE' ? 'Microsoft Azure' : 'Google Cloud'}. Stay tuned for updates!
            </p>
          </div>
        ) : (
          <div className="space-y-4 animate-in fade-in duration-300 w-full pt-4">
          <div className="flex items-center justify-between mb-2">
            <FilterBar
              showLabel={true}
              className="flex flex-wrap items-center gap-4"
              filters={[
                { label: "Group:", value: filter.group, onChange: v => setFilter({ ...filter, group: v }), options: groupOptions, width: "max-w-[150px]" }
              ]}
            />
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search resources..."
                  className="w-full pl-9 pr-3 py-1.5 bg-[#1e1e24] border border-zinc-800 rounded-lg text-xs text-white placeholder-zinc-500 outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>
          </div>

          <div className="bg-[#111114] border border-[#1f1f24] rounded-2xl shadow-xl [overflow:clip]">
            <div className="flex items-center justify-between p-4 border-b border-zinc-800/80 bg-zinc-900/50">
              <div className="text-sm font-medium text-zinc-400">
                {treeData.length} Resource{treeData.length !== 1 && 's'} Found
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleToggleAll(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-bold rounded-lg transition-colors bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-700 hover:bg-zinc-700 uppercase tracking-wider"
                >
                  <CheckSquare className="h-3 w-3" /> Show All
                </button>
                <button
                  onClick={() => handleToggleAll(false)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-bold rounded-lg transition-colors bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-700 hover:bg-zinc-700 uppercase tracking-wider"
                >
                  <EyeOff className="h-3 w-3" /> Hide All
                </button>
              </div>
            </div>

            {(treeData.length === 0 && (loading || (offset === 0 && hasMore))) ? (
              <div className="p-4 space-y-4">
                <div className="h-16 bg-zinc-800/50 animate-pulse rounded-xl" />
                <div className="h-16 bg-zinc-800/50 animate-pulse rounded-xl" />
                <div className="h-16 bg-zinc-800/50 animate-pulse rounded-xl" />
              </div>
            ) : treeData.length > 0 ? (
              <Virtuoso
                useWindowScroll={!document.getElementById('main-scroll-container')}
                customScrollParent={document.getElementById('main-scroll-container')}
                data={treeData}
                endReached={loadMore}
                itemContent={(index, r) => (
                  <SettingsRow
                    key={r.resource_id}
                    r={r}
                    isGroupView={true}
                    toggleRow={toggleRow}
                    handleToggle={handleToggle}
                    setDetailResource={setDetailResource}
                  />
                )}
              />
            ) : (
              <EmptyState icon={Database} message="No resources found matching filters." height="h-[400px]" />
            )}
          </div>
          </div>
        )}
      </div>
      
      {detailResource && (
        <ControlResourceDetailModal 
          resource={detailResource} 
          onClose={() => setDetailResource(null)} 
        />
      )}
    </>
  );
}
