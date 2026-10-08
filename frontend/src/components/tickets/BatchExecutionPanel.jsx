import React, { useState } from 'react';
import { FaPlay, FaInfoCircle, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import { getScriptCategory } from '../../utils/ticketUtils';

export default function BatchExecutionPanel({ 
  selectedScriptsCount,
  selectedScripts = [],
  isBatchRunning,
  batchProgress,
  batchSummary,
  onRunBatch,
  onDeselectAll,
  onRemoveScript,
  onClearSummary
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (selectedScriptsCount === 0 && !batchSummary) return null;

  return (
    <div style={{
      padding: '1.25rem',
      borderRadius: '12px',
      background: 'rgba(56, 189, 248, 0.05)',
      border: '1px solid rgba(56, 189, 248, 0.2)',
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem',
      animation: 'fadeIn 0.3s ease-out'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }} onClick={() => setIsExpanded(!isExpanded)}>
          <div style={{
            width: '36px', height: '36px', borderRadius: '10px',
            background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <FaPlay size={14} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#f8fafc' }}>Batch Execution</h3>
              {isExpanded ? <FaChevronUp size={12} color="var(--text-muted)" /> : <FaChevronDown size={12} color="var(--text-muted)" />}
            </div>
            <p style={{ margin: '0.1rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
              {selectedScriptsCount} scripts selected
            </p>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={onDeselectAll}
            disabled={isBatchRunning}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              background: 'transparent',
              color: 'var(--text-main)',
              fontSize: '0.82rem',
              cursor: isBatchRunning ? 'not-allowed' : 'pointer',
            }}
          >
            Clear Selection
          </button>
          <button
            onClick={onRunBatch}
            disabled={isBatchRunning || selectedScriptsCount === 0}
            style={{
              padding: '0.5rem 1.25rem',
              borderRadius: '6px',
              border: 'none',
              background: 'linear-gradient(135deg, #38bdf8 0%, #2563eb 100%)',
              color: '#fff',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: (isBatchRunning || selectedScriptsCount === 0) ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              boxShadow: '0 4px 12px rgba(37,99,235,0.3)'
            }}
          >
            {isBatchRunning ? 'Running Batch...' : 'Run Selected Tickets'}
          </button>
        </div>
      </div>

      {isExpanded && selectedScripts.length > 0 && !isBatchRunning && (
        <div style={{
          marginTop: '0.5rem',
          padding: '1rem',
          background: 'rgba(15, 23, 42, 0.5)',
          borderRadius: '8px',
          border: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          maxHeight: '200px',
          overflowY: 'auto'
        }}>
          {selectedScripts.map((script, idx) => (
            <div key={idx} style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              paddingBottom: '0.4rem',
              borderBottom: idx < selectedScripts.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none'
            }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>{script}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ 
                  fontSize: '0.7rem', 
                  color: '#38bdf8', 
                  background: 'rgba(56, 189, 248, 0.1)', 
                  padding: '0.2rem 0.5rem', 
                  borderRadius: '4px' 
                }}>
                  {getScriptCategory(script)}
                </span>
                
                {onRemoveScript && (
                  <button
                    onClick={() => onRemoveScript(script)}
                    disabled={isBatchRunning}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: isBatchRunning ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: '0.2rem',
                      opacity: isBatchRunning ? 0.5 : 1
                    }}
                    title="Deselect script"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {isBatchRunning && (
        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span>Running: <strong style={{ color: '#fff' }}>{batchProgress.currentScript}</strong></span>
            <span>{batchProgress.current} / {batchProgress.total}</span>
          </div>
          <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ 
              height: '100%', 
              background: 'linear-gradient(90deg, #38bdf8, #2563eb)', 
              width: `${(batchProgress.current / batchProgress.total) * 100}%`,
              transition: 'width 0.3s ease'
            }} />
          </div>
        </div>
      )}

      {batchSummary && (
        <div style={{ 
          marginTop: '0.5rem', 
          padding: '0.75rem', 
          borderRadius: '6px', 
          background: batchSummary.includes('error') ? 'rgba(239, 68, 68, 0.1)' : 'rgba(34, 197, 94, 0.1)',
          border: `1px solid ${batchSummary.includes('error') ? 'rgba(239, 68, 68, 0.3)' : 'rgba(34, 197, 94, 0.3)'}`,
          color: batchSummary.includes('error') ? '#fca5a5' : '#86efac',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '0.5rem',
          wordBreak: 'break-word'
        }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
            <FaInfoCircle style={{ flexShrink: 0, marginTop: '2px' }} />
            <span style={{ lineHeight: '1.4', overflowWrap: 'anywhere' }}>{batchSummary}</span>
          </div>
          {onClearSummary && (
            <button 
              onClick={onClearSummary}
              style={{
                background: 'rgba(255, 255, 255, 0.1)', border: 'none', color: batchSummary.includes('error') ? '#fca5a5' : '#86efac',
                cursor: 'pointer', padding: '0.3rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: '4px', flexShrink: 0, transition: 'all 0.2s', alignSelf: 'flex-start'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
                e.currentTarget.style.color = '#fff';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                e.currentTarget.style.color = batchSummary.includes('error') ? '#fca5a5' : '#86efac';
              }}
              title="Dismiss"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
