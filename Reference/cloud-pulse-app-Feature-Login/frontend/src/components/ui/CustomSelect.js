import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';

export function CustomSelect({ label, value, options, onChange, width = 'max-w-[150px]', disabled = false }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  
  useEffect(() => {
    function handleClickOutside(event) {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [ref]);

  return (
    <div ref={ref} className={`relative flex items-center bg-[#161b22] border border-[#30363d] rounded-md px-2.5 py-1 transition-colors ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-[#1c2128]'}`} onClick={() => !disabled && setOpen(!open)}>
      <span className="text-[11px] text-[#71717a] mr-1.5">{label}</span>
      <span className={`text-[12px] font-medium text-[#d4d4d8] truncate pr-4 ${width}`}>
        {options.find(o => String(o.value) === String(value))?.label || value}
      </span>
      <ChevronDown className="absolute right-2 h-3 w-3 text-zinc-400 pointer-events-none"/>
      
      {open && (
        <div className="absolute top-full left-0 mt-1 w-max min-w-full bg-[#161b22] border border-[#30363d] rounded-md shadow-xl z-50 max-h-60 overflow-y-auto overflow-x-hidden">
          {options.map((opt, i) => (
            <div 
              key={i}
              className="px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-[#1c2128] hover:text-white cursor-pointer transition-colors"
              onClick={(e) => { e.stopPropagation(); onChange(opt.value); setOpen(false); }}
            >
              {opt.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
