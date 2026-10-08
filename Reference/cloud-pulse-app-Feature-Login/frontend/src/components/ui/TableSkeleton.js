import React from 'react';

export function TableSkeleton() {
  return (
    <div className="w-full flex flex-col bg-[#111114]/50 border border-[#1f1f24] rounded-xl overflow-hidden opacity-0" style={{ animation: 'fadeIn 0.3s ease-in-out 0.15s forwards' }}>
      {/* Skeleton Header */}
      <div className="flex w-full bg-[#0a0a0f] border-b border-[#1f1f24] p-4 gap-4">
        <div className="h-4 w-32 bg-zinc-800/50 rounded animate-pulse"></div>
        <div className="h-4 w-16 bg-zinc-800/50 rounded animate-pulse ml-auto"></div>
      </div>
      
      {/* Skeleton Rows */}
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="flex items-center p-4 border-b border-[#1f1f24]/50 gap-4">
          <div className="flex items-center gap-3 w-[30%]">
            <div className="w-6 h-6 rounded bg-zinc-800/50 animate-pulse shrink-0"></div>
            <div className="flex flex-col gap-1.5 w-full">
              <div className="h-3.5 w-3/4 bg-zinc-800/50 rounded animate-pulse"></div>
              <div className="h-2.5 w-1/2 bg-zinc-800/30 rounded animate-pulse"></div>
            </div>
          </div>
          <div className="w-[10%]"><div className="h-3 w-16 bg-zinc-800/50 rounded animate-pulse"></div></div>
          <div className="w-[10%]"><div className="h-3 w-16 bg-zinc-800/50 rounded animate-pulse"></div></div>
          <div className="w-[15%]"><div className="h-5 w-20 bg-zinc-800/50 rounded animate-pulse"></div></div>
          <div className="w-[20%]"><div className="h-4 w-24 bg-zinc-800/50 rounded animate-pulse"></div></div>
          <div className="w-[15%] flex justify-end gap-2">
            <div className="h-6 w-16 bg-zinc-800/50 rounded animate-pulse"></div>
            <div className="h-6 w-16 bg-zinc-800/50 rounded animate-pulse"></div>
          </div>
        </div>
      ))}
      
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
