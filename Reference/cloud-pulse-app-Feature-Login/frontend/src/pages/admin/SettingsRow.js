import React from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { ResourceIcon } from '../../components/ui/ResourceIcon';

export function SettingsRow({ r, isGroupView, toggleRow, handleToggle, setDetailResource }) {
  const isExpandable = r._isExpandable;
  const isExpanded = r._isExpanded;
  const paddingLeft = r._level ? `${r._level * 24 + 16}px` : '16px';

  return (
    <div 
      className="flex items-center justify-between py-2 pr-4 border-b border-zinc-800/40 hover:bg-zinc-800/20 transition-colors group"
      style={{ paddingLeft }}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        
        {isGroupView && (
          <div className="w-4 flex-shrink-0 flex items-center justify-center">
            {isExpandable ? (
              <button 
                onClick={() => toggleRow(r.resource_id)}
                className="p-0.5 hover:bg-zinc-700/50 rounded text-zinc-400 hover:text-white transition-colors"
              >
                {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            ) : (
              <div className="w-3.5" /> // spacer
            )}
          </div>
        )}

        <div className={`flex-shrink-0 p-1.5 rounded-lg ${r.is_visible ? 'bg-blue-500/10 text-blue-400' : 'bg-zinc-800 text-zinc-500'}`}>
          <ResourceIcon serviceType={r.service_type} className="w-3.5 h-3.5" />
        </div>

        <div className="min-w-0 flex-1">
          <div 
            className={`text-[12px] font-semibold truncate cursor-pointer hover:text-blue-400 hover:underline transition-colors ${r.is_visible ? 'text-zinc-100' : 'text-zinc-500'}`}
            onClick={() => setDetailResource && setDetailResource(r)}
          >
            {r.name}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[10px] text-zinc-500 font-mono truncate max-w-[200px]">
              {r.resource_id}
            </span>
            <span className="text-[9px] font-semibold text-zinc-400 bg-zinc-800/80 px-1.5 py-0.5 rounded-sm uppercase tracking-wider">
              {r.service_type}
            </span>
            <span className="text-[9px] font-semibold text-zinc-500 border border-zinc-800 px-1.5 py-0.5 rounded-sm">
              {r.region}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 pl-4">
        {/* Boxy Toggle Button */}
        <button
          onClick={() => handleToggle(r)}
          className={`inline-flex items-center justify-center min-w-[70px] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-sm transition-colors border ${
            r.is_visible 
              ? 'bg-blue-600/10 text-blue-400 border-blue-600/30 hover:bg-blue-600/20' 
              : 'bg-zinc-800 text-zinc-500 border-zinc-700 hover:bg-zinc-700 hover:text-zinc-300'
          }`}
        >
          {r.is_visible ? 'Visible' : 'Hidden'}
        </button>
      </div>
    </div>
  );
}
