import React, { useState, useEffect, useCallback } from 'react';
import { Database, Search, ListTree } from 'lucide-react';
import { TableVirtuoso } from 'react-virtuoso';
import { FilterBar } from '../../../components/ui/FilterBar';
import { EmptyState } from '../../../components/ui/EmptyState';
import { TableSkeleton } from '../../../components/ui/TableSkeleton';
import { toast } from 'sonner';
import { listResources, togglePower, saveSchedule, getDbState, getControlSummary } from '../../../api/control';
import ActionModal from '../ActionModal';
import { ControlResourceDetailModal } from '../ControlResourceDetailModal';
import { buildResourceTree } from '../../../utils/resource-tree';
import { ResourceTableRow } from './components/ResourceTableRow';
import { useDynamicFilters } from '../../../hooks/useDynamicFilters';
import { useResourcePolling } from '../../../hooks/useResourcePolling';

export function ResourcesTab({ topFilters, onActionLogged, syncRefreshTrigger }) {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const [filter, setFilter] = useState({
    group: 'All',
    type: 'All',
    powerState: 'All'
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [modalState, setModalState] = useState({ isOpen: false, mode: null, resource: null });
  const [detailResource, setDetailResource] = useState(null);
  const [isGroupView, setIsGroupView] = useState(() => {
    const saved = localStorage.getItem('pulse_control_group_view');
    return saved === 'true';
  });
  const [expandedRowIds, setExpandedRowIds] = useState(new Set());

  const toggleGroupView = () => {
    setIsGroupView(prev => {
      const next = !prev;
      localStorage.setItem('pulse_control_group_view', next);
      return next;
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
      const data = await listResources(topFilters, LIMIT, currentOffset);
      const mapped = (data || []).map(s => ({
        resource_id: s.resource_id,
        name: s.resource_name || s.resource_id,
        service_type: s.service_type,
        control_type: s.control_type,
        account_name: s.account_name,
        region: s.region,
        cloud_provider: s.cloud_provider || 'aws',
        instance_spec: s.instance_spec || 'unknown',
        tags_json: s.tags_json,
        status: s.status || 'UNKNOWN',
        parent_resource_id: s.parent_resource_id,
        schedule: {
          is_automation_enabled: s.is_automation_enabled,
          schedule_pattern: s.schedule_pattern || 'daily',
          owner_email: s.owner_email || '',
          start_time: s.start_time,
          stop_time: s.stop_time,
          timezone: s.timezone
        }
      }));

      if (reset) {
        setResources(mapped);
      } else {
        setResources(prev => [...prev, ...mapped]);
      }

      setOffset(currentOffset + mapped.length);
      setHasMore(mapped.length === LIMIT);
    } catch (err) {
      toast.error('Failed to load resources');
    } finally {
      setLoading(false);
    }
  };

  const [refreshCounter, setRefreshCounter] = useState(0);

  useEffect(() => {
    const handleRefresh = () => setRefreshCounter(c => c + 1);
    window.addEventListener('app:refresh-data', handleRefresh);
    return () => window.removeEventListener('app:refresh-data', handleRefresh);
  }, []);

  useEffect(() => {
    setHasMore(true);
    setOffset(0);
    loadResources(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.account, topFilters.provider, topFilters.region, topFilters.tag, syncRefreshTrigger, refreshCounter]);

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadResources(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, offset, topFilters]);

  // Real-Time Polling Engine
  useResourcePolling(resources, setResources);

  const handleModalConfirm = async ({ mode, resource, automationEnabled, startTime, stopTime, timezone, disabledDates }) => {
    try {
      if (mode === 'schedule') {
        await saveSchedule({
          resource_id: resource.resource_id,
          service_type: resource.service_type,
          account_name: resource.account_name,
          region: resource.region,
          is_automation_enabled: automationEnabled,
                              start_time: startTime,
          stop_time: stopTime,
          timezone: timezone,
          disabled_dates: disabledDates
        });

        setResources(prev => prev.map(r => r.resource_id === resource.resource_id ? {
          ...r,
          schedule: { is_automation_enabled: automationEnabled, start_time: startTime, stop_time: stopTime, timezone: timezone, disabled_dates: disabledDates }
        } : r));

        toast.success(`Schedule saved for ${resource.resource_id}`);
      } else if (mode === 'start' || mode === 'stop') {
        const optimisticState = mode === 'start' ? 'STARTING' : 'STOPPING';

        const toggleRes = await togglePower({
          resource_id: resource.resource_id,
          service_type: resource.service_type,
          account_name: resource.account_name,
          region: resource.region,
          action: mode.toUpperCase()
        });

        setResources(prev => prev.map(r => {
          if (r.resource_id === resource.resource_id) {
            return { ...r, status: optimisticState };
          }
          // Optimistically update child EC2 instances for ASG
          if (resource.service_type === 'ASG') {
            try {
              const tags = typeof r.tags_json === 'string' ? JSON.parse(r.tags_json) : (r.tags_json || {});
              if (tags['aws:autoscaling:groupName'] === resource.name || tags['aws:autoscaling:groupName'] === resource.resource_id) {
                return { ...r, status: mode === 'start' ? 'STARTING' : 'TERMINATING' };
              }
            } catch (e) { }
          }
          return r;
        }));

        if (toggleRes && toggleRes.saved_config_json) {
          try {
            const configData = JSON.parse(toggleRes.saved_config_json);
            if (configData.asg_name) {
              const asgName = configData.asg_name;
              setResources(prev => prev.map(r => {
                if (r.resource_id === asgName) {
                  return { ...r, status: optimisticState };
                }
                if (r.service_type === 'EC2') {
                  const tags = typeof r.tags_json === 'string' ? JSON.parse(r.tags_json) : (r.tags_json || {});
                  if (tags['aws:autoscaling:groupName'] === asgName) {
                    return { ...r, status: mode === 'start' ? 'STARTING' : 'TERMINATING' };
                  }
                }
                return r;
              }));
            }
          } catch (e) { }
        }

        toast.success(`Resource is now ${optimisticState.toLowerCase()}`);
      }
    } catch (e) {
      toast.error(`Action Blocked: ${e.response?.data?.detail || 'Operation failed'}`);
    } finally {
      setModalState({ isOpen: false, mode: null, resource: null });
      if (onActionLogged) onActionLogged();
    }
  };

  const getGroup = (type) => {
    const t = (type || '').toUpperCase();
    if (['RDS', 'AURORA'].includes(t)) return 'RDS';
    if (['EC2'].includes(t)) return 'EC2';
    return t;
  };

  const getStatusStyle = (status) => {
    switch(status?.toUpperCase()) {
      case 'RUNNING':
      case 'AVAILABLE':
        return 'bg-green-500/10 text-green-400 border border-green-500/20';
      case 'STOPPED':
      case 'PAUSED':
      case 'TERMINATED':
        return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
      case 'STARTING':
      case 'PENDING':
        return 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
      case 'STOPPING':
      case 'TERMINATING':
        return 'bg-red-500/10 text-red-400 border border-red-500/20';
      default:
        return 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20';
    }
  };

  const matchesFilter = (r) => {
    const groupMatch = filter.group === 'All' || getGroup(r.service_type) === filter.group;
    const typeMatch = filter.type === 'All' || (r.service_type || '').toUpperCase() === filter.type;
    const stateMatch = filter.powerState === 'All' || r.status === filter.powerState;
    const searchMatch = r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.resource_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.account_name.toLowerCase().includes(searchQuery.toLowerCase());
    return groupMatch && typeMatch && stateMatch && searchMatch;
  };

  const directlyMatchedIds = new Set(resources.filter(matchesFilter).map(r => r.resource_id));
  const familyMatchedIds = new Set(directlyMatchedIds);

  if (isGroupView) {
    resources.forEach(r => {
      if (directlyMatchedIds.has(r.resource_id) && r.parent_resource_id) {
        familyMatchedIds.add(r.parent_resource_id); // Include parent if child matches
      }
      if (r.parent_resource_id && directlyMatchedIds.has(r.parent_resource_id)) {
        familyMatchedIds.add(r.resource_id); // Include child if parent matches
      }
    });
  }

  const filteredResources = resources.filter(r => {
    if (!isGroupView) {
      // DYNAMIC: Exclude ONLY non-actionable parent clusters (like ECS Clusters, Beanstalk Apps) from flat view.
      // Actionable parents like ASGs and Beanstalk Environments (which can be STOPPED/RUNNING) should be shown.
      const isNonActionableParent = ['ACTIVE', 'UNKNOWN'].includes(r.status) && resources.some(child => child.parent_resource_id === r.resource_id);
      if (isNonActionableParent) return false;
      return directlyMatchedIds.has(r.resource_id);
    }
    return familyMatchedIds.has(r.resource_id);
  });

  const getTypeParam = () => {
    if (filter.group === 'All') return filter.type === 'All' ? null : filter.type;
    if (filter.type !== 'All') return filter.type;
    if (filter.group === 'RDS') return 'RDS,AURORA';
    if (filter.group === 'EC2') return 'EC2,EBS,ELB,ASG';
    return filter.group;
  };

  const treeData = React.useMemo(() => buildResourceTree(filteredResources, isGroupView, expandedRowIds), [filteredResources, isGroupView, expandedRowIds]);

  const { groupOptions, typeOptions } = useDynamicFilters({
    module: 'control',
    fetchSummary: getControlSummary,
    filters: filter,
    topFilters: topFilters,
    dynamicGroups: [],
    dynamicTypes: [],
    dynamicRegions: [],
    getGroupFn: getGroup,
    activeTypeParam: getTypeParam()
  });

  const powerStateOptions = [
    { label: 'All States', value: 'All' },
    { label: 'Running', value: 'RUNNING' },
    { label: 'Stopped', value: 'STOPPED' }
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <FilterBar
          showLabel={true}
          className="flex flex-wrap items-center gap-4"
          filters={[
            { label: "Group:", value: filter.group, onChange: v => setFilter({ ...filter, group: v, type: 'All' }), options: [{ label: 'All Groups', value: 'All' }, ...groupOptions.map(g => ({ label: `${g.label || g.group.toUpperCase()} (${g.count})`, value: g.group }))], width: "max-w-[130px]" },
            { label: "Type:", value: filter.type, onChange: v => setFilter({ ...filter, type: v }), options: [{ label: 'All Types', value: 'All' }, ...typeOptions.map(t => ({ label: `${t.label} (${t.count})`, value: t.type }))], width: "max-w-[150px]" },
            { label: "State:", value: filter.powerState, onChange: v => setFilter({ ...filter, powerState: v }), options: powerStateOptions, width: "max-w-[130px]" }
          ]}
        />

        <div className="flex items-center gap-2">
          <button
            onClick={toggleGroupView}
            title={isGroupView ? "Switch to Flat View" : "Switch to Group View"}
            className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors ${isGroupView ? 'bg-blue-600/10 text-blue-400 border-blue-600/20' : 'bg-zinc-800 text-zinc-300 border-zinc-700 hover:bg-zinc-700'}`}
          >
            <ListTree className="w-3.5 h-3.5" />
            {isGroupView ? 'Grouped' : 'Flat'}
          </button>

          <div className="relative w-64">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search loaded resources..."
              className="w-full pl-9 pr-3 py-1.5 bg-[#1e1e24] border border-zinc-800 rounded-lg text-xs text-white placeholder-zinc-500 outline-none focus:border-blue-500 transition-colors"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-[#111114] border border-[#1f1f24] rounded-xl shadow-xl [overflow:clip]">
        {(treeData.length === 0 && (loading || (offset === 0 && hasMore))) ? (
          <div className="h-[600px] w-full">
            <TableSkeleton />
          </div>
        ) : treeData.length > 0 ? (
          <TableVirtuoso
            useWindowScroll={!document.getElementById('main-scroll-container')}
            customScrollParent={document.getElementById('main-scroll-container')}
            data={treeData}
            endReached={loadMore}
            components={{
              Table: (props) => <table {...props} className="w-full text-left text-[11px]" style={{ borderCollapse: 'collapse', tableLayout: 'fixed' }} />,
              TableHead: React.forwardRef((props, ref) => <thead {...props} ref={ref} className="sticky top-0 z-40 bg-[#111114]" />),
              TableRow: (props) => <tr {...props} className="hover:bg-zinc-800/30 transition-colors border-b border-zinc-800/20 last:border-0" />,
              TableBody: React.forwardRef((props, ref) => <tbody {...props} ref={ref} className="divide-y divide-zinc-800/60 text-zinc-300" />),
            }}
            fixedHeaderContent={() => (
              <tr className="bg-[#111114]">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[30%] bg-[#111114] border-b border-[#1f1f24]">Resource Name</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[10%] bg-[#111114] border-b border-[#1f1f24]">Service</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[15%] bg-[#111114] border-b border-[#1f1f24]">Region</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[12%] bg-[#111114] border-b border-[#1f1f24]">Status</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[18%] bg-[#111114] border-b border-[#1f1f24] whitespace-nowrap">Automated Schedule</th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[15%] bg-[#111114] border-b border-[#1f1f24]">Actions</th>
              </tr>
            )}
            itemContent={(index, r) => (
              <ResourceTableRow
                r={r}
                isGroupView={isGroupView}
                toggleRow={toggleRow}
                setDetailResource={setDetailResource}
                getStatusStyle={getStatusStyle}
                setModalState={setModalState}
              />
            )}
          />
        ) : (
          <EmptyState icon={Database} message="No resources found." height="h-full py-24" />
        )}
      </div>

      <ActionModal
        isOpen={modalState.isOpen}
        onClose={() => setModalState({ isOpen: false, mode: null, resource: null })}
        mode={modalState.mode}
        resource={modalState.resource}
        onConfirm={handleModalConfirm}
      />

      {detailResource && (
        <ControlResourceDetailModal
          resource={detailResource}
          onClose={() => setDetailResource(null)}
        />
      )}
    </div>
  );
}
