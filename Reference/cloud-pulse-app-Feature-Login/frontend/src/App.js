import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster, toast } from 'sonner';
import InventoryPage from './pages/inventory/InventoryPage';
import ConfigPage from './pages/config/ConfigPage';
import ControlPage from './pages/control/ControlPage';
import AdminPage from './pages/admin/AdminPage';
import { Sidebar } from './components/layout/Sidebar';
import { LoginPage } from './pages/auth/LoginPage';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = React.useState(
    !!localStorage.getItem('cloud_pulse_token')
  );

  return (
    <BrowserRouter>
      <Toaster position="top-right" theme="dark" richColors duration={2500} />
      
      {!isAuthenticated ? (
        <Routes>
          <Route path="/login" element={<LoginPage onLogin={() => setIsAuthenticated(true)} />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      ) : (
        <div className="flex h-screen" onClick={() => toast.dismiss()}>
          <Sidebar />
          
          {/* Main content */}
          <main id="main-scroll-container" className="flex-1 overflow-y-auto p-6 bg-[#0a0a0f]">
            <Routes>
              <Route path="/login" element={<Navigate to="/control" replace />} />
              <Route path="/" element={<Navigate to="/control" replace />} />
              <Route path="/control" element={<ControlPage />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="*" element={<Navigate to="/control" replace />} />
            </Routes>
          </main>
        </div>
      )}
    </BrowserRouter>
  );
}
