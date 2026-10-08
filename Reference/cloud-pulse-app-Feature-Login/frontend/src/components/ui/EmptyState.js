import React from 'react';

export function EmptyState({ icon: Icon, message, height = "h-[200px]", className = "" }) {
  return (
    <div className={`${height} flex flex-col items-center justify-center gap-3 w-full ${className}`}>
      {Icon && (
        <div className="flex items-center justify-center w-12 h-12 rounded-full bg-zinc-800/30 text-zinc-500 mb-1">
          <Icon className="h-5 w-5 stroke-[1.5]" />
        </div>
      )}
      <div className="flex flex-col items-center gap-1">
        <h3 className="text-sm font-medium text-zinc-400">No data found</h3>
        <span className="text-xs text-zinc-500 text-center">{message}</span>
      </div>
    </div>
  );
}
