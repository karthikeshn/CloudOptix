import React from 'react';

export function Kpi({label, value, subtext, subtextColor='text-zinc-500', color='text-white', icon, onClick}) {
  return (
    <div 
      className={`bg-[#111114] border border-[#1f1f24] rounded-xl p-4 flex flex-col justify-between min-h-[100px] ${onClick ? 'cursor-pointer hover:bg-zinc-800/30 transition-colors hover:border-zinc-700' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-2">
        <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">{label}</p>
        {icon && <span className="text-zinc-500">{icon}</span>}
      </div>
      <div>
        <p className={`text-xl font-bold ${color}`}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
        {subtext && (
          <p className={`text-[11px] mt-1 font-medium ${subtextColor}`}>
            {subtext}
          </p>
        )}
      </div>
    </div>
  );
}
