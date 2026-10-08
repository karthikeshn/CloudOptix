import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Clock, Power, Server, Database } from 'lucide-react';
import { ScheduleCalendar } from './components/ScheduleCalendar';

export default function ActionModal({ isOpen, onClose, mode, resource, onConfirm }) {
  const [automationEnabled, setAutomationEnabled] = useState(true);
  const [disabledDates, setDisabledDates] = useState([]);
  const [startTime, setStartTime] = useState('10:00');
  const [stopTime, setStopTime] = useState('21:00');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleConfirm = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onConfirm({ mode, resource, automationEnabled, startTime, stopTime, timezone, disabledDates });
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    if (resource?.schedule) {
      setAutomationEnabled(resource.schedule.is_automation_enabled ?? true);
      setStartTime(resource.schedule.start_time || '10:00');
      setStopTime(resource.schedule.stop_time || '21:00');
      setTimezone(resource.schedule.timezone || 'Asia/Kolkata');
      
      let parsedDisabled = [];
      try {
        if (resource.schedule.disabled_dates) {
            parsedDisabled = typeof resource.schedule.disabled_dates === 'string' ? JSON.parse(resource.schedule.disabled_dates) : resource.schedule.disabled_dates;
        }
      } catch (e) {}
      setDisabledDates(parsedDisabled);
    }
  }, [resource]);

  if (!isOpen || !resource) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && resource && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm"
        >
          <motion.div 
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-[#131315] border border-[#26262b] rounded-xl w-full max-w-[420px] shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
          >
        <div className="px-4 py-3 border-b border-[#26262b] bg-[#131315] flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-[13px] font-bold text-zinc-100 flex items-center gap-2">
              {mode === 'schedule' ? <Clock className="h-3.5 w-3.5 text-blue-400"/> : <Power className={`h-3.5 w-3.5 ${mode === 'start' ? 'text-emerald-400' : 'text-amber-400'}`}/>}
              {mode === 'schedule' ? 'Configure Schedule' : mode === 'start' ? 'Start Resource' : 'Stop Resource'}
            </h2>
            <p className="text-[11px] text-zinc-500 mt-0.5 uppercase tracking-wider font-semibold">{resource.service_type || resource.resource_type} • {resource.region}</p>
          </div>
          <motion.button 
            whileHover={{ scale: 1.05, backgroundColor: '#26262b' }}
            whileTap={{ scale: 0.95 }}
            onClick={onClose} 
            className="p-1 text-zinc-500 rounded-md transition-colors"
          >
            <X className="h-4 w-4" />
          </motion.button>
        </div>

        <div className="p-4 overflow-y-auto bg-[#0a0a0f]">
          {mode === 'schedule' ? (
            <div className="space-y-4">
              <div>
                <h3 className="text-[11px] uppercase tracking-wider font-bold text-zinc-300 mb-3">Automation Settings</h3>
                <label className="flex items-center justify-between p-3 bg-[#161b22] border border-[#26262b] rounded-lg cursor-pointer transition-colors mb-3 hover:border-zinc-500">
                  <div>
                    <span className="text-[12px] font-semibold text-zinc-200 block">Enable Automated Schedule</span>
                    <span className="text-[11px] text-zinc-500">Allow CloudPulse to manage power state</span>
                  </div>
                  <input type="checkbox" checked={automationEnabled} onChange={e => setAutomationEnabled(e.target.checked)} className="rounded accent-white w-3.5 h-3.5"/>
                </label>

                {automationEnabled && (
                  <motion.div 
                    initial={{ opacity: 0, y: -10 }} 
                    animate={{ opacity: 1, y: 0 }} 
                    className="space-y-3"
                  >

                    <ScheduleCalendar disabledDates={disabledDates} setDisabledDates={setDisabledDates} />

                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-[#161b22] p-3 rounded-lg border border-[#26262b] shadow-sm">
                        <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1.5 block">Power ON Time</label>
                        <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} className="w-full text-[12px] font-mono bg-[#0a0a0f] border border-[#26262b] shadow-inner rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 transition-colors"/>
                      </div>
                      <div className="bg-[#161b22] p-3 rounded-lg border border-[#26262b] shadow-sm">
                        <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1.5 block">Power OFF Time</label>
                        <input type="time" value={stopTime} onChange={e => setStopTime(e.target.value)} className="w-full text-[12px] font-mono bg-[#0a0a0f] border border-[#26262b] shadow-inner rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 transition-colors"/>
                      </div>
                    </div>


                  </motion.div>
                )}
              </div>
            </div>
          ) : (

            <div className="space-y-4">
              <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm relative overflow-hidden">
                <div className={`absolute left-0 top-0 bottom-0 w-1 ${mode === 'start' ? 'bg-emerald-500/50' : 'bg-amber-500/50'}`} />
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1.5 block pl-2">Target Resource</label>
                <div className="font-mono text-[11px] text-zinc-300 break-all select-all pl-2 flex items-center gap-2">
                  {resource.service_type === 'ec2' ? <Server className="h-3.5 w-3.5 text-zinc-500"/> : <Database className="h-3.5 w-3.5 text-zinc-500"/>}
                  {resource.resource_id}
                </div>
              </div>
              <div className={`border rounded-xl p-3 shadow-sm relative overflow-hidden ${
                mode === 'start' ? 'bg-emerald-950/10 border-emerald-900/30' : 'bg-amber-950/10 border-amber-900/30'
              }`}>
                <div className="flex items-start gap-3">
                  <Power className={`h-4 w-4 mt-0.5 shrink-0 ${mode === 'start' ? 'text-emerald-500' : 'text-amber-500'}`} />
                  <div>
                    <h3 className={`text-[12px] font-bold ${mode === 'start' ? 'text-emerald-400' : 'text-amber-400'}`}>
                      Are you sure you want to {mode === 'start' ? 'START' : 'STOP'} this resource immediately?
                    </h3>
                    <p className="text-[11px] mt-0.5 font-medium text-zinc-400">
                      This action will override any currently active schedules.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="px-4 py-3 bg-[#131315] border-t border-[#26262b] flex justify-end gap-2.5 shrink-0">
          <motion.button 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onClose} 
            disabled={isSubmitting} 
            className="px-3.5 py-1.5 text-[11px] font-bold text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
          >
            Cancel
          </motion.button>
          <motion.button 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleConfirm} 
            disabled={isSubmitting} 
            className="px-3.5 py-1.5 text-[11px] font-bold bg-white text-black hover:bg-zinc-200 rounded transition-colors disabled:opacity-50 shadow-[0_0_15px_rgba(255,255,255,0.1)] flex items-center gap-1.5"
          >
            {isSubmitting ? 'Processing...' : mode === 'schedule' ? 'Save Schedule' : mode === 'start' ? 'Start Resource' : 'Stop Resource'}
          </motion.button>
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
