import React, { useState } from 'react';

export default function DynamicTable({ data, scriptName, onCellEdit }) {
  const [hoverTooltip, setHoverTooltip] = useState({ visible: false, text: '', x: 0, y: 0 });
  const [editingCell, setEditingCell] = useState(null); // { rowIndex, col, value }

  const handleMouseMove = (e, text) => {
    if (text && text.length > 40) {
      setHoverTooltip({ visible: true, text, x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseLeave = () => {
    if (hoverTooltip.visible) {
      setHoverTooltip({ visible: false, text: '', x: 0, y: 0 });
    }
  };

  const handleDoubleClick = (rowIndex, col, currentValue) => {
    setEditingCell({ rowIndex, col, value: currentValue });
    handleMouseLeave(); // Hide tooltip while editing
  };

  const handleKeyDown = (e, row) => {
    if (e.key === 'Enter') {
      if (onCellEdit) {
        onCellEdit(row, editingCell.col, editingCell.value);
      }
      setEditingCell(null);
    } else if (e.key === 'Escape') {
      setEditingCell(null);
    }
  };

  // Compute union of all columns across all rows to support mixed ticket types
  const columns = React.useMemo(() => {
    const keys = new Set();
    if (data && Array.isArray(data)) {
      data.forEach(row => {
        Object.keys(row).forEach(k => {
          if (!k.startsWith('__')) keys.add(k);
        });
      });
    }
    
    const colArray = Array.from(keys);
    // Sort columns so important stuff like STATE, ID, TITLE are first
    const priority = ['STATE', 'STATUS', 'WORKITEMTYPE', 'ID', 'TITLE', 'CATEGORY', 'OWNER'];
    colArray.sort((a, b) => {
      const idxA = priority.indexOf(a.toUpperCase());
      const idxB = priority.indexOf(b.toUpperCase());
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });
    return colArray;
  }, [data]);

  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        No records found in this dataset.
      </div>
    );
  }

  return (
    <div style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      
      {/* Header Info Bar if scriptName is provided */}
      {scriptName && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.95rem', fontWeight: 600 }}>
            {scriptName}
          </h4>
          <span style={{ fontSize: '0.75rem', background: 'rgba(37, 99, 235, 0.15)', color: '#60a5fa', padding: '0.2rem 0.5rem', borderRadius: '16px', border: '1px solid rgba(37, 99, 235, 0.3)' }}>
            {columns.length} Columns • {data.length} {data.length === 1 ? 'Row' : 'Rows'}
          </span>
        </div>
      )}

      {/* Horizontal Scroll Hint */}
      {columns.length > 5 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', fontSize: '0.72rem', color: '#64748b', gap: '0.3rem', alignItems: 'center' }}>
          <span>Scroll horizontally to view all {columns.length} columns</span>
          <span>→</span>
        </div>
      )}

      {/* Table Scrollable Wrapper */}
      <div 
        className="custom-scrollbar"
        style={{ 
          width: '100%', 
          maxWidth: '100%',
          boxSizing: 'border-box',
          overflowX: 'auto', 
          overflowY: 'auto',
          maxHeight: '440px',
          borderRadius: '8px', 
          border: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'rgba(15, 23, 42, 0.4)',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2)'
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, textAlign: 'left', color: 'var(--text-main)', fontSize: '0.78rem' }}>
          <thead>
            <tr>
              <th style={{
                position: 'sticky',
                top: 0,
                zIndex: 10,
                background: '#0f172a',
                padding: '0.55rem 0.75rem',
                borderBottom: '2px solid rgba(255, 255, 255, 0.12)',
                color: '#94a3b8',
                fontWeight: 700,
                fontSize: '0.68rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                whiteSpace: 'nowrap',
                width: '40px',
                textAlign: 'center'
              }}>
                #
              </th>
              {columns.map(col => (
                <th key={col} style={{ 
                  position: 'sticky',
                  top: 0,
                  zIndex: 10,
                  background: '#0f172a',
                  padding: '0.55rem 0.85rem', 
                  borderBottom: '2px solid rgba(255, 255, 255, 0.12)', 
                  color: '#94a3b8',
                  fontWeight: 700,
                  fontSize: '0.68rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  whiteSpace: 'nowrap'
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rowIndex) => (
              <tr 
                key={rowIndex} 
                style={{ 
                  background: rowIndex % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)',
                  transition: 'background 0.15s ease'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(37, 99, 235, 0.08)'}
                onMouseLeave={(e) => e.currentTarget.style.background = rowIndex % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)'}
              >
                <td style={{ 
                  padding: '0.5rem 0.75rem', 
                  borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                  color: '#64748b',
                  fontWeight: 600,
                  textAlign: 'center',
                  whiteSpace: 'nowrap'
                }}>
                  {rowIndex + 1}
                </td>
                {columns.map(col => {
                  const val = row[col];
                  const strVal = val !== null && val !== undefined ? String(val) : '';
                  const isEditing = editingCell && editingCell.rowIndex === rowIndex && editingCell.col === col;
                  const isStateCol = col === 'STATE' || col === 'STATUS';
                  
                  let cellContent;
                  
                  if (isEditing) {
                    if (isStateCol) {
                      cellContent = (
                        <select
                          autoFocus
                          value={editingCell.value}
                          onChange={(e) => {
                            const newVal = e.target.value;
                            if (onCellEdit && newVal !== strVal) {
                              onCellEdit(row, editingCell.col, newVal);
                            }
                            setEditingCell(null);
                          }}
                          onBlur={() => setEditingCell(null)}
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') setEditingCell(null);
                          }}
                          style={{
                            width: '100%',
                            background: 'rgba(15, 23, 42, 0.95)',
                            border: '1px solid #38bdf8',
                            color: '#e2e8f0',
                            padding: '0.2rem 0.4rem',
                            borderRadius: '4px',
                            outline: 'none',
                            fontSize: '0.78rem',
                            cursor: 'pointer'
                          }}
                        >
                          <option value="">Select State...</option>
                          <option value="Pending">Pending</option>
                          <option value="In Progress">In Progress</option>
                          <option value="Approved">Approved</option>
                          <option value="Rejected">Rejected</option>
                        </select>
                      );
                    } else {
                      cellContent = (
                        <input
                          autoFocus
                          type="text"
                          value={editingCell.value}
                          onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
                          onKeyDown={(e) => handleKeyDown(e, row)}
                          onBlur={() => {
                            if (onCellEdit && editingCell.value !== strVal) {
                              onCellEdit(row, editingCell.col, editingCell.value);
                            }
                            setEditingCell(null);
                          }}
                          style={{
                            width: '100%',
                            background: 'rgba(15, 23, 42, 0.8)',
                            border: '1px solid #38bdf8',
                            color: '#e2e8f0',
                            padding: '0.2rem 0.4rem',
                            borderRadius: '4px',
                            outline: 'none',
                            fontSize: '0.78rem'
                          }}
                        />
                      );
                    }
                  } else {
                    if (isStateCol) {
                      const status = strVal;
                      const lower = status.toLowerCase();
                      const bg = (lower === 'approved') ? 'rgba(16, 185, 129, 0.1)' 
                               : (lower === 'rejected') ? 'rgba(239, 68, 68, 0.1)' 
                               : (lower === 'in progress') ? 'rgba(59, 130, 246, 0.1)' 
                               : 'rgba(245, 158, 11, 0.1)';
                      const color = (lower === 'approved') ? '#10b981' 
                                  : (lower === 'rejected') ? '#ef4444' 
                                  : (lower === 'in progress') ? '#3b82f6' 
                                  : '#f59e0b';
                      cellContent = (
                        <span style={{ 
                          fontSize: '0.7rem', padding: '0.25rem 0.5rem', borderRadius: '4px',
                          background: bg, color: color, fontWeight: 600, display: 'inline-block'
                        }}>
                          {status || 'Unknown'}
                        </span>
                      );
                    } else {
                      cellContent = strVal;
                    }
                  }
                  
                  return (
                    <td 
                      key={col} 
                      onMouseMove={(e) => !isEditing && handleMouseMove(e, strVal)}
                      onMouseLeave={handleMouseLeave}
                      onDoubleClick={() => handleDoubleClick(rowIndex, col, strVal)}
                      style={{ 
                        padding: isEditing && !isStateCol ? '0.2rem 0.4rem' : '0.5rem 0.85rem', 
                        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                        whiteSpace: 'nowrap',
                        maxWidth: '300px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        cursor: isEditing ? 'default' : (strVal.length > 40 ? 'pointer' : 'cell')
                      }}
                    >
                      {cellContent}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Custom Glassmorphism Tooltip for Truncated Cells */}
      {hoverTooltip.visible && (
        <div style={{
          position: 'fixed',
          top: hoverTooltip.y + 15,
          left: hoverTooltip.x + 15,
          maxWidth: '400px',
          background: 'rgba(15, 23, 42, 0.95)',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(56, 189, 248, 0.4)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          color: '#f8fafc',
          fontSize: '0.8rem',
          lineHeight: '1.5',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
          zIndex: 99999,
          pointerEvents: 'none',
          whiteSpace: 'normal',
          wordBreak: 'break-word',
          transform: `translate(${hoverTooltip.x + 420 > window.innerWidth ? 'calc(-100% - 30px)' : '0'}, ${hoverTooltip.y + 150 > window.innerHeight ? 'calc(-100% - 30px)' : '0'})`
        }}>
          {hoverTooltip.text}
        </div>
      )}
    </div>
  );
}
