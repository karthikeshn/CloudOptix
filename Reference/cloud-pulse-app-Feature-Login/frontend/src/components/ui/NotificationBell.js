import React, { useState, useEffect, useRef } from 'react';
import { Bell, Check, Info, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { apiClient } from '../../api/api';
import { formatDynamicLocalTime } from '../../utils/dateFormatter';

export function NotificationBell() {
  const [notifications, setNotifications] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  const lastSeenIdRef = useRef(null);

  const fetchNotifications = async () => {
    try {
      const res = await apiClient.get('/notifications');
      if (res.status === 200) {
        const newNotifs = res.data;
        setNotifications(newNotifs);
        
        if (newNotifs.length > 0) {
          const maxId = Math.max(...newNotifs.map(n => n.id));
          if (lastSeenIdRef.current !== null && maxId > lastSeenIdRef.current) {
            window.dispatchEvent(new CustomEvent('app:refresh-data'));
          }
          lastSeenIdRef.current = maxId;
        }
      }
    } catch (e) {
      console.error('Failed to fetch notifications', e);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000); // 30s polling
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const unreadCount = notifications.filter(n => !n.is_read).length;

  const markAllAsRead = async () => {
    try {
      await apiClient.post('/notifications/mark-read', {});
      fetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const markAsRead = async (id) => {
    try {
      await apiClient.post('/notifications/mark-read', { id });
      fetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const getIcon = (type) => {
    switch(type?.toUpperCase()) {
      case 'SUCCESS': return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      case 'ERROR': return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default: return <Info className="w-4 h-4 text-blue-500" />;
    }
  };

  const formatTime = (dateStr) => {
    return formatDynamicLocalTime(dateStr);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 text-zinc-400 hover:text-white transition-colors"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 max-h-[400px] overflow-hidden flex flex-col bg-[#131315] border border-[#26262b] rounded-xl shadow-2xl z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-3 border-b border-[#26262b] flex items-center justify-between bg-[#0e1015]">
            <h3 className="text-sm font-semibold text-white">Notifications</h3>
            {unreadCount > 0 && (
              <button 
                onClick={markAllAsRead}
                className="text-[11px] text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1"
              >
                <Check className="w-3 h-3" /> Mark all read
              </button>
            )}
          </div>
          
          <div className="overflow-y-auto flex-1 p-2 space-y-1">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-xs text-zinc-500 italic">No notifications</div>
            ) : (
              notifications.map(n => (
                <div 
                  key={n.id} 
                  onClick={() => { if (!n.is_read) markAsRead(n.id); }}
                  className={`p-3 rounded-lg border flex gap-3 transition-colors cursor-pointer ${n.is_read ? 'bg-[#161b22] border-transparent opacity-60 hover:opacity-100' : 'bg-[#1c2128] border-[#30363d] shadow-sm'}`}
                >
                  <div className="shrink-0 mt-0.5">{getIcon(n.type)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <h4 className={`text-[13px] font-semibold truncate ${n.is_read ? 'text-zinc-400' : 'text-zinc-200'}`}>{n.title}</h4>
                      <span className="text-[10px] text-zinc-500 whitespace-nowrap">{formatTime(n.created_at)}</span>
                    </div>
                    <p className="text-xs text-zinc-400 leading-snug break-words">{n.message}</p>
                  </div>
                  {!n.is_read && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0 self-center" />}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

