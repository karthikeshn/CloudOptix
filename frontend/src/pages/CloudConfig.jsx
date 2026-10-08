import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FaAws } from 'react-icons/fa';

export default function CloudConfig({ token }) {
  const [configs, setConfigs] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [verifyingId, setVerifyingId] = useState(null);
  const [verifyStatus, setVerifyStatus] = useState({});
  
  const [provider, setProvider] = useState('AWS');
  const [accountName, setAccountName] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [useIamRole, setUseIamRole] = useState(false);
  const [accessKey, setAccessKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [assumeRoleArn, setAssumeRoleArn] = useState('');
  const [externalId, setExternalId] = useState('');
  
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchConfigs();
  }, []);

  const fetchConfigs = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/cloud-config', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setConfigs(res.data);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch cloud configs. Please make sure the backend is running properly.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this configuration?')) return;
    try {
      await axios.delete(`http://localhost:8000/api/cloud-config/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchConfigs();
    } catch (err) {
      console.error(err);
      setError('Failed to delete configuration.');
    }
  };

  const handleVerify = async (id) => {
    setVerifyStatus(prev => ({ ...prev, [id]: null }));
    setVerifyingId(id);
    try {
      const res = await axios.post(`http://localhost:8000/api/cloud-config/${id}/verify`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const { status, detail } = res.data;
      if (status === 'verified' || status === 'success') {
        setVerifyStatus(prev => ({ ...prev, [id]: { type: 'success', text: 'Active' } }));
        setMessage('Active');
        setTimeout(() => setMessage(null), 3000);
      } else if (status === 'expired') {
        setVerifyStatus(prev => ({ ...prev, [id]: { type: 'error', text: 'Credentials Expired' } }));
      } else if (status === 'invalid') {
        setVerifyStatus(prev => ({ ...prev, [id]: { type: 'error', text: 'Incorrect credentials' } }));
      } else {
        setVerifyStatus(prev => ({ ...prev, [id]: { type: 'error', text: detail || 'Verification Failed' } }));
      }
    } catch (err) {
      console.error(err);
      setVerifyStatus(prev => ({ ...prev, [id]: { type: 'error', text: 'Verification Failed' } }));
    } finally {
      setVerifyingId(null);
      fetchConfigs(); // Always refresh to get updated timestamp even on failure
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    try {
      const payload = {
        provider,
        account_name: accountName,
        region,
        use_iam_role: useIamRole,
        aws_access_key_id: accessKey,
        aws_secret_access_key: secretKey,
        aws_session_token: sessionToken || null,
        assume_role_arn: assumeRoleArn || null,
        external_id: externalId || null
      };

      if (editingId) {
        await axios.put(`http://localhost:8000/api/cloud-config/${editingId}`, payload, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setMessage('Cloud configuration updated successfully!');
      } else {
        await axios.post('http://localhost:8000/api/cloud-config', payload, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setMessage('Cloud configuration saved successfully!');
      }

      setShowForm(false);
      setEditingId(null);
      
      // Reset form
      setAccountName('');
      setAccessKey('');
      setSecretKey('');
      setSessionToken('');
      
      fetchConfigs();
    } catch (err) {
      console.error(err);
      if (err.response && err.response.data && err.response.data.detail) {
        setError(`Failed to save: ${err.response.data.detail}`);
      } else {
        setError('Failed to save cloud config. Check console for details.');
      }
    }
  };

  const handleEdit = (config) => {
    setEditingId(config.id);
    setProvider(config.provider || 'AWS');
    setAccountName(config.account_name || '');
    setRegion(config.region || 'us-east-1');
    setUseIamRole(config.use_iam_role || false);
    setAccessKey(config.aws_access_key_id || '');
    setSecretKey(config.aws_secret_access_key || '');
    setSessionToken(config.aws_session_token || '');
    setShowForm(true);
  };

  return (
    <div className="cloud-config-page">
      <div className="page-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="page-title">
          <h2 style={{ fontSize: '1.8rem', margin: '0 0 0.25rem 0', fontWeight: '700' }}>Cloud Configuration</h2>
          <p className="subtitle" style={{ color: 'var(--text-muted)', margin: 0 }}>Add AWS, Azure, or GCP credentials for resource discovery</p>
        </div>
        {!showForm && (
          <button className="primary-btn" onClick={() => { setEditingId(null); setShowForm(true); }} style={{ background: 'var(--primary)', color: '#fff', border: 'none', padding: '0.6rem 1.25rem', borderRadius: '8px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            Add Config
          </button>
        )}
      </div>
      
      {message && <div className="success-banner">✓ {message}</div>}
      {error && <div className="error-banner">⚠ {error}</div>}
      
      {!showForm ? (
        <div className="configs-list" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1.5rem' }}>
          {configs.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No accounts configured yet. Add one to get started.</p>
          ) : (
            configs.map(config => (
              <div key={config.id} className="config-list-item" style={{ 
                padding: '0.75rem 1rem', 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center'
              }}>
                {/* Left Side: Icon & Details */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  {config.provider === 'AWS' || !config.provider ? (
                    <div style={{ 
                      width: '42px', height: '42px', 
                      background: 'linear-gradient(145deg, #090d16 0%, #151c28 100%)', 
                      borderRadius: '12px', 
                      border: '1.5px solid rgba(255, 153, 0, 0.7)', 
                      display: 'flex', alignItems: 'center', justifyContent: 'center', 
                      boxShadow: '0 0 12px rgba(255, 153, 0, 0.25), inset 0 0 10px rgba(255, 153, 0, 0.12)',
                      flexShrink: 0
                    }}>
                      <FaAws size={26} color="#FF9900" />
                    </div>
                  ) : (
                    <div style={{ 
                      width: '42px', height: '42px', 
                      background: 'linear-gradient(135deg, #0f172a, #1e293b)', 
                      borderRadius: '12px', 
                      border: '1.5px solid rgba(255, 255, 255, 0.2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', 
                      color: '#fff', fontWeight: '700', fontSize: '0.85rem',
                      flexShrink: 0
                    }}>
                      {config.provider}
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                    <div style={{ fontSize: '0.95rem', fontWeight: '700', color: '#fff' }}>
                      {config.account_name || 'Unnamed Account'}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
                      <span>{config.provider} • {config.region}</span>
                      
                      {verifyStatus[config.id] ? (
                        <>
                          <span style={{
                            background: verifyStatus[config.id].type === 'error' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                            color: verifyStatus[config.id].type === 'error' ? '#f87171' : '#4ade80',
                            padding: '0.1rem 0.4rem',
                            borderRadius: '10px',
                            fontSize: '0.7rem'
                          }}>
                            {verifyStatus[config.id].text}
                          </span>
                          <span>•</span>
                          <span>Last Verified: {config.last_verified ? new Date(config.last_verified).toLocaleString() : 'Just now'}</span>
                        </>
                      ) : (
                        <>
                          {config.is_deleted ? (
                            <span style={{ background: 'rgba(100, 116, 139, 0.15)', color: '#94a3b8', padding: '0.1rem 0.4rem', borderRadius: '10px', fontSize: '0.7rem' }}>
                              Disconnected (Deleted)
                            </span>
                          ) : (
                            <>
                              {config.status === 'verified' && (
                                <span style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80', padding: '0.1rem 0.4rem', borderRadius: '10px', fontSize: '0.7rem' }}>
                                  Active
                                </span>
                              )}
                              {config.status === 'expired' && (
                                <span style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', padding: '0.1rem 0.4rem', borderRadius: '10px', fontSize: '0.7rem' }}>
                                  Credentials Expired
                                </span>
                              )}
                              {config.status === 'invalid' && (
                                <span style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', padding: '0.1rem 0.4rem', borderRadius: '10px', fontSize: '0.7rem' }}>
                                  Incorrect credentials
                                </span>
                              )}
                              {(!config.status || config.status === 'unverified') && (
                                <span style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', padding: '0.1rem 0.4rem', borderRadius: '10px', fontSize: '0.7rem' }}>
                                  Unverified
                                </span>
                              )}
                            </>
                          )}
                          
                          {config.last_verified && (
                            <>
                              <span>•</span>
                              <span>Last Verified: {new Date(config.last_verified).toLocaleString()}</span>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Right Side: Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                  <button 
                    onClick={() => handleVerify(config.id)}
                    disabled={verifyingId === config.id || config.is_deleted}
                    style={{ 
                      background: 'transparent', border: 'none', 
                      color: 'var(--primary)', fontWeight: '600', 
                      cursor: (verifyingId === config.id || config.is_deleted) ? 'default' : 'pointer', 
                      display: 'flex', alignItems: 'center', gap: '0.35rem',
                      opacity: (verifyingId === config.id || config.is_deleted) ? 0.3 : 1,
                      fontSize: '0.85rem'
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: verifyingId === config.id ? 'spin 1s linear infinite' : 'none' }}>
                      <polyline points="23 4 23 10 17 10"></polyline>
                      <polyline points="1 20 1 14 7 14"></polyline>
                      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Refresh Status
                  </button>

                  <button 
                    onClick={() => handleEdit(config)}
                    style={{ background: 'transparent', border: 'none', color: '#3b82f6', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                    title="Edit account to restore"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                  </button>
                  
                  {!config.is_deleted && (
                    <button 
                      onClick={() => handleDelete(config.id)}
                      style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                      title="Delete account"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        <line x1="10" y1="11" x2="10" y2="17"></line>
                        <line x1="14" y1="11" x2="14" y2="17"></line>
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="config-form-card" style={{ marginTop: '1.5rem' }}>
          <form onSubmit={handleSave}>
            <div className="form-row three-cols">
              <div className="form-group">
                <label>Provider</label>
                <select value={provider} onChange={(e) => setProvider(e.target.value)} className="form-input">
                  <option value="AWS">Amazon Web Services</option>
                  <option value="Azure">Microsoft Azure</option>
                  <option value="GCP">Google Cloud Platform</option>
                </select>
              </div>
              <div className="form-group">
                <label>Account Name</label>
                <input 
                  type="text" 
                  value={accountName} 
                  onChange={(e) => setAccountName(e.target.value)} 
                  className="form-input"
                  placeholder="My AWS Account"
                  required
                />
              </div>
              <div className="form-group">
                <label>Region</label>
                <input 
                  type="text" 
                  value={region} 
                  onChange={(e) => setRegion(e.target.value)} 
                  className="form-input"
                  placeholder="us-east-1"
                />
              </div>
            </div>

            <div className="form-row">
              <label className="checkbox-label">
                <input 
                  type="checkbox" 
                  checked={useIamRole} 
                  onChange={(e) => setUseIamRole(e.target.checked)} 
                />
                Use IAM Role (EC2 instance profile)
              </label>
            </div>

            {!useIamRole && (
              <div className="form-row three-cols">
                <div className="form-group">
                  <label>Access Key</label>
                  <input 
                    type="text" 
                    value={accessKey} 
                    onChange={(e) => setAccessKey(e.target.value)} 
                    className="form-input"
                    placeholder="AKIAIOSFODNN7EXAMPLE"
                  />
                </div>
                <div className="form-group">
                  <label>Secret Key</label>
                  <input 
                    type="password" 
                    value={secretKey} 
                    onChange={(e) => setSecretKey(e.target.value)} 
                    className="form-input"
                    placeholder="••••••••"
                  />
                </div>
                <div className="form-group">
                  <label>Session Token (Optional)</label>
                  <input 
                    type="text" 
                    value={sessionToken} 
                    onChange={(e) => setSessionToken(e.target.value)} 
                    className="form-input"
                    placeholder="For temp credentials"
                  />
                </div>
              </div>
            )}

            <div className="form-actions">
              <button type="submit" className="btn btn-primary btn-save">{editingId ? 'Update Configuration' : 'Save Configuration'}</button>
              <button type="button" className="btn btn-secondary" onClick={() => { setShowForm(false); setEditingId(null); }}>Cancel</button>
            </div>
          </form>
        </div>
      )}
      <style>
        {`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
  );
}
