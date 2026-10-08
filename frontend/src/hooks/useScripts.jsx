import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const ScriptsContext = createContext();

export const ScriptsProvider = ({ token, children }) => {
  const [scripts, setScripts] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [error, setError] = useState(null);
  
  const [runningScript, setRunningScript] = useState(null);
  const [activeScript, setActiveScript] = useState(null);
  const [tableData, setTableData] = useState(null);
  const [resultFilename, setResultFilename] = useState(null);

  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0, currentScript: '', completedCount: 0 });
  const [batchSummary, setBatchSummary] = useState(null);
  const [selectedScripts, setSelectedScripts] = useState([]);

  useEffect(() => {
    if (token) {
      fetchScripts();
      fetchConfigs();
    }
  }, [token]);

  const fetchConfigs = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/cloud-config', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setConfigs(res.data);
      if (res.data.length > 0) {
        setSelectedAccountId(res.data[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchScripts = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/scripts', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setScripts(res.data.scripts || []);
    } catch (err) {
      setError('Failed to fetch scripts.');
    }
  };

  const runScript = async (scriptName) => {
    setRunningScript(scriptName);
    setError(null);
    setBatchSummary(null);
    setTableData(null);
    setActiveScript(null);
    setResultFilename(null);
    try {
      const res = await axios.post(
        `http://localhost:8000/api/scripts/${encodeURIComponent(scriptName)}/run`,
        { account_id: selectedAccountId || null },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.data.data) {
        setTableData(res.data.data);
        setActiveScript(scriptName);
        setResultFilename(res.data.filename);
      }
    } catch (err) {
      if (err.response && err.response.data && err.response.data.detail) {
        setError(`Script Error: ${err.response.data.detail}`);
      } else {
        setError(`Failed to run script: ${err.message}`);
      }
    } finally {
      setRunningScript(null);
    }
  };

  const runBatchScripts = async (selectedScripts) => {
    if (selectedScripts.length === 0 || isBatchRunning) return;
    setIsBatchRunning(true);
    setError(null);
    setBatchSummary(null);
    setTableData(null);
    setActiveScript(null);

    const total = selectedScripts.length;
    let completed = 0;
    const errors = [];
    const scriptCounts = [];

    for (let i = 0; i < total; i++) {
      const scriptName = selectedScripts[i];
      setBatchProgress({ current: i + 1, total, currentScript: scriptName, completedCount: completed });
      try {
        const res = await axios.post(
          `http://localhost:8000/api/scripts/${encodeURIComponent(scriptName)}/run`,
          { account_id: selectedAccountId || null },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        completed++;
        
        const count = res.data.data ? res.data.data.length : 0;
        scriptCounts.push(`${scriptName.replace('.py', '')}: ${count}`);

        if (res.data.data && i === total - 1) {
          setTableData(res.data.data);
          setActiveScript(scriptName);
          setResultFilename(res.data.filename);
        }
      } catch (err) {
        const detail = err.response?.data?.detail || err.message;
        errors.push(`${scriptName}: ${detail}`);
      }
    }

    setIsBatchRunning(false);
    setBatchProgress({ current: 0, total: 0, currentScript: '', completedCount: 0 });

    if (errors.length > 0) {
      setError(`Batch execution completed with ${errors.length} error(s): ${errors.join('; ')}`);
    } else {
      setBatchSummary(`✓ Successfully executed ${completed} scripts! Tickets generated per script: ${scriptCounts.join(', ')}.`);
    }
  };

  const downloadCSV = async (filename) => {
    if (!filename) return;
    try {
      const response = await axios.get(`http://localhost:8000/api/scripts/download/${filename}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <ScriptsContext.Provider value={{
      scripts, configs, selectedAccountId, setSelectedAccountId, error, setError,
      runningScript, activeScript, tableData, resultFilename,
      isBatchRunning, batchProgress, batchSummary, setBatchSummary,
      runScript, runBatchScripts, downloadCSV,
      selectedScripts, setSelectedScripts
    }}>
      {children}
    </ScriptsContext.Provider>
  );
};

export const useScripts = () => useContext(ScriptsContext);
