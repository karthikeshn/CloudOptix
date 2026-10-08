import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function UserDirectory({ token }) {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [editingUserId, setEditingUserId] = useState(null);
  const [editForm, setEditForm] = useState({ email: '', role: '', is_active: true });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchUsers = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/users', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUsers(response.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [token]);

  const handleEditClick = (user) => {
    setEditingUserId(user.id);
    setEditForm({ email: user.email || '', role: user.role, is_active: user.is_active });
  };

  const handleCancelEdit = () => {
    setEditingUserId(null);
    setEditForm({ email: '', role: '', is_active: true });
    setError('');
  };

  const handleSaveEdit = async (userId) => {
    try {
      await axios.put(`http://localhost:8000/api/users/${userId}`, editForm, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSuccess('User updated successfully!');
      setError('');
      setEditingUserId(null);
      fetchUsers();
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update user');
    }
  };

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>User Directory</h2>
        <button className="btn btn-primary" onClick={() => navigate('/admin-control')} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line>
          </svg>
          Add User
        </button>
      </div>
      <div className="card-body">
        {error && <div className="error-msg" style={{ marginBottom: '1rem' }}>{error}</div>}
        {success && <div style={{ color: '#10b981', marginBottom: '1rem' }}>{success}</div>}
        
        <div className="table-panel" style={{ overflowX: 'auto' }}>
          <table className="dynamic-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>{u.username}</td>
                  
                  {/* Email Column */}
                  <td>
                    {editingUserId === u.id ? (
                      <input 
                        type="email" 
                        className="form-input" 
                        value={editForm.email} 
                        onChange={(e) => setEditForm({...editForm, email: e.target.value})}
                        style={{ padding: '0.25rem', fontSize: '0.85rem' }}
                      />
                    ) : (
                      u.email || '-'
                    )}
                  </td>
                  
                  {/* Role Column */}
                  <td>
                    {editingUserId === u.id ? (
                      <select 
                        className="form-input" 
                        value={editForm.role} 
                        onChange={(e) => setEditForm({...editForm, role: e.target.value})}
                        style={{ 
                          padding: '0.25rem 0.5rem', 
                          fontSize: '0.85rem',
                          background: 'rgba(15, 23, 42, 0.95)',
                          border: '1px solid #38bdf8',
                          color: '#e2e8f0',
                          borderRadius: '4px',
                          outline: 'none',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="engineer">Engineer</option>
                        <option value="manager">Manager</option>
                        <option value="admin">Admin</option>
                      </select>
                    ) : (
                      <span className={`status-badge ${u.role}`}>
                        {u.role}
                      </span>
                    )}
                  </td>
                  
                  {/* Status Column */}
                  <td>
                    {editingUserId === u.id ? (
                      <select 
                        className="form-input" 
                        value={editForm.is_active ? 'true' : 'false'} 
                        onChange={(e) => setEditForm({...editForm, is_active: e.target.value === 'true'})}
                        style={{ 
                          padding: '0.25rem 0.5rem', 
                          fontSize: '0.85rem',
                          background: 'rgba(15, 23, 42, 0.95)',
                          border: '1px solid #38bdf8',
                          color: '#e2e8f0',
                          borderRadius: '4px',
                          outline: 'none',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="true">Active</option>
                        <option value="false">Deactivate</option>
                      </select>
                    ) : (
                      <span className={`status-badge ${u.is_active ? 'active' : 'deactivated'}`}>
                        {u.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    )}
                  </td>
                  
                  {/* Actions Column */}
                  <td>
                    {editingUserId === u.id ? (
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button 
                          className="btn btn-primary" 
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
                          onClick={() => handleSaveEdit(u.id)}
                        >
                          Save
                        </button>
                        <button 
                          className="btn btn-secondary" 
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
                          onClick={handleCancelEdit}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button 
                        className="btn btn-secondary" 
                        style={{ padding: '0.25rem 0.75rem', fontSize: '0.8rem' }}
                        onClick={() => handleEditClick(u)}
                      >
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && <tr><td colSpan="6">No users found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
