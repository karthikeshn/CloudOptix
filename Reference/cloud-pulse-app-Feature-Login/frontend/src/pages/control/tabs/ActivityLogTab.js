import React, { useState, useEffect, useCallback } from 'react';
import { History, Play, Square, CalendarClock } from 'lucide-react';
import { formatDynamicLocalTime } from '../../../utils/dateFormatter';
import { FilterBar } from '../../../components/ui/FilterBar';
import { TableVirtuoso } from 'react-virtuoso';
import { TableSkeleton } from '../../../components/ui/TableSkeleton';
import { EmptyState } from '../../../components/ui/EmptyState';
import { listAuditLogs } from '../../../api/control';

export function ActivityLogTab({ topFilters }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const [filter, setFilter] = useState({ eventType: 'All' });
  const [searchQuery, setSearchQuery] = useState('');

  const loadLogs = useCallback(async (reset = false) => {
    if (loading || (!hasMore && !reset)) return;
    
    setLoading(true);
    const currentOffset = reset ? 0 : offset;
    
    try {
      const data = await listAuditLogs({
        account: topFilters.account,
        eventType: filter.eventType,
        search: searchQuery.trim()
      }, LIMIT, currentOffset);
      
      const newLogs = data || [];
      setLogs(prev => reset ? newLogs : [...prev, ...newLogs]);
      setOffset(currentOffset + LIMIT);
      setHasMore(newLogs.length === LIMIT);
    } catch (e) {
      console.error("Failed to fetch paginated logs", e);
      if (reset) setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [topFilters.account, filter.eventType, searchQuery, offset, loading, hasMore]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      loadLogs(true);
    }, searchQuery ? 300 : 0);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.account, filter.eventType, searchQuery]);

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadLogs(false);
    }
  }, [loading, hasMore, loadLogs]);

  const eventOptions = [
    { label: 'All Events', value: 'All' },
    { label: 'Power Executions', value: 'power' },
    { label: 'Schedule Modifications', value: 'schedule' }
  ];

  const getActionIcon = (actionType) => {
    if (actionType.includes('START')) return <Play className="h-4 w-4 text-green-500" />;
    if (actionType.includes('STOP')) return <Square className="h-4 w-4 text-red-500" />;
    if (actionType.includes('SCHEDULE')) return <CalendarClock className="h-4 w-4 text-blue-500" />;
    return <History className="h-4 w-4 text-zinc-400" />;
  };

  const formatDate = (isoString) => {
    return formatDynamicLocalTime(isoString, 'full');
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <FilterBar 
          showLabel={true}
          filters={[
            { 
              label: "Event Type:", 
              value: filter.eventType, 
              onChange: v => setFilter({ ...filter, eventType: v }), 
              options: eventOptions,
              width: "max-w-[200px]"
            }
          ]}
        />
        <div className="relative">
          <input
            type="text"
            placeholder="Search resource or action..."
            className="bg-zinc-800/50 border border-zinc-700/50 rounded-md text-xs px-3 py-1.5 w-[250px] text-zinc-300 focus:outline-none focus:border-zinc-500"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="bg-[#111114] border border-[#1f1f24] rounded-xl shadow-xl [overflow:clip]">
        {(logs.length === 0 && (loading || (offset === 0 && hasMore))) ? (
          <div className="h-[600px] w-full">
            <TableSkeleton />
          </div>
        ) : logs.length > 0 ? (
          <TableVirtuoso
            useWindowScroll={!document.getElementById('main-scroll-container')}
            customScrollParent={document.getElementById('main-scroll-container')}
            data={logs}
            endReached={loadMore}
            components={{
              Table: (props) => <table {...props} className="w-full text-left text-[11px]" style={{ borderCollapse: 'separate', borderSpacing: 0, tableLayout: 'fixed' }} />,
              TableHead: React.forwardRef((props, ref) => <thead {...props} ref={ref} className="sticky top-0 z-20 text-zinc-400 uppercase text-[10px]" />),
              TableRow: (props) => <tr {...props} className="hover:bg-zinc-800/30 transition-colors border-b border-zinc-800/20 last:border-0" />,
              TableBody: React.forwardRef((props, ref) => <tbody {...props} ref={ref} className="divide-y divide-zinc-800/60 text-zinc-300" />),
            }}
            fixedHeaderContent={() => (
              <tr className="bg-[#0a0a0f]">
                <th className="p-4 w-[15%] bg-[#111114] rounded-tl-xl border-b border-[#1f1f24]">Timestamp</th>
                <th className="p-4 w-[15%] bg-[#111114] border-b border-[#1f1f24]">Event Type</th>
                <th className="p-4 w-[10%] bg-[#111114] border-b border-[#1f1f24]">Service</th>
                <th className="p-4 w-[25%] bg-[#111114] border-b border-[#1f1f24]">Resource</th>
                <th className="p-4 w-[10%] bg-[#111114] border-b border-[#1f1f24]">Status</th>
                <th className="p-4 w-[25%] bg-[#111114] rounded-tr-xl border-b border-[#1f1f24]">Details</th>
              </tr>
            )}
            itemContent={(index, log) => (
              <>
                <td className="p-4 font-mono text-[11px] text-zinc-400 whitespace-nowrap">
                  {formatDate(log.timestamp + 'Z')}
                </td>
                <td className="p-4">
                  <div className="flex items-center gap-2 font-medium">
                    {getActionIcon(log.action_type)}
                    <span className="text-zinc-200">{log.action_type.replace(/_/g, ' ')}</span>
                  </div>
                </td>
                <td className="p-4 text-[12px] font-bold text-zinc-400 uppercase">
                  {log.service_type || 'Unknown'}
                </td>
                <td className="p-4">
                  <div className="font-semibold text-white truncate">{log.resource_name || log.native_id}</div>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-zinc-500">
                    <span className="font-mono uppercase">{log.provider}</span> • <span>{log.account_name}</span>
                  </div>
                </td>
                <td className="p-4">
                  {log.status === 'SUCCESS' ? (
                    <span className="flex items-center gap-1.5 text-green-400 bg-green-500/10 px-2 py-1 rounded-full text-[10px] font-bold w-fit">
                      SUCCESS
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-red-400 bg-red-500/10 px-2 py-1 rounded-full text-[10px] font-bold w-fit">
                      FAILED
                    </span>
                  )}
                </td>
                <td className="p-4 text-[11px] text-zinc-400">
                  {log.details || '-'}
                </td>
              </>
            )}
          />
        ) : (
          <EmptyState icon={History} message="No activity logs found for the current filters." height="h-full py-24" />
        )}
      </div>
    </div>
  );
}

