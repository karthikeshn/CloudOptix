import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export function ScheduleCalendar({ disabledDates, setDisabledDates }) {
  const [currentDate, setCurrentDate] = useState(new Date());

  const daysInMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
  const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1).getDay();

  const prevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
  };

  const nextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  };

  const toggleDate = (day) => {
    // Format YYYY-MM-DD
    const dateStr = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    
    setDisabledDates(prev => {
      if (prev.includes(dateStr)) {
        return prev.filter(d => d !== dateStr);
      }
      return [...prev, dateStr];
    });
  };

  const getActionableWeekendsInMonth = () => {
    const dates = [];
    const today = new Date();
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    
    for (let i = 1; i <= daysInMonth; i++) {
      const date = new Date(currentDate.getFullYear(), currentDate.getMonth(), i);
      if (date.getDay() === 0 || date.getDay() === 6) {
        if (date >= todayStart) {
          const dateStr = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
          dates.push(dateStr);
        }
      }
    }
    return dates;
  };

  const actionableWeekends = getActionableWeekendsInMonth();
  const allWeekendsDisabled = actionableWeekends.length > 0 && actionableWeekends.every(d => disabledDates.includes(d));

  const toggleWeekends = () => {
    if (actionableWeekends.length === 0) return;
    
    if (allWeekendsDisabled) {
      setDisabledDates(prev => prev.filter(d => !actionableWeekends.includes(d)));
    } else {
      setDisabledDates(prev => {
        const newSet = new Set(prev);
        actionableWeekends.forEach(d => newSet.add(d));
        return Array.from(newSet);
      });
    }
  };

  const renderDays = () => {
    const days = [];
    const weekDays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

    // Header
    weekDays.forEach(day => {
      days.push(
        <div key={`header-${day}`} className="text-[10px] font-bold text-zinc-500 text-center py-1">
          {day}
        </div>
      );
    });

    // Empty slots before 1st
    for (let i = 0; i < firstDayOfMonth; i++) {
      days.push(<div key={`empty-${i}`} className="p-1"></div>);
    }

    // Days
    for (let i = 1; i <= daysInMonth; i++) {
      const dateStr = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
      const isDisabled = disabledDates.includes(dateStr);
      
      const today = new Date();
      const isToday = today.getDate() === i && today.getMonth() === currentDate.getMonth() && today.getFullYear() === currentDate.getFullYear();
      
      const isPast = new Date(currentDate.getFullYear(), currentDate.getMonth(), i) < new Date(today.getFullYear(), today.getMonth(), today.getDate());

      days.push(
        <button
          key={dateStr}
          onClick={() => !isPast && toggleDate(i)}
          disabled={isPast}
          className={`h-7 w-full rounded text-[11px] font-medium flex items-center justify-center transition-all
            ${isPast ? 'opacity-30 cursor-not-allowed bg-zinc-900 text-zinc-600' : 'cursor-pointer hover:scale-105 active:scale-95'}
            ${!isPast && !isDisabled ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.1)]' : ''}
            ${!isPast && isDisabled ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : ''}
            ${isToday ? 'ring-1 ring-white/50' : ''}
          `}
        >
          {i}
        </button>
      );
    }
    return days;
  };

  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

  return (
    <div className="bg-[#161b22] p-3 rounded-lg border border-[#26262b] shadow-sm select-none">
      <div className="flex items-center justify-between mb-3">
        <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Active Dates</label>
        <div className="flex items-center gap-2">
          <button onClick={prevMonth} className="p-1 hover:bg-[#26262b] rounded transition-colors text-zinc-400 hover:text-white">
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <span className="text-[12px] font-bold text-zinc-200 w-24 text-center">
            {monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}
          </span>
          <button onClick={nextMonth} className="p-1 hover:bg-[#26262b] rounded transition-colors text-zinc-400 hover:text-white">
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between mb-2">
        <button onClick={toggleWeekends} className="text-[10px] bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-2 py-1 rounded transition-colors w-full border border-zinc-700/50 shadow-sm font-medium">
          {allWeekendsDisabled ? 'Keep All Weekends (This Month)' : 'Skip All Weekends (This Month)'}
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {renderDays()}
      </div>
      
      <div className="flex items-center justify-center gap-4 mt-3 pt-2 border-t border-[#26262b]/50">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-emerald-500/20 border border-emerald-500/30"></div>
          <span className="text-[10px] text-zinc-500 font-medium">Scheduled</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-rose-500/20 border border-rose-500/30"></div>
          <span className="text-[10px] text-zinc-500 font-medium">Skipped</span>
        </div>
      </div>
    </div>
  );
}
