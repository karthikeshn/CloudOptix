import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import axios from 'axios';
import DynamicTable from '../components/common/DynamicTable';
import CategoryFilter from '../components/tickets/CategoryFilter';
import ScriptFilter from '../components/tickets/ScriptFilter';

export default function Results({ token }) {
  const { activeAccount } = useOutletContext() || {};
  const [scripts, setScripts] = useState([]);
  const [loadingScripts, setLoadingScripts] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('All Categories');
  const [selectedScript, setSelectedScript] = useState('');
  const [resultData, setResultData] = useState(null);
  const [resultFilename, setResultFilename] = useState('');
  const [resultTimestamp, setResultTimestamp] = useState(null);
  const [loadingResult, setLoadingResult] = useState(false);
  const [resultMessage, setResultMessage] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [isCategoryDropdownOpen, setIsCategoryDropdownOpen] = useState(false);
  const [isScriptDropdownOpen, setIsScriptDropdownOpen] = useState(false);

  const SCRIPT_CATEGORIES = {
    "Storage & Volumes": ["EBS", "Efs", "S3", "ECR", "Bucket", "Disk", "gp2", "gp3"],
    "Snapshots & Backups": ["Snapshot", "Backup", "AMI", "RecoveryPoint"],
    "Databases & Cache": ["RDS", "DynamoDB", "Elastic Cache", "Valkey", "ElasticSearch", "Database"],
    "Networking & IP": ["IPV4", "IPV6", "Vpc", "Cloudfront", "Data Transfer", "Global Accelerator", "Egress", "Load Balancer"],
    "Compute & Management": ["EC2", "EKS", "Eks", "Lambda", "CodePipeline", "Codepipeline", "Compute Optimizer", "CloudFormation", "Access Analyzer"],
    "Analytics & Security": ["Glue", "Guardduty", "Kinesis"],
  };

  const getScriptCategory = (scriptName) => {
    const name = scriptName.toLowerCase();
    for (const [category, keywords] of Object.entries(SCRIPT_CATEGORIES)) {
      if (keywords.some(kw => name.includes(kw.toLowerCase()))) {
        return category;
      }
    }
    if (name.includes('fix_') || name.includes('test_') || name.includes('refactor_')) {
      return "Internal Utilities";
    }
    return "Other";
  };

  const formatScriptName = (filename) => {
    if (!filename) return '';
    return filename.replace('.py', '').trim();
  };

  useEffect(() => {
    const fetchScripts = async () => {
      setLoadingScripts(true);
      try {
        const res = await axios.get('http://localhost:8000/api/scripts', {
          headers: { Authorization: `Bearer ${token}` }
        });
        const allScripts = res.data.scripts || [];
        setScripts(allScripts);
        if (allScripts.length > 0) {
          setSelectedScript(allScripts[0]);
        }
      } catch (err) {
        console.error("Error fetching scripts:", err);
      } finally {
        setLoadingScripts(false);
      }
    };
    fetchScripts();
  }, [token]);

  const filteredScripts = scripts.filter(s => {
    if (selectedCategory === "All Categories") return true;
    return getScriptCategory(s) === selectedCategory;
  });

  const handleCategoryChange = (category) => {
    setSelectedCategory(category);
    const filtered = scripts.filter(s => {
      if (category === "All Categories") return true;
      return getScriptCategory(s) === category;
    });
    if (filtered.length > 0) {
      setSelectedScript(filtered[0]);
    } else {
      setSelectedScript('');
    }
  };

  useEffect(() => {
    if (!activeAccount) return;
    if (!selectedScript) {
      setResultData(null);
      setResultMessage('No ticket selected.');
      return;
    }

    const fetchResult = async () => {
      setLoadingResult(true);
      setResultMessage('');
      setResultData(null);
      setResultFilename('');
      
      try {
        const params = {};
        if (selectedScript !== 'All Tickets' && selectedScript !== 'All Scripts') {
          params.script_name = selectedScript;
        }
        if (activeAccount?.id) {
          params.account_id = activeAccount.id;
        }

        const res = await axios.get('http://localhost:8000/api/tickets', {
          headers: { Authorization: `Bearer ${token}` },
          params: params
        });

        if (res.data && res.data.length > 0) {
          // Extract data from the database tickets directly so they stay in perfect sync
          const ticketsData = res.data.map(ticket => {
            let row = {};
            try {
              row = JSON.parse(ticket.details || '{}');
            } catch (e) {
              row = {};
            }
            
            // The magic fix: Overwrite the raw JSON 'STATE' or 'STATUS' to strictly match the DB Ticket Status
            // Delete any existing variations to prevent duplicate columns in 'All Tickets' view
            const stateKeys = Object.keys(row).filter(k => k.toLowerCase() === 'state' || k.toLowerCase() === 'status');
            stateKeys.forEach(k => delete row[k]);
            
            // Inject exactly one canonical STATE column
            row['STATE'] = ticket.status;
            
            // Inject the real database ticket ID into the ID column so it matches the Approval page
            const idKeys = Object.keys(row).filter(k => k.toLowerCase() === 'id');
            idKeys.forEach(k => delete row[k]);
            row['id'] = ticket.id;
            
            // Inject metadata for API edits (hidden from table via DynamicTable update)
            row['__script_name'] = ticket.script_name;
            
            return row;
          });
          
          setResultData(ticketsData);
          setResultFilename(selectedScript + '_db_export.csv');
          setResultTimestamp(new Date(res.data[0].created_at).getTime() / 1000);
        } else {
          setResultMessage('No tickets generated for this script yet.');
        }
      } catch (err) {
        setResultMessage(err.response?.data?.detail || 'Failed to load output results.');
      } finally {
        setLoadingResult(false);
      }
    };

    fetchResult();
  }, [selectedScript, activeAccount, token]);

  const handleDownload = async () => {
    if (!resultFilename) return;
    try {
      const response = await axios.get(`http://localhost:8000/api/scripts/download/${resultFilename}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', resultFilename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  const displayedData = React.useMemo(() => {
    if (!resultData || !Array.isArray(resultData)) return [];
    if (!searchTerm.trim()) return resultData;

    const term = searchTerm.toLowerCase();
    return resultData.filter(row => 
      Object.values(row).some(val => 
        String(val).toLowerCase().includes(term)
      )
    );
  }, [resultData, searchTerm]);

  const handleCellEdit = async (row, colName, newValue) => {
    try {
      let resId = "unknown";
      for (const candidate of ["resourceId", "resourceNameOrId", "resource_id", "Resource ID", "VolumeId", "InstanceId"]) {
        if (row[candidate] && String(row[candidate]).trim()) {
          resId = String(row[candidate]).trim();
          break;
        }
      }
      if (resId === "unknown") {
        for (const [key, val] of Object.entries(row)) {
          const k_lower = String(key).toLowerCase();
          const val_str = String(val).trim();
          if (val_str && (k_lower.includes("id") || k_lower.includes("arn") || k_lower.includes("name"))) {
            if (k_lower === "accountid") continue;
            resId = val_str;
            break;
          }
        }
      }

      const actualScriptName = row['__script_name'] || selectedScript;

      await axios.put('http://localhost:8000/api/tickets/sync-edit', {
        script_name: actualScriptName,
        resource_id: resId,
        field: colName,
        value: newValue
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const updatedData = resultData.map(r => {
        if (r === row) {
          return { ...r, [colName]: newValue };
        }
        return r;
      });
      setResultData(updatedData);
      
    } catch (err) {
      console.error(err);
      alert("Failed to sync edit to DB: " + (err.response?.data?.detail || err.message));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
      
      {/* Header Section */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', width: '100%', boxSizing: 'border-box' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: '800', margin: 0, background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', letterSpacing: '-0.5px' }}>
            Ticket Results & Output Sheets
          </h2>
          <p style={{ color: 'var(--text-muted)', margin: '0.15rem 0 0 0', fontSize: '0.8rem' }}>
            View, search, and export processed report datasets for optimized cloud tickets
          </p>
        </div>

        {activeAccount && (
          <div style={{ background: 'var(--glass-bg)', border: 'var(--glass-border)', padding: '0.35rem 0.75rem', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0 }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981', boxShadow: '0 0 6px #10b981' }}></span>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Active Account:</span>
            <strong style={{ color: 'var(--text-main)', fontSize: '0.8rem' }}>{activeAccount.account_name || activeAccount.provider}</strong>
          </div>
        )}
      </div>

      {/* Side-by-Side Control Bar: Category Dropdown & Ticket Dropdown */}
      <div className="card" style={{ padding: '0.85rem 1.25rem', borderRadius: '12px', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
        
        {/* Dropdown 1: Select Category */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: '1 1 200px', minWidth: 0 }}>
          <label style={{ fontSize: '0.8rem', fontWeight: '600', color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
            Category:
          </label>
          <div style={{ flex: 1 }}>
            <CategoryFilter 
              categories={SCRIPT_CATEGORIES}
              selectedCategory={selectedCategory}
              onSelectCategory={handleCategoryChange}
              isOpen={isCategoryDropdownOpen}
              setIsOpen={setIsCategoryDropdownOpen}
            />
          </div>
        </div>

        {/* Dropdown 2: Select Ticket */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: '2 1 260px', minWidth: 0 }}>
          <label style={{ fontSize: '0.8rem', fontWeight: '600', color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
            Ticket:
          </label>
          <div style={{ flex: 1 }}>
            <ScriptFilter 
              scripts={filteredScripts}
              selectedScript={selectedScript || "Select Script"}
              onSelectScript={setSelectedScript}
              isOpen={isScriptDropdownOpen}
              setIsOpen={setIsScriptDropdownOpen}
              formatLabel={formatScriptName}
            />
          </div>
        </div>

        {/* Search Input */}
        {resultData && resultData.length > 0 && (
          <div style={{ position: 'relative', flex: '1 1 180px', minWidth: '140px' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              type="text"
              placeholder="Filter table rows..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem 0.5rem 2rem',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: 'var(--text-main)',
                fontSize: '0.78rem',
                outline: 'none',
                boxSizing: 'border-box'
              }}
            />
          </div>
        )}
      </div>

      {/* Main Table Output Container */}
      <div className="card" style={{ padding: '1rem', borderRadius: '12px', width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
        
        {/* Table Header Bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem', width: '100%', boxSizing: 'border-box' }}>
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: '700', color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {selectedScript === 'All Tickets' ? 'All Tickets' : (selectedScript ? formatScriptName(selectedScript) : 'No Selection')}
            </h3>
            {resultTimestamp && (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Sheet Last Updated: {new Date(resultTimestamp * 1000).toLocaleString()}
              </span>
            )}
          </div>

          {resultFilename && (
            <button
              onClick={handleDownload}
              title={`Download ${resultFilename}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '0.4rem',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                color: '#fff',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(16, 185, 129, 0.25)',
                flexShrink: 0
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
          )}
        </div>

        {/* Content Display */}
        {loadingResult ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem', gap: '0.5rem', color: 'var(--text-muted)' }}>
            <div className="spinner" style={{ width: '28px', height: '28px', border: '2px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
            <span style={{ fontSize: '0.8rem' }}>Loading result sheet data...</span>
          </div>
        ) : resultData && resultData.length > 0 ? (
          <div style={{ width: '100%', maxWidth: '100%', overflow: 'hidden', boxSizing: 'border-box' }}>
            <DynamicTable data={displayedData} onCellEdit={handleCellEdit} />
            <div style={{ marginTop: '0.5rem', textAlign: 'right', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Showing {displayedData.length} of {resultData.length} records
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', background: 'rgba(255, 255, 255, 0.015)', borderRadius: '8px', border: '1px dashed rgba(255, 255, 255, 0.1)' }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: '0.5rem', opacity: 0.5, color: '#38bdf8' }}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <h4 style={{ margin: '0 0 0.3rem 0', color: 'var(--text-main)', fontSize: '0.95rem' }}>No Output Data Available</h4>
            <p style={{ margin: 0, maxWidth: '380px', fontSize: '0.8rem', lineHeight: '1.4' }}>
              {resultMessage || "No output sheet found for this ticket. Navigate to the 'Tickets Run' page and run this ticket to generate its output dataset."}
            </p>
          </div>
        )}
      </div>

    </div>
  );
}
