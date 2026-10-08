import React, { useState, useRef, useEffect } from 'react';
import { Globe, ChevronDown, Check } from 'lucide-react';

export const AWS_REGIONS = [
  { id: 'us-east-1',      label: 'US East (N. Virginia)' },
  { id: 'us-east-2',      label: 'US East (Ohio)' },
  { id: 'us-west-1',      label: 'US West (N. California)' },
  { id: 'us-west-2',      label: 'US West (Oregon)' },
  { id: 'ap-south-1',     label: 'AP South (Mumbai)' },
  { id: 'ap-south-2',     label: 'AP South (Hyderabad)' },
  { id: 'ap-northeast-1', label: 'AP Northeast (Tokyo)' },
  { id: 'ap-northeast-2', label: 'AP Northeast (Seoul)' },
  { id: 'ap-northeast-3', label: 'AP Northeast (Osaka)' },
  { id: 'ap-southeast-1', label: 'AP Southeast (Singapore)' },
  { id: 'ap-southeast-2', label: 'AP Southeast (Sydney)' },
  { id: 'ap-southeast-3', label: 'AP Southeast (Jakarta)' },
  { id: 'ap-east-1',      label: 'AP East (Hong Kong)' },
  { id: 'ca-central-1',   label: 'Canada (Central)' },
  { id: 'ca-west-1',      label: 'Canada (Calgary)' },
  { id: 'eu-central-1',   label: 'Europe (Frankfurt)' },
  { id: 'eu-central-2',   label: 'Europe (Zurich)' },
  { id: 'eu-west-1',      label: 'Europe (Ireland)' },
  { id: 'eu-west-2',      label: 'Europe (London)' },
  { id: 'eu-west-3',      label: 'Europe (Paris)' },
  { id: 'eu-north-1',     label: 'Europe (Stockholm)' },
  { id: 'eu-south-1',     label: 'Europe (Milan)' },
  { id: 'eu-south-2',     label: 'Europe (Spain)' },
  { id: 'me-south-1',     label: 'Middle East (Bahrain)' },
  { id: 'me-central-1',   label: 'Middle East (UAE)' },
  { id: 'af-south-1',     label: 'Africa (Cape Town)' },
  { id: 'sa-east-1',      label: 'South America (São Paulo)' },
  { id: 'il-central-1',   label: 'Israel (Tel Aviv)' },
];

/**
 * Multi-select AWS Region dropdown.
 * value: array of region IDs. ['all'] means All Regions.
 * onChange: (newArray) => void
 */
export function AwsRegionSelect({ value = ['all'], onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const isAll = !value || value.includes('all') || value.length === 0;

  const toggle = (regionId) => {
    if (regionId === 'all') { onChange(['all']); return; }
    let next;
    if (value.includes(regionId)) {
      next = value.filter(v => v !== regionId && v !== 'all');
      if (next.length === 0) next = ['all'];
    } else {
      next = value.filter(v => v !== 'all').concat(regionId);
    }
    onChange(next);
  };

  const label = isAll
    ? 'All Regions'
    : value.length === 1
    ? (AWS_REGIONS.find(r => r.id === value[0])?.label || value[0])
    : `${value.length} Regions selected`;

  return (
    <div ref={ref} className="relative inline-block" style={{ minWidth: 190 }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full bg-[#0f0f13] border border-zinc-800 text-zinc-300 py-1.5 pl-3 pr-3 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 cursor-pointer transition-colors hover:border-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Globe className="h-4 w-4 text-zinc-500 shrink-0" />
        <span className="truncate flex-1 text-left text-[12px]">{label}</span>
        {!isAll && (
          <span className="bg-emerald-600/20 text-emerald-400 text-[10px] font-bold rounded px-1.5 py-0.5 shrink-0">
            {value.length}
          </span>
        )}
        <ChevronDown className={`h-3.5 w-3.5 text-zinc-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-68 rounded-md shadow-2xl border border-zinc-700 bg-[#12121a] overflow-hidden" style={{ top: '100%', left: 0, width: 270 }}>
          <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-[#0f0f15]">
            <span className="text-[11px] text-zinc-400 uppercase tracking-wider font-semibold">AWS Regions</span>
            <div className="flex items-center gap-2">
              <button onClick={() => onChange(['all'])} className="text-[11px] text-emerald-400 hover:text-emerald-300 transition-colors">All</button>
              <span className="text-zinc-700">|</span>
              <button onClick={() => onChange(['all'])} className="text-[11px] text-zinc-400 hover:text-zinc-300 transition-colors">Clear</button>
            </div>
          </div>

          {/* All option */}
          <button
            onClick={() => toggle('all')}
            className={`flex items-center gap-2.5 w-full px-3 py-2 text-[12px] transition-colors border-b border-zinc-800/60 ${isAll ? 'bg-emerald-500/10 text-emerald-300' : 'text-zinc-300 hover:bg-zinc-800/50'}`}
          >
            <span className={`flex items-center justify-center h-4 w-4 rounded border shrink-0 ${isAll ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-600 bg-transparent'}`}>
              {isAll && <Check className="h-3 w-3" />}
            </span>
            All Regions
          </button>

          <div className="max-h-60 overflow-y-auto">
            {AWS_REGIONS.map(region => {
              const checked = value.includes(region.id);
              return (
                <button
                  key={region.id}
                  onClick={() => toggle(region.id)}
                  className={`flex items-center gap-2.5 w-full px-3 py-1.5 text-[12px] transition-colors ${checked ? 'bg-emerald-500/10 text-emerald-300' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-300'}`}
                >
                  <span className={`flex items-center justify-center h-4 w-4 rounded border shrink-0 ${checked ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-600 bg-transparent'}`}>
                    {checked && <Check className="h-3 w-3" />}
                  </span>
                  <span className="flex-1 text-left">{region.label}</span>
                  <span className="text-zinc-600 text-[10px] font-mono">{region.id}</span>
                </button>
              );
            })}
          </div>

          {!isAll && (
            <div className="px-3 py-2 border-t border-zinc-800 bg-[#0f0f15] flex items-center justify-between">
              <span className="text-[11px] text-zinc-500">{value.length} region{value.length > 1 ? 's' : ''} selected</span>
              <button onClick={() => setOpen(false)} className="text-[11px] text-emerald-400 hover:text-emerald-300 transition-colors font-semibold">Done ✓</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
