import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { getAdvancedSummary, getTrend, wipeDatabase, getFilterOptions } from '../../api/inventory';
import { useInventorySync } from '../../utils/syncManager';
import { apiClient } from '../../api/api';
import { OverviewTab as Overview } from './tabs/OverviewTab';
import { ChangesTab as Changes } from './tabs/ChangesTab';
import { ResourcesTab as Resources } from './tabs/ResourcesTab';
import { DeletedTab as Deleted } from './tabs/DeletedTab';
import { ResourceDetailModal } from './ResourceDetailModal';
import TopFilters from './TopFilters';
import { getStrategy } from '../../utils/cloud-strategies';
import { NotificationBell } from '../../components/ui/NotificationBell';
import { ScrollToTopButton } from '../../components/ui/ScrollToTopButton';

export default function InventoryPage() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const activeConfig = accounts.find(a => a.account_name === selectedAccount);

  const [topFilters, setTopFilters] = useState({
    provider: '',
    region: 'All Regions',
    linked: 'All Accounts',
    tag: 'All',
    range: 30
  });

  const [serverSummary, setServerSummary] = useState(null);
  const [filterOptions, setFilterOptions] = useState({ availableRegions: [], availableLinked: [], availableTags: [] });
  const [trend, setTrend] = useState([]);

  const [loadingSummary, setLoadingSummary] = useState(true);
  const { syncing, startInventorySync } = useInventorySync(selectedAccount);

  // Fetch Filter Options once per account
  useEffect(() => {
    if (!selectedAccount) return;
    const activeConfig = accounts.find(a => a.account_name === selectedAccount);
    if (!activeConfig) return;

    getFilterOptions(selectedAccount, activeConfig.provider).then(res => {
      setFilterOptions({
        availableRegions: res.data.regions || [],
        availableLinked: res.data.linked_accounts || [],
        availableTags: res.data.tags || []
      });
    }).catch(e => console.error(e));
  }, [selectedAccount, accounts]);

  // Fetch Summary when top filters change
  const loadSummary = useCallback(async () => {
    if (!selectedAccount) return;
    const activeConfig = accounts.find(a => a.account_name === selectedAccount);
    if (!activeConfig) return;

    setLoadingSummary(true);
    try {
      const summaryRes = await getAdvancedSummary(
        selectedAccount,
        activeConfig.provider,
        topFilters.region,
        topFilters.linked,
        topFilters.tag
      );
      setServerSummary(summaryRes.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSummary(false);
    }
  }, [selectedAccount, accounts, topFilters.region, topFilters.linked, topFilters.tag]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const [syncRefreshTrigger, setSyncRefreshTrigger] = useState(0);

  useEffect(() => {
    const handleGlobalRefresh = () => {
      loadSummary();
      setSyncRefreshTrigger(prev => prev + 1);
    };
    window.addEventListener('app:refresh-data', handleGlobalRefresh);
    return () => window.removeEventListener('app:refresh-data', handleGlobalRefresh);
  }, [loadSummary]);
  const [tab, setTab] = useState(() => localStorage.getItem('pulse_inventory_active_tab') || 'overview');
  const [resourceFilter, setResourceFilter] = useState({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'All' });
  const [deletedFilter, setDeletedFilter] = useState({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'All' });
  const filter = tab === 'deleted' ? deletedFilter : resourceFilter;
  const [selectedResource, setSelectedResource] = useState(null);
  const [crossFilterType, setCrossFilterType] = useState(null);
  const [pieGroupFilter, setPieGroupFilter] = useState(null);

  useEffect(() => {
    if (selectedAccount && !loadingSummary) {
      const activeConfig = accounts.find(a => a.account_name === selectedAccount);
      if (activeConfig) {
        getTrend(activeConfig.provider, null, 30, selectedAccount, crossFilterType).then(t => setTrend(t.data?.trend || []));
      }
    }
  }, [crossFilterType, selectedAccount, accounts, loadingSummary]);

  useEffect(() => {
    apiClient.get('/cloud-config/').then(res => {
      let accs = res.data || [];
      accs = accs.filter(a => (a.active_modules ?? 'inventory,control').includes('inventory'));
      setAccounts(accs);
      if (accs.length > 0) {
        const savedAccountName = localStorage.getItem('pulse_inventory_account');
        const match = accs.find(a => a.account_name === savedAccountName);
        if (match) {
          setSelectedAccount(match.account_name);
          setTopFilters(prev => ({ ...prev, provider: (match.provider || '').toUpperCase() }));
        } else {
          setSelectedAccount(accs[0].account_name);
          setTopFilters(prev => ({ ...prev, provider: (accs[0].provider || '').toUpperCase() }));
        }
      } else {
        setLoadingSummary(false);
      }
    });
  }, []);

  useEffect(() => {
    if (selectedAccount) {
      localStorage.setItem('pulse_inventory_account', selectedAccount);
      setResourceFilter({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'All' });
      setDeletedFilter({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'All' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccount]);

  useEffect(() => {
    if (!selectedAccount) return;
    const activeConfig = accounts.find(a => a.account_name === selectedAccount);
    if (!activeConfig) return;

    getTrend(activeConfig.provider, null, topFilters.range, selectedAccount)
      .then(t => setTrend(t.data?.trend || []))
      .catch(e => console.error("Failed to fetch trend", e));
  }, [selectedAccount, topFilters.range, accounts]);

  const sync = () => {
    const activeConfig = accounts.find(a => a.account_name === selectedAccount);
    if (!activeConfig) return;

    startInventorySync(activeConfig.provider, activeConfig.id, () => {
      loadSummary();
      getTrend(activeConfig.provider, null, topFilters.range, selectedAccount).then(t => setTrend(t.data?.trend || []));
    });
  };

  const handleWipe = async () => {
    if (!window.confirm(`Are you sure you want to completely wipe all database records for ${selectedAccount}? This is permanent.`)) return;
    try {
      await wipeDatabase(selectedAccount, topFilters.provider);
      toast.success(`${selectedAccount} data wiped successfully`);
      loadSummary();
    } catch (e) { toast.error("Wipe failed"); }
  };


  const filteredTrend = useMemo(() => {
    if (!trend.length) return [];
    // The backend already filters to topFilters.range days, so we just use the result directly
    const result = [...trend];

    if (result.length > 0) {
      const lastPoint = result[result.length - 1];
      const lastDate = new Date(lastPoint.raw_date || lastPoint.date);
      const today = new Date();

      // If the last snapshot is older than today, push a data point for right now to draw a flat line
      if (lastDate.toDateString() !== today.toDateString()) {
        result.push({
          ...lastPoint,
          raw_date: today.toISOString(),
          date: today.toISOString()
        });
      } else if (result.length === 1) {
        // If there's only 1 point and it was taken today, we still need 2 points to draw an area graph.
        // Prepend a point at the very start of today so it draws a flat line across today.
        const startOfDay = new Date(today);
        startOfDay.setHours(0, 0, 0, 0);
        if (new Date(lastPoint.raw_date || lastPoint.date) > startOfDay) {
          result.unshift({
            ...lastPoint,
            raw_date: startOfDay.toISOString(),
            date: startOfDay.toISOString()
          });
        }
      }
    }

    return result;
  }, [trend]);



  let donut = [];
  const strategy = getStrategy(topFilters.provider);

  // Compute group breakdown from type_breakdown
  const groupCounts = {};
  (serverSummary?.type_breakdown || []).forEach(t => {
    const g = strategy.getResourceGroup(t.type, '');
    groupCounts[g] = (groupCounts[g] || 0) + t.count;
  });
  const computedGroupBreakdown = Object.keys(groupCounts)
    .map(k => ({ group: k, count: groupCounts[k] }))
    .sort((a, b) => b.count - a.count);

  if (!pieGroupFilter) {
    const sorted = computedGroupBreakdown;
    if (sorted.length > 8) {
      const top = sorted.slice(0, 7);
      const otherCount = sorted.slice(7).reduce((sum, g) => sum + g.count, 0);
      donut = top.map(g => ({ name: g.group, value: g.count }));
      donut.push({ name: 'Other', value: otherCount });
    } else {
      donut = sorted.map(g => ({ name: g.group, value: g.count }));
    }
  } else {
    // Filter type_breakdown by the selected group to show sub-types
    const top7Groups = computedGroupBreakdown.slice(0, 7).map(g => g.group);

    const typeBreakdown = {};
    (serverSummary?.type_breakdown || []).forEach(t => {
      const g = strategy.getResourceGroup(t.type, '');
      const belongs = pieGroupFilter === 'Other' ? !top7Groups.includes(g) : g === pieGroupFilter;
      if (belongs) {
        typeBreakdown[t.type] = (typeBreakdown[t.type] || 0) + t.count;
      }
    });

    const sortedTypes = Object.keys(typeBreakdown)
      .map(k => ({ name: k, value: typeBreakdown[k] }))
      .sort((a, b) => b.value - a.value);

    if (sortedTypes.length > 8) {
      const top = sortedTypes.slice(0, 7);
      const otherCount = sortedTypes.slice(7).reduce((sum, t) => sum + t.value, 0);
      donut = [...top, { name: 'Other', value: otherCount }];
    } else {
      donut = sortedTypes;
    }
  }
  const tagDonut = [
    { name: 'Tagged', value: serverSummary?.tagged || 0 },
    { name: 'Untagged', value: serverSummary?.untagged || 0 }
  ];

  const canDrillDown = (groupName) => {
    // With server-side pagination, we don't have globalFilteredActive anymore.
    // Instead we rely on computedGroupBreakdown - if a group exists, we can click it.
    // However, if we need to know if there's >1 type in this group, we can check serverSummary.type_breakdown.
    if (groupName === 'Other') return true;
    const strategy = getStrategy(topFilters.provider);
    const typesInGroup = (serverSummary?.type_breakdown || [])
      .filter(t => strategy.getResourceGroup(t.type, '') === groupName);
    return typesInGroup.length > 1;
  };

  const dynamicGroups = computedGroupBreakdown;
  const dynamicTypes = (serverSummary?.type_breakdown || [])
    .filter(t => filter.group === 'All' || strategy.getResourceGroup(t.type, '') === filter.group)
    .sort((a, b) => b.count - a.count);

  // Compute deleted dynamic groups and types for the Deleted Tab
  const deletedGroupCounts = {};
  (serverSummary?.deleted_type_breakdown || []).forEach(t => {
    const g = strategy.getResourceGroup(t.type, '');
    deletedGroupCounts[g] = (deletedGroupCounts[g] || 0) + t.count;
  });
  const deletedDynamicGroups = Object.keys(deletedGroupCounts)
    .map(k => ({ group: k, count: deletedGroupCounts[k] }))
    .sort((a, b) => b.count - a.count);

  const deletedDynamicTypes = (serverSummary?.deleted_type_breakdown || [])
    .filter(t => deletedFilter.group === 'All' || strategy.getResourceGroup(t.type, '') === deletedFilter.group)
    .sort((a, b) => b.count - a.count);

  const deletedDynamicRegions = (serverSummary?.deleted_region_breakdown || []);
  const dynamicRegions = (serverSummary?.region_breakdown || []);

  return (
    <>
      <div className="sticky -top-6 h-6 -mx-6 -mt-6 bg-[#0a0a0f]/80 backdrop-blur-md z-30 pointer-events-none" />
      <div className="space-y-6 relative">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {topFilters.provider && (
              <img src={`/${topFilters.provider.toLowerCase()}-logo.svg`} alt="" className="h-10 w-10 object-contain shrink-0" />
            )}
            <div>
              <h1 className="text-xl font-semibold flex items-center gap-3 text-[#e4e4e7] tracking-tight">
                {topFilters.provider || 'Cloud'} - Inventory Insights ({selectedAccount || 'None'})
              </h1>
              <p className="text-[11px] text-[#a1a1aa] mt-1">Track all cloud resources • Detect daily changes</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <NotificationBell />
            <div className="flex items-center gap-3">
              <button onClick={handleWipe} className="flex items-center gap-2 px-3 py-1.5 text-[11px] uppercase tracking-wider font-semibold bg-transparent border border-red-900/50 text-red-400 rounded-md hover:bg-red-900/20">
                <Trash2 className="h-3 w-3" /> Wipe DB
              </button>
              <button onClick={sync} disabled={syncing} className="flex items-center gap-2 px-3 py-1.5 text-[11px] uppercase tracking-wider font-semibold bg-transparent border border-zinc-700 text-zinc-300 rounded-md hover:bg-zinc-800 disabled:opacity-50 transition-colors">
                <RefreshCw className={`h-3 w-3 ${syncing ? 'animate-spin' : ''}`} />{syncing ? 'Syncing...' : 'Sync Now'}
              </button>
            </div>
          </div>
        </div>

        <TopFilters
          topFilters={topFilters}
          setTopFilters={setTopFilters}
          selectedAccount={selectedAccount}
          setSelectedAccount={setSelectedAccount}
          accounts={accounts}
          availableRegions={filterOptions.availableRegions}
          availableLinked={filterOptions.availableLinked}
          availableTags={filterOptions.availableTags}
        />

        {/* Tabs and Content Group */}
        <div>
          <div className="border-b border-zinc-800 flex gap-6">
            {['overview', 'changes', 'resources', 'deleted'].map(t => (
              <button
                key={t}
                onClick={() => {
                  setTab(t);
                  localStorage.setItem('pulse_inventory_active_tab', t);
                  if (t === 'resources') setResourceFilter(prev => ({ ...prev, time: 'All' }));
                  if (t === 'deleted') setDeletedFilter(prev => ({ ...prev, time: 'All' }));
                }}
                className={`pb-3 text-sm font-medium border-b-2 capitalize transition-colors ${tab === t ? 'border-white text-white' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="pt-4">
            {tab === 'overview' && (
              <Overview
                summary={serverSummary}
                filteredTrend={filteredTrend}
                dynamicTypes={dynamicTypes}
                dynamicRegions={dynamicRegions}
                onKpiClick={(type) => {
                  if (type === 'new') {
                    setTab('resources');
                    localStorage.setItem('pulse_inventory_active_tab', 'resources');
                    setResourceFilter({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'Today' });
                  } else if (type === 'deleted') {
                    setTab('deleted');
                    localStorage.setItem('pulse_inventory_active_tab', 'deleted');
                    setDeletedFilter({ group: 'All', type: 'All', region: 'All', billable: 'All', time: 'Today' });
                  }
                }}
                donut={donut}
                tagDonut={tagDonut}
                pieGroupFilter={pieGroupFilter}
                setPieGroupFilter={setPieGroupFilter}
                crossFilterType={crossFilterType}
                setCrossFilterType={setCrossFilterType}
                canDrillDown={canDrillDown}
                topFilters={topFilters}
                setTopFilters={setTopFilters}
                selectedAccount={selectedAccount}
              />
            )}
            {tab === 'changes' && <Changes topFilters={topFilters} setTopFilters={setTopFilters} provider={activeConfig?.provider} account={selectedAccount} />}
            {tab === 'resources' && <Resources filter={resourceFilter} setFilter={setResourceFilter} dynamicGroups={dynamicGroups} dynamicTypes={dynamicTypes} dynamicRegions={dynamicRegions} setSelectedResource={setSelectedResource} provider={activeConfig?.provider} account={selectedAccount} topFilters={topFilters} syncRefreshTrigger={syncRefreshTrigger} />}
            {tab === 'deleted' && <Deleted filter={deletedFilter} setFilter={setDeletedFilter} dynamicGroups={deletedDynamicGroups} dynamicTypes={deletedDynamicTypes} dynamicRegions={deletedDynamicRegions} setSelectedResource={setSelectedResource} provider={activeConfig?.provider} account={selectedAccount} topFilters={topFilters} syncRefreshTrigger={syncRefreshTrigger} />}
          </div>
        </div>

        {tab !== 'overview' && <ScrollToTopButton />}

        <ResourceDetailModal
          selectedResource={selectedResource}
          setSelectedResource={setSelectedResource}
        />
      </div>
    </>
  );
}
