import React from 'react';
import { TrendingUp, Server, Tag as TagIcon, Plus, Minus, Globe } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Brush } from 'recharts';
import { formatDynamicLocalTime } from '../../../utils/dateFormatter';
import { formatType } from '../../../utils/ui-utils';
import { EmptyState } from '../../../components/ui/EmptyState';
import { CustomDonut } from '../../../components/charts/CustomDonut';
import { ActivityHeatmap } from '../../../components/charts/ActivityHeatmap';
import { Kpi } from '../../../components/ui/Kpi';

const COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6', '#f97316'];

const calculateYAxisMax = (dataMax) => {
  if (!dataMax || dataMax <= 10) return dataMax + 2;
  const digits = Math.floor(Math.log10(dataMax));
  const pow = Math.pow(10, digits);
  return Math.ceil(dataMax / pow) * pow + (dataMax % pow === 0 ? pow : 0);
};

const calculateYAxisMin = (dataMin) => {
  if (!dataMin || dataMin <= 10) return Math.max(0, dataMin - 2);
  const digits = Math.floor(Math.log10(dataMin));
  const pow = Math.pow(10, digits);
  return Math.max(0, Math.floor(dataMin / pow) * pow - (dataMin % pow === 0 ? pow : 0));
};

export function OverviewTab({ summary, dynamicTypes, dynamicRegions, selectedAccount, topFilters, filteredTrend, donut, tagDonut, crossFilterType, setCrossFilterType, pieGroupFilter, setPieGroupFilter, canDrillDown, onKpiClick }) {
  const enhancedTrend = React.useMemo(() => {
    return filteredTrend.map((item, index) => {
      const prevTotal = index > 0 ? filteredTrend[index - 1].total : item.total;
      return { ...item, delta: item.total - prevTotal };
    });
  }, [filteredTrend]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-6 gap-2.5">
        <Kpi label="Total Active" value={summary?.total || 0} subtext="all tracked resources" />
        <Kpi label="Billable" value={summary?.billable || 0} color="text-blue-400" subtext={summary?.total ? `${((summary?.billable / summary?.total) * 100).toFixed(1)}% of total` : '0%'} />
        <Kpi label="Non-Billable" value={summary?.non_billable || 0} color="text-zinc-400" subtext={summary?.total ? `${((summary?.non_billable / summary?.total) * 100).toFixed(1)}% of total` : '0%'} />
        <Kpi label="New Today" value={summary?.new_today || 0} color="text-green-400" subtextColor="text-green-500/80" subtext="in past 24h" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => onKpiClick && onKpiClick('new')} />
        <Kpi label="Deleted Today" value={summary?.deleted_today || 0} color="text-red-400" subtextColor="text-red-500/80" subtext="in past 24h" icon={<Minus className="h-3.5 w-3.5" />} onClick={() => onKpiClick && onKpiClick('deleted')} />
        <Kpi label="Regions" value={(summary?.region_breakdown || []).length} color="text-cyan-400" subtext="active locations" icon={<Globe className="h-3.5 w-3.5" />} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="col-span-2 bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-400" />Resource Count Trend
              {crossFilterType && (
                <span className="ml-2 text-[10px] font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20 cursor-pointer hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/20 transition-colors" onClick={() => setCrossFilterType(null)}>
                  Filtered: {formatType(crossFilterType, topFilters.provider)} ✕
                </span>
              )}
            </h3>
            <span className="text-[10px] font-medium text-zinc-400 bg-zinc-800/50 px-2 py-1 rounded-md border border-zinc-700/50">
              {{1:'Today',7:'Last 7 days',14:'Last 14 days',30:'Last 30 days',90:'Last 3 months',180:'Last 6 months',365:'Last 1 year'}[topFilters.range] || `${topFilters.range} days`}
            </span>
          </div>
          {enhancedTrend.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={enhancedTrend} margin={{ top: 10, right: 15, left: -20, bottom: 5 }}>
                <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f2e" />
                <XAxis 
                  dataKey="raw_date" 
                  tick={{ fontSize: 9, fill: '#555' }} 
                  axisLine={false} 
                  tickLine={false}
                  minTickGap={20}
                  tickFormatter={(val) => {
                    if (!val) return '';
                    if (topFilters.range <= 1) return formatDynamicLocalTime(val, 'timeOnly');
                    if (topFilters.range <= 7) return formatDynamicLocalTime(val, 'short');
                    return formatDynamicLocalTime(val, 'dateOnly');
                  }} 
                />
                <YAxis 
                  tick={{ fontSize: 9, fill: '#555' }} 
                  axisLine={false} 
                  tickLine={false} 
                  domain={[calculateYAxisMin, calculateYAxisMax]} 
                />
                <Tooltip 
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      const dateStr = formatDynamicLocalTime(label);
                      const deltaColor = data.delta > 0 ? '#10b981' : data.delta < 0 ? '#ef4444' : '#a1a1aa';
                      const deltaSign = data.delta > 0 ? '+' : '';
                      return (
                        <div className="bg-[#111] border border-[#333] rounded-lg p-2.5 text-[11px] text-[#e4e4e7] shadow-xl">
                          <p className="font-semibold mb-2 text-zinc-300">{dateStr}</p>
                          <div className="space-y-1">
                            <p className="flex justify-between gap-4"><span className="text-blue-400">Total Resources:</span> <span className="font-medium">{data.total}</span></p>
                            <p className="flex justify-between gap-4"><span style={{color: deltaColor}}>Net Change:</span> <span style={{color: deltaColor, fontWeight: 500}}>{deltaSign}{data.delta}</span></p>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area type="monotone" dataKey="total" stroke="#3b82f6" fill="url(#g)" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={true} animationDuration={1500} animationEasing="ease-out" />
                <Brush 
                  dataKey="raw_date" 
                  height={20} 
                  stroke="#3f3f46" 
                  fill="#18181b"
                  travellerWidth={10}
                  tickFormatter={() => ''} 
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EmptyState icon={TrendingUp} message="No trend data for this range." />}
        </div>
        <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 w-full overflow-hidden">
              <Server className="h-4 w-4 text-purple-400 shrink-0" />
              <span className="truncate" title={pieGroupFilter ? `By Type (${pieGroupFilter})` : 'By Resource Group'}>
                {pieGroupFilter ? `By Type (${pieGroupFilter})` : 'By Resource Group'}
              </span>
            </div>
          </h3>
          {donut.length > 0 ? (
            <>
              <CustomDonut data={donut} colors={COLORS} isAnimationActive={!pieGroupFilter} onSliceClick={(sliceName) => {
                if (!pieGroupFilter) {
                  if (canDrillDown && !canDrillDown(sliceName)) return;
                  setPieGroupFilter(sliceName);
                } else {
                  // Clicking any sub-resource goes back to the grouped view
                  setPieGroupFilter(null);
                }
              }} />
              <div className="space-y-1.5 mt-2 h-[120px] overflow-hidden">{donut.slice(0, 6).map((t, i) => (<div key={t.name} className="flex items-center justify-between"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm" style={{ backgroundColor: COLORS[i % COLORS.length] }} /><span className="text-[10px] text-zinc-300 truncate max-w-[120px]" title={t.name}>{pieGroupFilter ? formatType(t.name, topFilters.provider) : t.name}</span></div><span className="text-[10px] text-white font-bold">{t.value}</span></div>))}</div>
            </>
          ) : <EmptyState icon={Server} message="No resource type data." />}
        </div>
        <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><TagIcon className="h-4 w-4 text-emerald-400" />Tags</h3>
          {tagDonut && (tagDonut[0].value > 0 || tagDonut[1].value > 0) ? (
            <>
              <CustomDonut data={tagDonut} colors={['#10b981', '#52525b']} />
              <div className="space-y-1.5 mt-2">
                <div className="flex items-center justify-between"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-emerald-500" /><span className="text-[10px] text-zinc-300">Tagged</span></div><span className="text-[10px] text-white font-bold">{tagDonut[0].value}</span></div>
                <div className="flex items-center justify-between"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-zinc-500" /><span className="text-[10px] text-zinc-300">Untagged</span></div><span className="text-[10px] text-white font-bold">{tagDonut[1].value}</span></div>
              </div>
            </>
          ) : <EmptyState icon={TagIcon} message="No tag data available." />}
        </div>
      </div>
      <ActivityHeatmap account={selectedAccount} crossFilterType={crossFilterType} />
    </div>
  );
}
