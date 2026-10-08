import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ChevronRight, Activity } from 'lucide-react';
import { login } from '../../api/api';
import { toast } from 'sonner';

export const LoginPage = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      toast.error('Please enter both username and password');
      return;
    }
    setLoading(true);
    try {
      const response = await login(username, password);
      localStorage.setItem('cloud_pulse_token', response.data.access_token);
      onLogin(); // Tell App.js we are logged in
      navigate('/');
    } catch (error) {
      toast.error('Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0c] text-white p-4">
      
      {/* Background glow effects */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-emerald-600/10 blur-[100px] rounded-full pointer-events-none" />

      <div className="w-full max-w-md z-10">
        
        {/* Logo and Brand */}
        <div className="flex flex-col items-center mb-10">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-emerald-500/20 border border-white/10 flex items-center justify-center mb-4 shadow-xl backdrop-blur-md">
            <Activity className="h-8 w-8 text-blue-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Cloud Pulse</h1>
          <p className="text-zinc-400 text-sm">Sign in to manage your cloud infrastructure</p>
        </div>

        {/* Login Form */}
        <div className="bg-[#12141a]/90 backdrop-blur-xl border border-zinc-800/80 p-8 rounded-2xl shadow-2xl">
          <form onSubmit={handleLogin} className="space-y-5">
            
            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-zinc-400 uppercase tracking-wider">Username</label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User className="h-4 w-4 text-zinc-500 group-focus-within:text-blue-400 transition-colors" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-zinc-900/50 border border-zinc-800 text-white text-sm rounded-xl pl-10 pr-4 py-3 outline-none focus:bg-zinc-900 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-zinc-600"
                  placeholder="admin"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-zinc-400 uppercase tracking-wider">Password</label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-4 w-4 text-zinc-500 group-focus-within:text-blue-400 transition-colors" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-900/50 border border-zinc-800 text-white text-sm rounded-xl pl-10 pr-4 py-3 outline-none focus:bg-zinc-900 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-zinc-600"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-8 bg-blue-600 hover:bg-blue-500 text-white font-medium py-3 rounded-xl transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:hover:bg-blue-600 shadow-lg shadow-blue-900/20 hover:shadow-blue-900/40"
            >
              {loading ? 'Authenticating...' : 'Sign In'}
              {!loading && <ChevronRight className="h-4 w-4" />}
            </button>
            
          </form>
        </div>
        
        {/* Footer */}
        <p className="text-center text-[11px] text-zinc-500 mt-8">
          Securely encrypted via standard JWT and AES-GCM
        </p>
      </div>
    </div>
  );
};
