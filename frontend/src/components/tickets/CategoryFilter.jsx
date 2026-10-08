import React from 'react';
import { FaCogs } from 'react-icons/fa';

export default function CategoryFilter({
  categories,
  selectedCategory,
  onSelectCategory,
  isOpen,
  setIsOpen
}) {
  return (
    <div style={{ position: 'relative' }}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: '0.65rem 1rem',
          borderRadius: '8px',
          border: '1px solid var(--border-color)',
          background: 'var(--glass-bg)',
          color: 'var(--text-main)',
          fontSize: '0.85rem',
          fontWeight: 600,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.6rem',
          minWidth: '200px',
          justifyContent: 'space-between',
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <FaCogs color="#94a3b8" />
          {selectedCategory}
        </div>
        <span style={{ fontSize: '0.6rem', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
      </button>

      {isOpen && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 0.5rem)',
          left: 0,
          background: 'var(--bg-active-item)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '0.5rem',
          zIndex: 50,
          minWidth: '220px',
          maxHeight: '350px',
          overflowY: 'auto',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          {['All Categories', ...Object.keys(categories)].map(cat => (
            <div 
              key={cat}
              onClick={() => { onSelectCategory(cat); setIsOpen(false); }}
              style={{
                padding: '0.6rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.85rem',
                color: selectedCategory === cat ? '#fff' : 'var(--text-muted)',
                background: selectedCategory === cat ? 'var(--primary)' : 'transparent',
                transition: 'all 0.15s'
              }}
              onMouseEnter={(e) => {
                if(selectedCategory !== cat) e.target.style.background = 'rgba(255,255,255,0.05)';
              }}
              onMouseLeave={(e) => {
                if(selectedCategory !== cat) e.target.style.background = 'transparent';
              }}
            >
              {cat}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
