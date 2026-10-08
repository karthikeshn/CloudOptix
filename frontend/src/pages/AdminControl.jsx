import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function AdminControl({ token }) {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({ username: '', email: '', password: '', role: 'engineer' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('http://localhost:8000/api/users', formData, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSuccess('User created successfully!');
      setError('');
      setFormData({ username: '', email: '', password: '', role: 'engineer' });
      
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create user');
      setSuccess('');
    }
  };

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Admin Control Panel</h2>
        <button className="btn btn-primary" onClick={() => navigate('/user-directory')} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
            <circle cx="9" cy="7" r="4"></circle>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
          </svg>
          User Directory
        </button>
      </div>
      <div className="card-body">
        <div style={{ maxWidth: '400px', margin: '0 auto' }}>
          <div className="form-panel" style={{ background: 'var(--bg-active-item)', padding: '1.5rem', borderRadius: '12px', border: 'var(--glass-border)' }}>
            <h3 style={{ marginTop: 0, marginBottom: '1.5rem', fontSize: '1.1rem', color: 'var(--primary)' }}>Create New User</h3>
            {error && <div className="error-msg" style={{ marginBottom: '1rem' }}>{error}</div>}
            {success && <div style={{ color: '#10b981', marginBottom: '1rem', fontSize: '0.9rem' }}>{success}</div>}
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Username</label>
                <input 
                  type="text" className="form-input" required 
                  value={formData.username} onChange={e => setFormData({...formData, username: e.target.value})} 
                  placeholder="Enter username"
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Email</label>
                <input 
                  type="email" className="form-input" 
                  value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} 
                  placeholder="name@company.com"
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Password</label>
                <input 
                  type="password" className="form-input" required 
                  value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} 
                  placeholder="Set initial password"
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Role</label>
                <select 
                  className="form-input" 
                  value={formData.role} onChange={e => setFormData({...formData, role: e.target.value})}
                >
                  <option value="engineer">Engineer</option>
                  <option value="manager">Manager</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button type="submit" className="btn btn-primary" style={{ marginTop: '0.5rem' }}>Create User</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
