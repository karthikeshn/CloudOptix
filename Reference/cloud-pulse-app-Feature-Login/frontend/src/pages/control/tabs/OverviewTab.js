import React, { useState, useEffect } from 'react';
import { Power, Clock, Server, Trash2, Activity, Play, Square, CalendarClock, History } from 'lucide-react';
import { Kpi } from '../../../components/ui/Kpi';
import { Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { CustomDonut } from '../../../components/charts/CustomDonut';
import { listAuditLogs } from '../../../api/control';
import { formatDynamicLocalTime } from '../../../utils/dateFormatter';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1'];

export function OverviewTab({ totalCount, runningCount, stoppedCount, terminatedCount = 0, activeSchedulesCount, typeBreakdown = [], regionBreakdown = [], topFilters }) {
  const [recentLogs, setRecentLogs] = useState([]);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const data = await listAuditLogs({ account: topFilters?.account, eventType: 'All' }, 5, 0);
        setRecentLogs(data || []);
      } catch (err) {
        console.error("Failed to fetch recent audit logs", err);
      }
    };
    if (topFilters?.account) {
      fetchLogs();
    }
  }, [topFilters?.account]);

  // Custom tooltip for dark mode charts
  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#111114] border border-zinc-800 p-2 rounded-lg text-xs shadow-xl text-zinc-300">
          <p className="font-semibold">{`${payload[0].name || payload[0].payload.region} : ${payload[0].value}`}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      {/* 5-column grid to accommodate the new Terminated KPI */}
      <div className="grid grid-cols-5 gap-2.5">
        <Kpi 
          label="Total Resources" 
          value={totalCount} 
          icon={<Server className="h-4 w-4" />} 
          subtext="all managed instances"
        />
        <Kpi 
          label="Running Workloads" 
          value={runningCount} 
          color="text-green-400"
          icon={<Power className="h-4 w-4" />} 
          subtextColor="text-green-500/80"
          subtext={totalCount ? `${((runningCount / totalCount) * 100).toFixed(1)}% of total` : '0%'}
        />
        <Kpi 
          label="Stopped Workloads" 
          value={stoppedCount} 
          color="text-amber-400"
          icon={<Power className="h-4 w-4" />} 
          subtextColor="text-amber-500/80"
          subtext={totalCount ? `${((stoppedCount / totalCount) * 100).toFixed(1)}% of total` : '0%'}
        />
        <Kpi 
          label="Terminated Workloads" 
          value={terminatedCount} 
          color="text-red-400"
          icon={<Trash2 className="h-4 w-4" />} 
          subtextColor="text-red-500/80"
          subtext={totalCount ? `${((terminatedCount / totalCount) * 100).toFixed(1)}% of total` : '0%'}
        />
        <Kpi 
          label="Automated Schedules" 
          value={`${activeSchedulesCount} Active`} 
          color="text-blue-400"
          icon={<Clock className="h-4 w-4" />} 
          subtextColor="text-blue-500/80"
          subtext="currently managed"
        />
      </div>
      
      {/* Charts Section */}
      <div className="grid grid-cols-3 gap-4">
        
        {/* Resource Type Donut Chart */}
        <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Server className="w-4 h-4 text-purple-400" />
            Resource Distribution
          </h3>
          {typeBreakdown.length > 0 ? (
            <div>
              <CustomDonut 
                data={typeBreakdown.map(entry => ({ name: entry.type, value: entry.count }))} 
                colors={COLORS} 
              />
              <div className="space-y-1.5 mt-2 h-[80px] overflow-hidden">
                {typeBreakdown.slice(0, 4).map((entry, index) => (
                  <div key={entry.type} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: COLORS[index % COLORS.length] }}></span>
                      <span className="text-[10px] text-zinc-300 truncate max-w-[120px]">{entry.type}</span>
                    </div>
                    <span className="text-[10px] text-white font-bold">{entry.count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-[240px] flex items-center justify-center text-zinc-500 text-xs">
              No resource data available
            </div>
          )}
        </div>

        {/* Region Bar Chart */}
        <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Server className="w-4 h-4 text-emerald-400" />
            Geographical Distribution
          </h3>
          {regionBreakdown.length > 0 ? (
             <div className="h-[220px] w-full overflow-x-auto overflow-y-hidden">
               <div style={{ minWidth: `${Math.max(100, regionBreakdown.length * 60)}px`, height: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={regionBreakdown}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#1f1f24" />
                    <XAxis dataKey="region" type="category" axisLine={false} tickLine={false} tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                    <YAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                    <Tooltip cursor={{ fill: '#1f1f24' }} content={<CustomTooltip />} />
                    <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} maxBarSize={40}>
                      {regionBreakdown.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
             <div className="h-[220px] flex items-center justify-center text-zinc-500 text-xs">
              No regional data available
            </div>
          )}
        </div>

        {/* Recent Actions Feed */}
        <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-rose-400" />
            Recent Actions
          </h3>
          <div className="h-[220px] overflow-hidden">
            {recentLogs.length > 0 ? (
              <div className="space-y-3 pt-1">
                {recentLogs.map((log, index) => {
                  let Icon = History;
                  let colorClass = 'text-zinc-400';
                  
                  if (log.action_type.includes('START')) {
                    Icon = Play;
                    colorClass = 'text-green-400';
                  } else if (log.action_type.includes('STOP')) {
                    Icon = Square;
                    colorClass = 'text-amber-400';
                  } else if (log.action_type.includes('SCHEDULE')) {
                    Icon = CalendarClock;
                    colorClass = 'text-blue-400';
                  }

                  return (
                    <div key={index} className="flex gap-3 justify-between items-start">
                      <div className="flex gap-3 min-w-0 flex-1">
                        <div className={`mt-0.5 shrink-0 p-1.5 rounded-lg bg-zinc-800/50 ${colorClass}`}>
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-[11px] font-semibold text-zinc-300 truncate">
                            {log.resource_name || log.native_id || 'Unknown Resource'}
                          </p>
                          <p className="text-[10px] text-zinc-500 capitalize truncate">
                            {log.action_type.replace(/_/g, ' ').toLowerCase()} • {log.service_type || 'Unknown'}
                          </p>
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-[10px] font-medium text-zinc-500 mt-0.5 whitespace-nowrap">
                          {formatDynamicLocalTime(log.timestamp + 'Z', 'timeOnly')}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-zinc-500 text-xs">
                No recent actions found
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}
