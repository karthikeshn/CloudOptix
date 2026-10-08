import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

// Custom Checkbox Dropdown Component
function MultiSelectDropdown({ label, options, selectedValues, onChange, disabled, placeholder }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleOption = (option) => {
    if (selectedValues.includes(option)) {
      onChange(selectedValues.filter(val => val !== option));
    } else {
      onChange([...selectedValues, option]);
    }
  };

  const displayText = selectedValues.length === 0 
    ? placeholder 
    : selectedValues.length === 1 
      ? selectedValues[0] 
      : `${selectedValues.length} selected`;

  return (
    <div style={{ flex: 1, position: 'relative' }} ref={dropdownRef}>
      <label style={{ display: 'block', marginBottom: '0.75rem', fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-muted)' }}>{label}</label>
      
      <div 
        onClick={() => !disabled && setIsOpen(!isOpen)}
        style={{ 
          width: '100%', padding: '0.85rem', borderRadius: '8px', 
          border: '1px solid var(--glass-border)', background: 'var(--glass-bg)', 
          color: 'var(--text-main)', fontSize: '1rem', 
          cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}
      >
        <span>{displayText}</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>

      {isOpen && !disabled && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '0.5rem',
          background: 'var(--bg-active-item)', border: '1px solid var(--border-color)',
          borderRadius: '8px', padding: '0.5rem', maxHeight: '250px', overflowY: 'auto',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)', zIndex: 100, animation: 'fadeIn 0.2s ease-out'
        }}>
          {options.map(option => {
            const isSelected = selectedValues.includes(option);
            return (
              <div 
                key={option}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleOption(option);
                }}
                style={{
                  padding: '0.6rem 0.8rem',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  color: isSelected ? '#fff' : 'var(--text-muted)',
                  background: isSelected ? '#3b82f6' : 'transparent',
                  transition: 'all 0.15s',
                  marginBottom: '2px'
                }}
                onMouseEnter={(e) => {
                  if(!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                }}
                onMouseLeave={(e) => {
                  if(!isSelected) e.currentTarget.style.background = 'transparent';
                }}
              >
                {option}
              </div>
            );
          })}
          {options.length === 0 && <div style={{ padding: '0.5rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>No options available</div>}
        </div>
      )}
    </div>
  );
}

export default function CostExplorer({ token }) {
  const [services, setServices] = useState([]);
  const [ecosystems, setEcosystems] = useState([]);
  const [selectedServices, setSelectedServices] = useState([]);
  const [selectedEcosystems, setSelectedEcosystems] = useState([]);
  const [costData, setCostData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [servicesLoading, setServicesLoading] = useState(true);
  
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState('desc'); // 'asc' or 'desc'

  const displayedData = React.useMemo(() => {
    let data = [...costData];
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      data = data.filter(row => String(row.resource_id).toLowerCase().includes(term));
    }
    if (sortOrder === 'asc') {
      data.sort((a, b) => a.cost - b.cost);
    } else if (sortOrder === 'desc') {
      data.sort((a, b) => b.cost - a.cost);
    }
    return data;
  }, [costData, searchTerm, sortOrder]);

  // Fetch initial list of services
  useEffect(() => {
    setServicesLoading(true);
    axios.get('http://127.0.0.1:8000/api/costs/services', {
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      setServices(res.data);
      setServicesLoading(false);
    }).catch(err => {
      console.error(err);
      setServicesLoading(false);
    });
  }, [token]);

  // Fetch ecosystems when selected services change
  useEffect(() => {
    if (selectedServices.length > 0) {
      const queryParams = selectedServices.map(s => `services=${encodeURIComponent(s)}`).join('&');
      axios.get(`http://127.0.0.1:8000/api/costs/ecosystems?${queryParams}`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(res => {
        setEcosystems(res.data);
        // Clean up ecosystems that are no longer valid for the new services
        setSelectedEcosystems(prev => prev.filter(e => res.data.includes(e)));
      }).catch(err => console.error(err));
    } else {
      setEcosystems([]);
      setSelectedEcosystems([]);
      setCostData([]);
    }
  }, [selectedServices, token]);

  // Fetch cost data when both services and ecosystems are selected
  useEffect(() => {
    if (selectedServices.length > 0 && selectedEcosystems.length > 0) {
      setLoading(true);
      const sQuery = selectedServices.map(s => `services=${encodeURIComponent(s)}`).join('&');
      const eQuery = selectedEcosystems.map(e => `ecosystems=${encodeURIComponent(e)}`).join('&');
      
      axios.get(`http://127.0.0.1:8000/api/costs/resources?${sQuery}&${eQuery}`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(res => {
        setCostData(res.data);
        setLoading(false);
      }).catch(err => {
        console.error(err);
        setLoading(false);
      });
    } else {
        setCostData([]);
    }
  }, [selectedServices, selectedEcosystems, token]);

  return (
    <div className="page-container" style={{ padding: '2rem' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>Cost Explorer</h2>
        <p style={{ color: 'var(--text-muted)', margin: '0.5rem 0 0 0' }}>Select multiple services and ecosystems to view combined resource-level costs.</p>
      </div>
      
      <div style={{ display: 'flex', gap: '2rem', marginBottom: '2rem' }}>
        <MultiSelectDropdown 
          label="1. Select Main Services"
          options={services}
          selectedValues={selectedServices}
          onChange={setSelectedServices}
          disabled={services.length === 0 || servicesLoading}
          placeholder={servicesLoading ? "Loading services from billing files..." : "-- Select Services --"}
        />
        
        <MultiSelectDropdown 
          label="2. Select Ecosystems"
          options={ecosystems}
          selectedValues={selectedEcosystems}
          onChange={setSelectedEcosystems}
          disabled={selectedServices.length === 0}
          placeholder="-- Select Ecosystems --"
        />
      </div>

      <div className="card" style={{ padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: 0, paddingBottom: '1rem', borderBottom: '1px solid var(--glass-border)', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            Resource Costs
            {loading && <span className="spinner" style={{ width: '20px', height: '20px', border: '2px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></span>}
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ position: 'relative' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              <input
                type="text"
                placeholder="Search Resource ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  padding: '0.5rem 0.75rem 0.5rem 2rem',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: 'var(--text-main)',
                  fontSize: '0.8rem',
                  outline: 'none',
                  minWidth: '220px'
                }}
              />
            </div>
            
            <button
              onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                padding: '0.5rem 0.8rem', borderRadius: '8px',
                background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
                color: 'var(--text-main)', fontSize: '0.8rem', cursor: 'pointer', transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'var(--glass-bg)'}
            >
              Sort Cost: {sortOrder === 'desc' ? 'Highest First ↓' : 'Lowest First ↑'}
            </button>
          </div>
        </h3>
        
        {selectedServices.length === 0 || selectedEcosystems.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)', fontSize: '1.1rem' }}>
            Please select at least one Service and Ecosystem to view granular costs.
          </div>
        ) : costData.length === 0 && !loading ? (
          <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)', fontSize: '1.1rem' }}>
            No costs found for this selection.
          </div>
        ) : (
          <div style={{ overflowX: 'auto', marginTop: '1rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Resource ID</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Usage Type</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Operation</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Usage Amount</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Cost ($)</th>
                </tr>
              </thead>
              <tbody>
                {displayedData.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', transition: 'background 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding: '1rem', fontWeight: 500, color: 'var(--text-main)' }}>{row.resource_id}</td>
                    <td style={{ padding: '1rem', color: 'var(--text-muted)' }}>{row.usage_type}</td>
                    <td style={{ padding: '1rem', color: 'var(--text-muted)' }}>{row.operation}</td>
                    <td style={{ padding: '1rem', color: 'var(--text-muted)' }}>{row.usage_amount.toLocaleString()}</td>
                    <td style={{ padding: '1rem', color: '#10b981', fontWeight: 600 }}>${row.cost.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
