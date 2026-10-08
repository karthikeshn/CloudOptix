import React, { useState } from 'react';
import { FaPlay, FaInfoCircle } from 'react-icons/fa';

export default function ScriptCard({ 
  scriptName, 
  category, 
  description,
  theme, 
  icon,
  isSelected,
  isRunning,
  isBatchRunning,
  onToggleSelect,
  onRun
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div 
      className={`script-card ${isSelected ? 'selected' : ''}`}
      style={{
        background: isSelected ? 'rgba(56, 189, 248, 0.05)' : 'rgba(255,255,255,0.02)',
        border: isSelected ? '1px solid rgba(56, 189, 248, 0.2)' : '1px solid rgba(255,255,255,0.03)',
        borderRadius: '8px',
        padding: '0.75rem 1rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '0.85rem',
        position: 'relative',
        transition: 'all 0.15s ease',
        cursor: 'pointer'
      }}
      onClick={() => onToggleSelect(scriptName)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 }}>
        <div style={{
          width: '28px', height: '28px', borderRadius: '6px',
          background: theme.bg, color: theme.color,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0
        }}>
          {icon}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '0.1rem' }}>
            {category}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: isSelected ? '#fff' : 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {scriptName}
            </span>
            <div 
              style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
            >
              <FaInfoCircle size={10} color="var(--text-muted)" style={{ cursor: 'help', flexShrink: 0 }} />
              
              {showTooltip && (
                <div style={{
                  position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: '8px',
                  width: '220px', padding: '0.75rem', background: '#0f172a',
                  border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px',
                  color: '#cbd5e1', fontSize: '0.75rem', lineHeight: 1.4, fontWeight: 400,
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)', zIndex: 50, pointerEvents: 'none',
                  textAlign: 'left', wordBreak: 'normal', whiteSpace: 'normal'
                }}>
                  {description}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
        <button
          onClick={(e) => { e.stopPropagation(); onRun(scriptName); }}
          disabled={isRunning || isBatchRunning}
          style={{
            padding: '0.4rem 0.6rem',
            borderRadius: '4px',
            border: 'none',
            background: isRunning ? 'rgba(56, 189, 248, 0.1)' : 'transparent',
            color: isRunning ? '#38bdf8' : 'var(--text-muted)',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: (isRunning || isBatchRunning) ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.3rem',
            transition: 'all 0.15s'
          }}
          onMouseEnter={(e) => { if (!isRunning && !isBatchRunning) { e.currentTarget.style.color = '#38bdf8'; e.currentTarget.style.background = 'rgba(56,189,248,0.05)'; } }}
          onMouseLeave={(e) => { if (!isRunning && !isBatchRunning) { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent'; } }}
        >
          {isRunning ? (
            <>
              <div className="spinner" style={{ width: '10px', height: '10px', border: '2px solid rgba(56,189,248,0.3)', borderTopColor: '#38bdf8', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              Running
            </>
          ) : (
            <><FaPlay size={8} /> Run</>
          )}
        </button>
      </div>
    </div>
  );
}