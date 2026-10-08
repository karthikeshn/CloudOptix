import React from 'react';
import { Filter } from 'lucide-react';
import { CustomSelect } from './CustomSelect';

export function FilterBar({ filters, showLabel = false, className = "flex flex-wrap items-center gap-3" }) {
  return (
    <div className={className}>
      {showLabel && (
        <div className="flex items-center gap-2 pr-4 border-r border-zinc-800">
          <Filter className="h-4 w-4 text-blue-400" />
          <span className="text-xs font-semibold text-zinc-300">Filter by:</span>
        </div>
      )}

      {filters.map((f, i) => (
        <CustomSelect
          key={i}
          label={f.label}
          value={f.value}
          onChange={f.onChange}
          options={f.options}
          width={f.width}
          disabled={f.disabled}
        />
      ))}
    </div>
  );
}
