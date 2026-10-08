import React from 'react';
import { Eye, Server } from 'lucide-react';
import { TableVirtuoso } from 'react-virtuoso';
import { formatDynamicLocalTime } from '../../../utils/dateFormatter';
import { FilterBar } from '../../../components/ui/FilterBar';
import { EmptyState } from '../../../components/ui/EmptyState';
import { TableSkeleton } from '../../../components/ui/TableSkeleton';

import { getResources, getAdvancedSummary } from '../../../api/inventory';
import { getStrategy } from '../../../utils/cloud-strategies';
import { formatType, formatIdentifier, formatName } from '../../../utils/ui-utils';
import { useDynamicFilters } from '../../../hooks/useDynamicFilters';

export function DeletedTab({ filter, setFilter, dynamicGroups, dynamicTypes, dynamicRegions, setSelectedResource, provider, account, topFilters, syncRefreshTrigger }) {
  const [resources, setResources] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [hasMore, setHasMore] = React.useState(true);
  const [offset, setOffset] = React.useState(0);
  
  const strategy = getStrategy(provider);
  const LIMIT = 50;

  const getTypeParam = React.useCallback(() => {
    if (filter.group === 'All') return filter.type === 'All' ? null : filter.type;
    
    if (filter.type !== 'All') return filter.type;

    const groupTypes = dynamicTypes.filter(t => strategy.getResourceGroup(t.type, '') === filter.group).map(t => t.type);
    return groupTypes.length > 0 ? groupTypes.join(',') : 'NONE';
  }, [filter.type, filter.group, dynamicTypes, strategy]);

  const { groupOptions, typeOptions, regionOptions } = useDynamicFilters({
    module: 'inventory',
    fetchSummary: getAdvancedSummary,
    filters: { ...filter, isDeletedTab: true },
    topFilters: {
      account, provider, region: filter.region, linked: topFilters.linked, tag: topFilters.tag
    },
    dynamicGroups,
    dynamicTypes,
    dynamicRegions,
    activeTypeParam: getTypeParam()
  });

  const fetchResources = React.useCallback(async (reset = false) => {
    if (loading || (!hasMore && !reset)) return;
    setLoading(true);

    try {
      const currentOffset = reset ? 0 : offset;
      const typeParam = getTypeParam();

      if (typeParam === 'NONE') {
        setResources(reset ? [] : resources);
        setHasMore(false);
        setLoading(false);
        return;
      }

      console.log("Fetching deleted resources with typeParam:", typeParam, "filter:", filter);

      const res = await getResources(
        provider,
        null, // configId
        typeParam,
        filter.region === 'All' ? topFilters.region : filter.region,
        filter.billable,
        account,
        'deleted',
        LIMIT,
        currentOffset,
        topFilters.linked,
        topFilters.tag,
        filter.time
      );

      const newResources = res.data.resources;
      
      setResources(prev => reset ? newResources : [...prev, ...newResources]);
      setOffset(currentOffset + LIMIT);
      setHasMore(newResources.length === LIMIT);
    } catch (e) {
      console.error("Failed to fetch paginated resources", e);
    } finally {
      setLoading(false);
    }
  }, [account, provider, filter, topFilters, offset, loading, hasMore, resources, getTypeParam]);

  React.useEffect(() => {
    setHasMore(true);
    setOffset(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, provider, filter, topFilters]);

  React.useEffect(() => {
    if (offset === 0 && hasMore && !loading) {
      fetchResources(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, hasMore, fetchResources]);

  React.useEffect(() => {
    if (syncRefreshTrigger > 0) {
      fetchResources(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncRefreshTrigger]);

  const loadMore = () => {
    if (!loading && hasMore) {
      fetchResources(false);
    }
  };

  return (
    <div>
      <FilterBar
        showLabel={true}
        className="flex flex-wrap items-center gap-4 mb-4"
        filters={[
          { label: "Group:", value: filter.group, onChange: v => setFilter({ ...filter, group: v, type: 'All' }), options: [{ label: 'All Services', value: 'All' }, ...groupOptions.map(g => ({ label: `${g.label || g.group.toUpperCase()} (${g.count})`, value: g.group }))], width: "max-w-[160px]" },
          { label: "Type:", value: filter.type, onChange: v => setFilter({ ...filter, type: v }), options: [{ label: 'All Types', value: 'All' }, ...typeOptions.map(t => ({ label: `${t.label || formatType(t.type, provider)} (${t.count})`, value: t.type }))], width: "max-w-[200px]" },
          { label: "Region:", value: filter.region, onChange: v => setFilter({ ...filter, region: v }), options: [{ label: 'All Regions', value: 'All' }, ...regionOptions.map(r => ({ label: `${r.label || r.region} (${r.count})`, value: r.region }))], width: "max-w-[160px]" },
          { label: "Billable:", value: filter.billable, onChange: v => setFilter({ ...filter, billable: v }), options: [{ label: 'All Statuses', value: 'All' }, { label: 'Billable', value: 'true' }, { label: 'Non-Billable', value: 'false' }], width: "w-[90px]" },
          { label: "Time:", value: filter.time, onChange: v => setFilter({ ...filter, time: v }), options: [{ label: 'All Time', value: 'All' }, { label: 'Today', value: 'Today' }], width: "w-[70px]" }
        ]}
      />

      <div className="bg-[#111114] border border-[#1f1f24] rounded-xl [overflow:clip]">
        {(resources.length === 0 && (loading || (offset === 0 && hasMore))) ? (
          <div className="h-[600px] w-full">
            <TableSkeleton />
          </div>
        ) : resources.length > 0 ? (
          <TableVirtuoso
            useWindowScroll={!document.getElementById('main-scroll-container')}
            customScrollParent={document.getElementById('main-scroll-container')}
            data={resources}
            endReached={loadMore}
            components={{
              Table: (props) => <table {...props} className="w-full text-left text-[11px]" style={{ borderCollapse: 'collapse', tableLayout: 'fixed' }} />,
              TableHead: React.forwardRef((props, ref) => <thead {...props} ref={ref} className="sticky top-0 z-40 bg-[#111114]" />),
              TableRow: (props) => <tr {...props} className="hover:bg-zinc-800/30 transition-colors border-b border-zinc-800/20 last:border-0" />,
              TableBody: React.forwardRef((props, ref) => <tbody {...props} ref={ref} className="divide-y divide-zinc-800/30" />),
            }}
            fixedHeaderContent={() => (
              <tr className="bg-[#111114]">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[40%] bg-[#111114] border-b border-[#1f1f24]">Identifier</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[25%] bg-[#111114] border-b border-[#1f1f24]">Type</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[15%] bg-[#111114] border-b border-[#1f1f24]">Region</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[10%] bg-[#111114] border-b border-[#1f1f24]">Deleted At</th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-zinc-400 uppercase w-[10%] bg-[#111114] border-b border-[#1f1f24]">Actions</th>
              </tr>
            )}
            itemContent={(index, r) => (
              <>
                  <td className="px-4 py-3 truncate">
                    <div className="text-[13px] font-semibold text-zinc-200 truncate">{formatName(r.name, r.native_id, r.provider) || formatIdentifier(r.native_id, r.provider)}</div>
                    <div className="text-[10px] text-zinc-500 font-mono mt-0.5 truncate">{formatIdentifier(r.native_id, r.provider)}</div>
                  </td>
                  <td className="px-4 py-3 text-[11px] text-zinc-400 font-medium uppercase">
                    {formatType(r.resource_type, r.provider)}
                  </td>
                  <td className="px-4 py-3 text-[11px] text-zinc-400 font-medium">{r.region}</td>
                <td className="px-4 py-3">
                  <span className="text-xs text-red-400">
                    <span className="text-zinc-400">
                      {formatDynamicLocalTime(r.deleted_at)}
                    </span>
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => setSelectedResource(r)} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold bg-blue-600/10 text-blue-400 hover:bg-blue-600/20 rounded-md transition-colors">
                    <Eye className="h-3 w-3" /> View
                  </button>
                </td>
              </>
            )}
          />
        ) : (
          <EmptyState icon={Server} message="No resources found." height="h-full py-24" />
        )}
      </div>
    </div>
  );
}
