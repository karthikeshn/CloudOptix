import React, { useState, useEffect } from 'react';
import DynamicTable from '../components/common/DynamicTable';
import { FaAws, FaServer } from 'react-icons/fa';
import { useScripts } from '../hooks/useScripts.jsx';
import ScriptCard from '../components/tickets/ScriptCard';
import BatchExecutionPanel from '../components/tickets/BatchExecutionPanel';
import CategoryFilter from '../components/tickets/CategoryFilter';
import { getScriptCategory, getCategoryTheme, renderAwsIcon, getScriptDescription, SCRIPT_CATEGORIES } from '../utils/ticketUtils';
import scriptManifestData from '../utils/scriptManifest.json';

const scriptManifest = scriptManifestData || {};

export default function TicketsRun({ token, userRole }) {
  const {
    scripts, configs, selectedAccountId, setSelectedAccountId, error, setError,
    runningScript, activeScript, tableData, resultFilename,
    isBatchRunning, batchProgress, batchSummary, setBatchSummary,
    runScript, runBatchScripts, downloadCSV,
    selectedScripts, setSelectedScripts
  } = useScripts();

  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [isCategoryDropdownOpen, setIsCategoryDropdownOpen] = useState(false);
  
  const [selectedService, setSelectedService] = useState("All Services");
  const [isServiceDropdownOpen, setIsServiceDropdownOpen] = useState(false);
  
  useEffect(() => {
    setSelectedService("All Services");
  }, [selectedCategory]);


  const [isScriptDropdownOpen, setIsScriptDropdownOpen] = useState(false);
  const [isTargetEnvDropdownOpen, setIsTargetEnvDropdownOpen] = useState(false);

  const toggleSelectScript = (scriptName) => {
    setSelectedScripts(prev => 
      prev.includes(scriptName) 
        ? prev.filter(s => s !== scriptName)
        : [...prev, scriptName]
    );
  };

  const handleSelectAll = (visibleScripts) => {
    const allVisibleSelected = visibleScripts.length > 0 && visibleScripts.every(s => selectedScripts.includes(s));
    if (allVisibleSelected) {
      setSelectedScripts(prev => prev.filter(s => !visibleScripts.includes(s)));
    } else {
      const combined = Array.from(new Set([...selectedScripts, ...visibleScripts]));
      setSelectedScripts(combined);
    }
  };

  const groupedScripts = scripts.reduce((acc, script) => {
    const category = getScriptCategory(script);
    if (!acc[category]) acc[category] = [];
    acc[category].push(script);
    return acc;
  }, {});

  const filteredScriptsByCategory = (selectedCategory === "All Categories" 
    ? scripts 
    : groupedScripts[selectedCategory] || []).sort((a, b) => a.localeCompare(b));

  // Dynamically pull all unique services directly from the script manifest!
  const availableServices = Array.from(
    new Set(
      filteredScriptsByCategory.map(script => {
        const entry = scriptManifest[script] || {};
        return entry.service || "AWS";
      })
    )
  ).sort((a, b) => a.localeCompare(b));


  const visibleScripts = selectedService === "All Services" 
    ? filteredScriptsByCategory 
    : filteredScriptsByCategory.filter(s => {
        const entry = scriptManifest[s] || {};
        const srv = entry.service || "AWS";
        return srv.toLowerCase() === selectedService.toLowerCase();
      });

  const allVisibleSelected = visibleScripts.length > 0 && visibleScripts.every(s => selectedScripts.includes(s));

  const currentConfig = configs.find(c => c.id.toString() === selectedAccountId?.toString());

  return (
    <div className="tickets-run-container" style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem', animation: 'fadeIn 0.4s ease-out' }}>
      
      <div style={{
        padding: '0.75rem 1.25rem',
        borderRadius: '8px',
        background: currentConfig ? (
            currentConfig.is_deleted ? 'rgba(100, 116, 139, 0.1)' 
          : currentConfig.status === 'verified' ? 'rgba(34, 197, 94, 0.1)' 
          : currentConfig.status === 'expired' ? 'rgba(239, 68, 68, 0.1)' 
          : 'rgba(234, 179, 8, 0.1)'
        ) : 'rgba(148, 163, 184, 0.1)',
        borderLeft: `4px solid ${
          currentConfig ? (
              currentConfig.is_deleted ? '#64748b'
            : currentConfig.status === 'verified' ? '#22c55e' 
            : currentConfig.status === 'expired' ? '#ef4444' 
            : '#eab308'
          ) : '#94a3b8'
        }`,
        color: currentConfig ? (
            currentConfig.is_deleted ? '#94a3b8'
          : currentConfig.status === 'verified' ? '#86efac' 
          : currentConfig.status === 'expired' ? '#fca5a5' 
          : '#fde047'
        ) : '#cbd5e1',
        fontSize: '0.85rem',
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        animation: 'fadeIn 0.3s'
      }}>
        <span>Environment Status: {
          currentConfig 
            ? (currentConfig.is_deleted ? 'Disconnected (Deleted)'
               : currentConfig.status === 'verified' ? 'Active' 
               : currentConfig.status === 'expired' ? 'Expired' 
               : 'Unverified/Invalid') 
            : 'No active environment configured'
        }</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.25rem', flexWrap: 'wrap', background: 'rgba(15, 23, 42, 0.4)', padding: '1rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
        
        {/* 1. Target Environment */}
        {configs.length > 0 && (
          <div style={{ flex: 1, minWidth: '160px' }}>
            <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Target Environment
            </label>
            <div style={{ position: 'relative' }}>
              <button 
                onClick={() => setIsTargetEnvDropdownOpen(!isTargetEnvDropdownOpen)}
                style={{ 
                  width: '100%', padding: '0.65rem 1rem', 
                  borderRadius: '8px', background: 'var(--glass-bg)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: 600,
                  cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <FaServer color="#FF9900" />
                  {currentConfig ? `${currentConfig.account_name || currentConfig.provider} (${currentConfig.region})` : 'Select Environment'}
                </div>
                <span style={{ fontSize: '0.6rem', transform: isTargetEnvDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
              </button>

              {isTargetEnvDropdownOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 0.5rem)', left: 0, right: 0,
                  background: 'var(--bg-active-item)', border: '1px solid var(--border-color)',
                  borderRadius: '8px', zIndex: 100, padding: '0.5rem',
                  boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
                  animation: 'fadeIn 0.2s ease-out'
                }}>
                  {configs.map(config => (
                    <div 
                      key={config.id} 
                      onClick={() => { setSelectedAccountId(config.id); setIsTargetEnvDropdownOpen(false); }}
                      style={{ 
                        padding: '0.6rem 0.8rem', borderRadius: '6px', cursor: 'pointer',
                        fontSize: '0.85rem', 
                        color: selectedAccountId?.toString() === config.id.toString() ? '#fff' : 'var(--text-muted)',
                        background: selectedAccountId?.toString() === config.id.toString() ? 'var(--primary)' : 'transparent',
                        transition: 'all 0.15s'
                      }}
                      onMouseEnter={(e) => {
                        if (selectedAccountId?.toString() !== config.id.toString()) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                      }}
                      onMouseLeave={(e) => {
                        if (selectedAccountId?.toString() !== config.id.toString()) e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      {config.account_name || config.provider} ({config.region})
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 2. Filter Category */}
        <div style={{ flex: 1, minWidth: '140px' }}>
          <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Filter Category
          </label>
          <CategoryFilter 
            categories={SCRIPT_CATEGORIES}
            selectedCategory={selectedCategory}
            onSelectCategory={setSelectedCategory}
            isOpen={isCategoryDropdownOpen}
            setIsOpen={setIsCategoryDropdownOpen}
          />
        </div>

        {/* 2.5. Filter Service */}
        <div style={{ flex: 1, minWidth: '140px', position: 'relative' }}>
          <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Filter Service
          </label>
          <button 
            onClick={() => setIsServiceDropdownOpen(!isServiceDropdownOpen)}
            style={{ 
              width: '100%', padding: '0.65rem 1rem', 
              borderRadius: '8px', background: 'var(--glass-bg)',
              border: '1px solid var(--border-color)',
              fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: 600,
              cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              {selectedService}
            </div>
            <span style={{ fontSize: '0.6rem', transform: isServiceDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
          </button>

          {isServiceDropdownOpen && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 0.5rem)', left: 0, right: 0,
              background: 'var(--bg-active-item)', border: '1px solid var(--border-color)',
              borderRadius: '8px', zIndex: 100, padding: '0.5rem', maxHeight: '350px', overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
              animation: 'fadeIn 0.2s ease-out'
            }}>
              {["All Services", ...availableServices].map(service => (
                <div 
                  key={service} 
                  onClick={() => { setSelectedService(service); setIsServiceDropdownOpen(false); }}
                  style={{ 
                    padding: '0.6rem 0.8rem', borderRadius: '6px', cursor: 'pointer',
                    fontSize: '0.85rem', 
                    color: selectedService === service ? '#fff' : 'var(--text-muted)',
                    background: selectedService === service ? '#3b82f6' : 'transparent',
                    transition: 'all 0.15s',
                    marginBottom: '2px'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedService !== service) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                  }}
                  onMouseLeave={(e) => {
                    if (selectedService !== service) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  {service}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 3. Script Selection Dropdown with Checkboxes */}
        <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
          <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Select Scripts
          </label>
          <button 
            onClick={() => setIsScriptDropdownOpen(!isScriptDropdownOpen)}
            style={{ 
              width: '100%', padding: '0.65rem 1rem', 
              borderRadius: '8px', background: 'var(--glass-bg)',
              border: '1px solid var(--border-color)',
              fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: 600,
              cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
            }}
          >
            <span>
              {selectedScripts.length === 0 ? 'Select scripts...' : `${selectedScripts.length} scripts selected`}
            </span>
            <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', transform: isScriptDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
          </button>
          
          {isScriptDropdownOpen && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 0.5rem)', left: 0, right: 0,
              background: 'var(--bg-active-item)', border: '1px solid var(--border-color)',
              borderRadius: '8px', zIndex: 100, maxHeight: '350px', overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0,0,0,0.5)', padding: '0.5rem',
              animation: 'fadeIn 0.2s ease-out'
            }}>
              {visibleScripts.length === 0 ? (
                <div style={{ padding: '0.6rem 0.8rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>No scripts in this category</div>
              ) : (
                visibleScripts.map(script => {
                  const isChecked = selectedScripts.includes(script);
                  return (
                    <div 
                      key={script}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSelectScript(script);
                      }}
                      style={{ 
                        padding: '0.6rem 0.8rem', cursor: 'pointer', fontSize: '0.85rem',
                        borderRadius: '6px',
                        color: isChecked ? '#fff' : 'var(--text-muted)',
                        background: isChecked ? 'var(--primary)' : 'transparent',
                        transition: 'all 0.15s',
                        marginBottom: '2px'
                      }}
                      onMouseEnter={(e) => {
                        if (!isChecked) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                      }}
                      onMouseLeave={(e) => {
                        if (!isChecked) e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      <span style={{ wordBreak: 'break-word', paddingRight: '0.5rem' }}>{script}</span>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>

      <BatchExecutionPanel 
        selectedScriptsCount={selectedScripts.length}
        selectedScripts={selectedScripts}
        isBatchRunning={isBatchRunning}
        batchProgress={batchProgress}
        batchSummary={batchSummary}
        onRunBatch={() => runBatchScripts(selectedScripts)}
        onDeselectAll={() => setSelectedScripts([])}
        onRemoveScript={(script) => toggleSelectScript(script)}
        onClearSummary={() => setBatchSummary(null)}
      />

      {error && (
        <div style={{
          padding: '0.85rem 1.15rem', background: 'rgba(239, 68, 68, 0.1)', 
          borderLeft: '4px solid #ef4444', borderRadius: '8px', color: '#fca5a5',
          fontSize: '0.85rem', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px',
          wordBreak: 'break-word'
        }}>
          <div style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', lineHeight: '1.4' }}>
            {error}
          </div>
          <button 
            onClick={() => setError(null)}
            style={{
              background: 'rgba(255, 255, 255, 0.1)', border: 'none', color: '#fca5a5',
              cursor: 'pointer', padding: '0.3rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
              borderRadius: '4px', flexShrink: 0, transition: 'all 0.2s', alignSelf: 'flex-start'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
              e.currentTarget.style.color = '#fff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.color = '#fca5a5';
            }}
            title="Dismiss"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      )}
      


      {tableData && tableData.length > 0 && activeScript && (
        <div style={{ marginTop: '1.5rem', animation: 'slideUpFade 0.4s ease-out' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '1.25rem', fontWeight: 700 }}>
              Execution Output: <span style={{ color: '#38bdf8' }}>{activeScript}</span>
            </h3>
            {resultFilename && (
              <button 
                onClick={() => downloadCSV(resultFilename)}
                className="btn btn-secondary"
                style={{ fontSize: '0.8rem', padding: '0.45rem 0.95rem' }}
              >
                Download Raw File ({resultFilename})
              </button>
            )}
          </div>
          <DynamicTable data={tableData} scriptName={activeScript} />
        </div>
      )}

    </div>
  );
}
