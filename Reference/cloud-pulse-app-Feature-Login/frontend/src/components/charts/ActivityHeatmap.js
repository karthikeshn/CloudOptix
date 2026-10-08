import React from 'react';
import { Activity, ChevronLeft, ChevronRight } from 'lucide-react';

export function ActivityHeatmap({ account, crossFilterType }) {
  const [data, setData] = React.useState([]);
  const [trendData, setTrendData] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [currentMonth, setCurrentMonth] = React.useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });
  const [selectedDay, setSelectedDay] = React.useState(() => {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    return { date: `${yyyy}-${mm}-${dd}`, count: 0, created: 0, deleted: 0, updated: 0 };
  });

  React.useEffect(() => {
    let mounted = true;
    if (!account) return;
    setLoading(true);
    import('../../api/inventory').then(api => {
      Promise.all([
        api.getHeatmapActivity(account, crossFilterType),
        api.getTrend('aws', null, null, account, crossFilterType)
      ]).then(([heatmapRes, trendRes]) => {
        if (mounted) {
          setData(heatmapRes);
          setTrendData(trendRes.data?.trend || []);
          setLoading(false);
        }
      }).catch(() => {
        if (mounted) setLoading(false);
      });
    });
    return () => { mounted = false; };
  }, [account, currentMonth, crossFilterType]);

  const activityMap = {};
  data.forEach(d => { activityMap[d.date] = d; });
  
  const trendMap = {};
  const sortedTrend = [...trendData].sort((a,b) => new Date(a.raw_date) - new Date(b.raw_date));
  
  sortedTrend.forEach(t => {
    if (t.raw_date) {
      const d = t.raw_date.split('T')[0];
      // Keep the latest snapshot of the day if there are multiple
      trendMap[d] = t.total;
    }
  });

  // Forward fill the gaps
  if (sortedTrend.length > 0) {
    let lastKnownTotal = '-';
    const minDateStr = sortedTrend[0].raw_date.split('T')[0];
    const maxDate = new Date(); // Fill up to today
    
    let curr = new Date(minDateStr);
    while (curr <= maxDate) {
      const yyyy = curr.getFullYear();
      const mm = String(curr.getMonth() + 1).padStart(2, '0');
      const dd = String(curr.getDate()).padStart(2, '0');
      const dStr = `${yyyy}-${mm}-${dd}`;
      
      if (trendMap[dStr] !== undefined) {
        lastKnownTotal = trendMap[dStr];
      } else {
        trendMap[dStr] = lastKnownTotal;
      }
      curr.setDate(curr.getDate() + 1);
    }
  }

  // Update selectedDay with data once loaded, if the selected day's data exists
  React.useEffect(() => {
    if (selectedDay && activityMap[selectedDay.date]) {
      setSelectedDay(prev => ({ ...prev, ...activityMap[prev.date] }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const prevMonth = () => {
    const d = new Date(currentMonth);
    d.setMonth(d.getMonth() - 1);
    setCurrentMonth(d);
  };
  
  const nextMonth = () => {
    const d = new Date(currentMonth);
    d.setMonth(d.getMonth() + 1);
    setCurrentMonth(d);
  };

  const generateCalendar = () => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    
    const days = [];
    for (let i = 0; i < firstDay.getDay(); i++) {
      days.push(null);
    }
    for (let i = 1; i <= lastDay.getDate(); i++) {
      const d = new Date(year, month, i);
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      days.push(`${yyyy}-${mm}-${dd}`);
    }
    return days;
  };

  const calendarDays = generateCalendar();

  const getColor = (count) => {
    if (count === 0) return '#ebedf0';
    if (count <= 5) return '#9be9a8';
    if (count <= 20) return '#40c463';
    return '#216e39';
  };

  // Remove the full-component loading replacement
  // if (loading) return <div className="...">Loading heatmap...</div>;

  return (
    <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-5 overflow-hidden mt-4">
      <h3 className="text-sm font-semibold mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-green-400" /> Infrastructure Volatility
        </div>
        <div className="flex items-center gap-3 text-xs font-medium text-zinc-300">
          <button onClick={prevMonth} className="hover:text-white p-1 bg-zinc-800 rounded border border-zinc-700/50"><ChevronLeft className="h-3 w-3" /></button>
          <span className="w-24 text-center">{currentMonth.toLocaleDateString([], { month: 'long', year: 'numeric' })}</span>
          <button onClick={nextMonth} className="hover:text-white p-1 bg-zinc-800 rounded border border-zinc-700/50"><ChevronRight className="h-3 w-3" /></button>
        </div>
      </h3>

      <div className={`flex flex-row gap-12 justify-center items-center py-2 transition-opacity duration-200 ${loading ? 'opacity-50 pointer-events-none' : 'opacity-100'}`}>
        <div className="flex flex-col gap-1 shrink-0 w-max min-h-[220px]">
          <div className="grid grid-cols-7 gap-2 text-[10px] text-zinc-500 mb-1 text-center font-semibold">
             <span>S</span><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span>
          </div>
          <div className="grid grid-cols-7 gap-2">
            {calendarDays.map((dateStr, i) => {
              if (!dateStr) return <div key={`empty-${i}`} className="w-[24px] h-[24px] rounded-sm opacity-0" />;
              
              const dayData = activityMap[dateStr] || { count: 0, created: 0, deleted: 0, updated: 0 };
              const isSelected = selectedDay?.date === dateStr;
              const dateObj = new Date(dateStr);
              
              return (
                <div 
                  key={dateStr}
                  onClick={() => setSelectedDay({ date: dateStr, ...dayData })}
                  className={`w-[24px] h-[24px] rounded-sm cursor-pointer border ${isSelected ? 'border-2 border-blue-500 text-black font-bold' : 'border border-transparent text-black/50 font-medium'} hover:border-zinc-400 flex items-center justify-center text-[10px] transition-colors duration-150`}
                  style={{ backgroundColor: getColor(dayData.count) }}
                  title={`${dateStr}: ${dayData.count} changes`}
                >
                  {dateObj.getDate()}
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-l border-zinc-800/50 pl-12 flex flex-col justify-center min-h-[140px] w-[280px]">
          {selectedDay ? (
            <div className="space-y-4 animate-in fade-in zoom-in-95 duration-200">
              <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                {new Date(selectedDay.date).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
              </h4>
              <div className="flex items-center gap-6">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider whitespace-nowrap">Total Active</span>
                  <span className="text-2xl font-bold text-white">{trendMap[selectedDay.date] !== undefined ? trendMap[selectedDay.date] : '-'}</span>
                </div>
                <div className="w-px h-8 bg-zinc-800/50"></div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Created</span>
                  <span className="text-2xl font-bold text-emerald-400">{selectedDay.created || 0}</span>
                </div>
                <div className="w-px h-8 bg-zinc-800/50"></div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Deleted</span>
                  <span className="text-2xl font-bold text-rose-400">{selectedDay.deleted || 0}</span>
                </div>
                <div className="w-px h-8 bg-zinc-800/50"></div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Updated</span>
                  <span className="text-2xl font-bold text-amber-400">{selectedDay.updated || 0}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-zinc-500 h-full flex flex-col items-center justify-center gap-2 opacity-50">
              <Activity className="h-6 w-6" />
              <span className="text-center">Select a day on the calendar<br/>to view change details.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
