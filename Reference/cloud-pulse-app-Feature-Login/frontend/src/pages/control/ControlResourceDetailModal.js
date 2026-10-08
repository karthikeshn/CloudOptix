import React from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Server, Database, X, Globe, Tag as TagIcon, LayoutTemplate } from 'lucide-react';
import { formatIdentifier, formatName } from '../../utils/ui-utils';
import { EmptyState } from '../../components/ui/EmptyState';

export function ControlResourceDetailModal({ resource, onClose }) {
  if (!resource) return null;

  let tags = {};
  try {
    if (resource.tags_json) tags = typeof resource.tags_json === 'string' ? JSON.parse(resource.tags_json) : resource.tags_json;
  } catch (e) {}

  const getStatusStyle = (status) => {
    const s = (status || '').toUpperCase();
    if (s === 'RUNNING' || s === 'AVAILABLE') return 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]';
    if (s === 'STOPPED' || s === 'PAUSED') return 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]';
    if (s === 'UNKNOWN') return 'bg-zinc-500 shadow-[0_0_8px_rgba(113,113,122,0.4)]';
    return 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]';
  };

  return createPortal(
    <AnimatePresence>
      {resource && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center w-screen h-screen bg-black/70 backdrop-blur-sm"
        >
          <motion.div 
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-[#131315] border border-[#26262b] rounded-xl w-full max-w-[480px] shadow-2xl overflow-hidden flex flex-col h-[550px] max-h-[85vh]"
          >
        <div className="px-4 py-3 border-b border-[#26262b] bg-[#131315] flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-[13px] font-bold text-zinc-100 flex items-center gap-2">
              {resource.service_type?.toLowerCase() === 'ec2' ? <Server className="h-3.5 w-3.5 text-blue-400" /> : <Database className="h-3.5 w-3.5 text-blue-400" />}
              {formatName(resource.name, resource.resource_id, resource.cloud_provider) || formatIdentifier(resource.resource_id, resource.cloud_provider)}
            </h2>
            <p className="text-[11px] text-zinc-500 mt-0.5 uppercase tracking-wider font-semibold">{resource.service_type} • {resource.region}</p>
          </div>
          <motion.button 
            whileHover={{ scale: 1.05, backgroundColor: '#26262b' }}
            whileTap={{ scale: 0.95 }}
            onClick={onClose} 
            className="p-1.5 text-zinc-500 rounded-md transition-colors"
          >
            <X className="h-4 w-4" />
          </motion.button>
        </div>

        <div className="p-4 overflow-y-auto space-y-4 bg-[#0a0a0f] flex-1 min-h-0">
          <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Resource ID</label>
            <div className="font-mono text-[11px] text-zinc-300 break-all select-all">
              {resource.resource_id}
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Provider</label>
              <p className="text-[12px] font-bold text-zinc-200 capitalize flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-zinc-500" /> {resource.cloud_provider}
              </p>
            </div>
            <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Account</label>
              <p className="text-[12px] font-bold text-zinc-200">{resource.account_name}</p>
            </div>
            <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Status</label>
              <p className="text-[12px] font-bold text-zinc-200 flex items-center gap-1.5">
                <span className={`inline-block w-2 h-2 rounded-full ${getStatusStyle(resource.status)}`} />
                {resource.status}
              </p>
            </div>
            <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Control Type</label>
              <p className="text-[12px] font-bold text-amber-400 capitalize">{resource.control_type?.replace(/_/g, ' ').toLowerCase()}</p>
            </div>
          </div>

          <div className="space-y-4">
            {resource.instance_spec && (
              <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Instance Spec</label>
                <div className="font-mono text-[11px] font-semibold text-zinc-200 break-all flex items-center gap-2">
                  <LayoutTemplate className="h-3.5 w-3.5 text-zinc-500"/>
                  {resource.instance_spec}
                </div>
              </div>
            )}

            {resource.parent_resource_id && (
              <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Master Instance</label>
                <div className="font-mono text-[10px] text-zinc-300 break-all flex items-center gap-2">
                  <Server className="h-3.5 w-3.5 text-zinc-400"/>
                  {resource.parent_resource_id}
                </div>
              </div>
            )}

            <div>
              <div className="flex items-center gap-2 mb-2">
                <TagIcon className="h-3.5 w-3.5 text-zinc-500" />
                <h3 className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Tags</h3>
              </div>
              {Object.keys(tags).length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(tags).map(([key, value]) => (
                    <div key={key} className="px-2 py-1 rounded-md bg-[#161b22] border border-[#26262b] text-[11px] flex gap-2 max-w-full shadow-sm items-center">
                      <span className="text-zinc-500 font-bold truncate shrink-0 max-w-[150px]">{key}</span>
                      <span className="text-zinc-200 font-semibold truncate max-w-[200px]" title={value}>{value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState icon={TagIcon} message="No tags found" height="h-[80px]" />
              )}
            </div>
          </div>
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
