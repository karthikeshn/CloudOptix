import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import TicketsRun from './pages/TicketsRun';
import CloudConfig from './pages/CloudConfig';
import Overview from './pages/Overview';
import Results from './pages/Results';
import AdminControl from './pages/AdminControl';
import UserDirectory from './pages/UserDirectory';
import Settings from './pages/Settings';
import ApprovalDashboard from './pages/ApprovalDashboard';
import MyAssignments from './pages/MyAssignments';
import CostExplorer from './pages/CostExplorer';
const parseJwt = (token) => {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch (e) {
    return null;
  }
};

function ProtectedRoute({ token, children }) {
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || null);
  
  const payload = token ? parseJwt(token) : null;
  const userRole = payload ? payload.role : null;

  const handleSetToken = (newToken) => {
    setToken(newToken);
    if (newToken) {
      localStorage.setItem('token', newToken);
    } else {
      localStorage.removeItem('token');
    }
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login setToken={handleSetToken} />} />
        
        <Route 
          path="/" 
          element={
            <ProtectedRoute token={token}>
              <Dashboard setToken={handleSetToken} token={token} userRole={userRole} />
            </ProtectedRoute>
          }
        >
          <Route index element={<Overview token={token} />} />
          <Route path="cloud-config" element={userRole === 'admin' || userRole === 'manager' ? <CloudConfig token={token} /> : <Navigate to="/" replace />} />
          <Route path="tickets-run" element={<TicketsRun token={token} />} />
          <Route path="results" element={<Results token={token} />} />
          <Route path="admin-control" element={userRole === 'admin' ? <AdminControl token={token} /> : <Navigate to="/" replace />} />
          <Route path="user-directory" element={userRole === 'admin' ? <UserDirectory token={token} /> : <Navigate to="/" replace />} />
          <Route path="approvals" element={userRole === 'admin' || userRole === 'manager' ? <ApprovalDashboard token={token} /> : <Navigate to="/" replace />} />
          <Route path="assignments" element={<MyAssignments token={token} />} />
          <Route path="cost-explorer" element={<CostExplorer token={token} />} />
          <Route path="settings" element={<Settings token={token} />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
