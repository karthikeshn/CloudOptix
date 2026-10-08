import React, { useState, useEffect, useRef } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { FaAws } from 'react-icons/fa';
import { ScriptsProvider } from '../hooks/useScripts.jsx';

export default function Dashboard({ setToken, token, userRole }) {
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeAccount, setActiveAccount] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  
  // User Menu & Password Modal State
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  
  // Password Change State
  const [passwordForm, setPasswordForm] = useState({ old_password: '', new_password: '', confirm_password: '' });
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [currentPasswordStatus, setCurrentPasswordStatus] = useState(null);

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError("New passwords do not match");
      return;
    }
    try {
      await axios.put('http://127.0.0.1:8000/api/users/me/password', {
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setPasswordSuccess('Password updated successfully!');
      setPasswordError('');
      setPasswordForm({ old_password: '', new_password: '', confirm_password: '' });
      setCurrentPasswordStatus(null);
    } catch (err) {
      setPasswordError(err.response?.data?.detail || 'Failed to change password');
      setPasswordSuccess('');
    }
  };

  const handleVerifyPassword = async () => {
    if (!passwordForm.old_password) return;
    setIsValidating(true);
    setCurrentPasswordStatus(null);
    try {
      const res = await axios.post('http://127.0.0.1:8000/api/users/me/verify-password', {
        password: passwordForm.old_password
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.valid) {
        setCurrentPasswordStatus('success');
      } else {
        setCurrentPasswordStatus('error');
      }
    } catch (err) {
      setCurrentPasswordStatus('error');
    } finally {
      setIsValidating(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    axios.get('http://127.0.0.1:8000/api/cloud-config', {
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      if (res.data && res.data.length > 0) {
        setAccounts(res.data);
        setActiveAccount(res.data[0]);
      } else {
        setAccounts([]);
        setActiveAccount(null);
      }
    }).catch(err => {
      console.error(err);
      setAccounts([]);
      setActiveAccount(null);
    });

    axios.get('http://127.0.0.1:8000/api/users/me', {
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      setCurrentUser(res.data);
    }).catch(err => console.error(err));
  }, [token]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    setToken(null);
    navigate('/login');
  };

  return (
    <div className="dashboard-layout">
      {/* Sidebar */}
      <nav className={`sidebar ${isSidebarOpen ? '' : 'closed'}`}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h1 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.35rem', fontWeight: '700', letterSpacing: '-0.5px' }}>
            <span style={{ color: "var(--primary)" }}>☁</span> 
            <span className="sidebar-text">Cloud Optix</span>
          </h1>
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="icon-btn sidebar-toggle-btn" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {isSidebarOpen ? (
                <polyline points="15 18 9 12 15 6"></polyline>
              ) : (
                <polyline points="9 18 15 12 9 6"></polyline>
              )}
            </svg>
          </button>
        </div>
        
        <div className="sidebar-category">Platform Console</div>
        
        <NavLink to="/" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} end title="Overview">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
          <span className="sidebar-text">Overview</span>
        </NavLink>
        
        {(userRole === 'admin' || userRole === 'manager') && (
          <NavLink to="/cloud-config" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="Cloud Configuration">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            <span className="sidebar-text">Cloud Configuration</span>
          </NavLink>
        )}
        
        <NavLink to="/tickets-run" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="Tickets Run">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
          <span className="sidebar-text">Tickets Run</span>
        </NavLink>

        <NavLink to="/cost-explorer" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="Cost Explorer">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
          <span className="sidebar-text">Cost Explorer</span>
        </NavLink>



        {(userRole === 'admin' || userRole === 'manager') && (
          <NavLink to="/approvals" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="Approval Dashboard">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
            <span className="sidebar-text">Approval Dashboard</span>
          </NavLink>
        )}

        {userRole === 'engineer' && (
          <NavLink to="/assignments" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="My Assignments">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect><path d="M9 14h6"></path><path d="M9 10h6"></path><path d="M9 18h6"></path></svg>
            <span className="sidebar-text">My Assignments</span>
          </NavLink>
        )}

        {userRole === 'admin' && (
          <NavLink to="/admin-control" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} title="Admin Control">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
            <span className="sidebar-text">Admin Control</span>
          </NavLink>
        )}



        {/* User Info Card */}
        {isSidebarOpen && currentUser && (
          <div style={{ marginTop: 'auto', padding: '0.85rem', borderRadius: '10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', fontWeight: 'bold' }}>
                {currentUser.username.charAt(0).toUpperCase()}
              </div>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {currentUser.username}
              </div>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              Role: 
              <span className={`status-badge ${userRole === 'admin' ? 'admin' : userRole === 'engineer' ? 'engineer' : 'manager'}`} style={{ padding: '0.1rem 0.4rem', fontSize: '0.65rem', textTransform: 'capitalize' }}>
                {userRole}
              </span>
            </div>
          </div>
        )}
      </nav>

      {/* Main Wrapper */}
      <div className="main-wrapper">
        {/* Top Navbar */}
        <header className="top-navbar">
          <div className="search-bar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <input type="text" placeholder="Search resources, services..." />
          </div>
          
          <div className="top-nav-actions">
            <div className="account-selector" style={{ position: 'relative' }}>
              <span className="label">Active Account</span>
              <div 
                className="account-pill"
                onClick={() => accounts.length > 0 && setIsDropdownOpen(!isDropdownOpen)}
                style={{ cursor: accounts.length > 0 ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: '0.45rem' }}
              >
                <FaAws size={16} color="#FF9900" />
                {activeAccount ? (activeAccount.account_name || activeAccount.provider) : "No Accounts"}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
              </div>
              
              {isDropdownOpen && accounts.length > 0 && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '0.5rem',
                  background: 'var(--glass-bg)',
                  border: 'var(--glass-border)',
                  borderRadius: '12px',
                  padding: '0.5rem',
                  minWidth: '200px',
                  boxShadow: 'var(--glass-shadow)',
                  zIndex: 100
                }}>
                  {accounts.map(acc => (
                    <div 
                      key={acc.id}
                      onClick={() => {
                        setActiveAccount(acc);
                        setIsDropdownOpen(false);
                      }}
                      style={{
                        padding: '0.75rem 1rem',
                        cursor: 'pointer',
                        borderRadius: '8px',
                        color: activeAccount && acc.id === activeAccount.id ? 'var(--primary)' : 'var(--text-main)',
                        background: activeAccount && acc.id === activeAccount.id ? 'rgba(37, 99, 235, 0.1)' : 'transparent',
                        transition: 'background 0.2s',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between'
                      }}
                      onMouseEnter={(e) => {
                        if (!activeAccount || acc.id !== activeAccount.id) {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!activeAccount || acc.id !== activeAccount.id) {
                          e.currentTarget.style.background = 'transparent';
                        }
                      }}
                    >
                      {acc.account_name || acc.provider}
                      {activeAccount && acc.id === activeAccount.id && (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button className="icon-btn" onClick={() => navigate('/settings')} title="Settings">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>

            <button className="icon-btn" title="Notifications">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
            </button>
            
            <div style={{ position: 'relative' }} ref={userMenuRef}>
              <button 
                className="icon-btn" 
                onClick={() => setIsUserMenuOpen(!isUserMenuOpen)} 
                title="User Menu"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              </button>

              {isUserMenuOpen && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '0.5rem',
                  background: 'var(--glass-bg)',
                  border: 'var(--glass-border)',
                  borderRadius: '12px',
                  padding: '0.5rem',
                  minWidth: '180px',
                  boxShadow: 'var(--glass-shadow)',
                  zIndex: 100
                }}>
                  <div 
                    onClick={() => {
                      setIsUserMenuOpen(false);
                      setIsPasswordModalOpen(true);
                    }}
                    style={{
                      padding: '0.5rem 0.75rem',
                      cursor: 'pointer',
                      borderRadius: '8px',
                      color: 'var(--text-main)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.85rem'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    Change Password
                  </div>
                  <div 
                    onClick={handleLogout}
                    style={{
                      padding: '0.5rem 0.75rem',
                      cursor: 'pointer',
                      borderRadius: '8px',
                      color: '#ef4444',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.85rem'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                    Sign Out
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Content Area */}
        <main className="main-content">
          <ScriptsProvider token={token}>
            <Outlet context={{ activeAccount }} />
          </ScriptsProvider>
        </main>
      </div>

      {/* Change Password Modal */}
      {isPasswordModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '400px', padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Change Password</h3>
              <button 
                onClick={() => {
                  setIsPasswordModalOpen(false);
                  setPasswordSuccess('');
                  setPasswordError('');
                  setPasswordForm({ old_password: '', new_password: '', confirm_password: '' });
                  setCurrentPasswordStatus(null);
                }} 
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            
            {passwordError && <div className="error-msg" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>{passwordError}</div>}
            {passwordSuccess && <div style={{ color: '#10b981', marginBottom: '1rem', fontSize: '0.85rem', background: 'rgba(16, 185, 129, 0.1)', padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>{passwordSuccess}</div>}
            
            <form onSubmit={handlePasswordSubmit}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.85rem' }}>Current Password</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input 
                    type="password" className="form-input" required 
                    value={passwordForm.old_password} 
                    onChange={e => {
                      setPasswordForm({...passwordForm, old_password: e.target.value});
                      setCurrentPasswordStatus(null);
                    }} 
                    style={{ paddingRight: '40px' }}
                  />
                  <button 
                    type="button" 
                    onClick={handleVerifyPassword}
                    disabled={!passwordForm.old_password || isValidating}
                    style={{
                      position: 'absolute', right: '10px', background: 'none', border: 'none',
                      cursor: (!passwordForm.old_password || isValidating) ? 'not-allowed' : 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: currentPasswordStatus === 'success' ? '#10b981' : currentPasswordStatus === 'error' ? '#ef4444' : '#64748b'
                    }}
                    title="Verify Password"
                  >
                    {isValidating ? (
                      <span className="spinner" style={{ width: '16px', height: '16px', border: '2px solid rgba(255,255,255,0.1)', borderTopColor: '#38bdf8', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></span>
                    ) : currentPasswordStatus === 'success' ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                    ) : currentPasswordStatus === 'error' ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                    )}
                  </button>
                </div>
                {currentPasswordStatus === 'error' && <div style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>Incorrect password</div>}
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.85rem' }}>New Password</label>
                <input 
                  type="password" className="form-input" required 
                  value={passwordForm.new_password} onChange={e => setPasswordForm({...passwordForm, new_password: e.target.value})} 
                />
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label style={{ fontSize: '0.85rem' }}>Confirm New Password</label>
                <input 
                  type="password" className="form-input" required 
                  value={passwordForm.confirm_password} onChange={e => setPasswordForm({...passwordForm, confirm_password: e.target.value})} 
                />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>Update Password</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
