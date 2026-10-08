import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { getControlSummary } from '../../api/control';
import { listConfigs } from '../../api/config';
import { OverviewTab } from './tabs/OverviewTab';
import { ActivityLogTab } from './tabs/ActivityLogTab';
import { ResourcesTab } from './tabs/ResourcesTab';
import { ScrollToTopButton } from '../../components/ui/ScrollToTopButton';
import { NotificationBell } from '../../components/ui/NotificationBell';

export default function ControlPage() {
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('pulse_control_active_tab') || 'overview');
  const [summary, setSummary] = useState({ total_count: 0, running_count: 0, stopped_count: 0, terminated_count: 0, active_schedules_count: 0 });
  const [loadingSummary, setLoadingSummary] = useState(false);
  
  // We keep topFilters with hardcoded values for child components, only allowing provider to change.
  const [topFilters, setTopFilters] = useState({
    provider: localStorage.getItem('pulse_control_provider') || 'AWS',
    account: '',
    region: 'All Regions',
    tag: 'All Tags',
    range: 30
  });

  const [verifiedConfigs, setVerifiedConfigs] = useState([]);
  const availableProviders = ['AWS', 'AZURE', 'GCP'];

  useEffect(() => {
    if (topFilters.provider) localStorage.setItem('pulse_control_provider', topFilters.provider);
  }, [topFilters.provider]);

  useEffect(() => {
    loadConfigs();
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.provider]);

  useEffect(() => {
    const handleGlobalRefresh = () => {
      loadSummary();
    };

    const handleProviderChange = () => {
      setTopFilters(prev => ({
        ...prev,
        provider: localStorage.getItem('pulse_control_provider') || 'AWS'
      }));
    };

    window.addEventListener('app:refresh-data', handleGlobalRefresh);
    window.addEventListener('app:provider-change', handleProviderChange);

    return () => {
      window.removeEventListener('app:refresh-data', handleGlobalRefresh);
      window.removeEventListener('app:provider-change', handleProviderChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topFilters.provider]);

  const loadLogs = async () => { };

  const loadConfigs = async () => {
    try {
      const res = await listConfigs();
      const configs = res.data.configs || [];
      const vConfigs = configs.filter(c => c.verified);
      setVerifiedConfigs(vConfigs);

      if (vConfigs.length > 0) {
        let currentProvider = topFilters.provider;
        const providerConfigs = vConfigs.filter(c => (c.provider || '').toUpperCase() === currentProvider);
      }
    } catch (err) {
      console.error("Failed to load configs", err);
    }
  };

  
  const loadSummary = async () => {
    setLoadingSummary(true);
    try {
      const summaryData = await getControlSummary(topFilters);
      if (summaryData) {
        setSummary(summaryData);
      }
    } catch (err) {
      toast.error('Failed to load summary from backend');
    } finally {
      setLoadingSummary(false);
    }
  };

  return (
    <>
      <div className="sticky -top-6 h-6 -mx-6 -mt-6 bg-[#0a0a0f]/80 backdrop-blur-md z-30 pointer-events-none" />
      <div className="space-y-6 relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-4">
            {topFilters.provider && (
              <img src={`/${topFilters.provider.toLowerCase()}-logo.svg`} alt="" className="h-10 w-10 object-contain shrink-0" />
            )}
            <div>
              <h1 className="text-xl font-semibold flex items-center gap-3 text-[#e4e4e7] tracking-tight">
                {topFilters.provider || 'Cloud'} - Control Insights
              </h1>
              <p className="text-[11px] text-[#a1a1aa] mt-1">Manage real-time execution & power scheduling for visible resources</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <NotificationBell />
          </div>
        </div>



        {/* Tabs and Content Group */}
        {['AZURE', 'GCP'].includes(topFilters.provider) ? (
          <div className="flex flex-col items-center justify-center pt-28 pb-16 animate-in fade-in duration-500">
            <div className="w-20 h-20 mb-6 rounded-3xl bg-[#15181e] flex items-center justify-center border border-zinc-800/80 shadow-2xl">
              <img src={`/${topFilters.provider.toLowerCase()}-logo.svg`} alt={topFilters.provider} className="h-10 w-10 object-contain opacity-60 grayscale-[50%]" />
            </div>
            <h2 className="text-2xl font-bold text-[#e4e4e7] tracking-tight mb-3">Control for {topFilters.provider === 'AZURE' ? 'Azure' : 'Google Cloud'} is Coming Soon</h2>
            <p className="text-[13px] text-[#8b949e] max-w-md text-center leading-relaxed">
              We are actively building deep, real-time resource execution and power scheduling controls for {topFilters.provider === 'AZURE' ? 'Microsoft Azure' : 'Google Cloud'}. Stay tuned for updates!
            </p>
          </div>
        ) : (
          <div>
            {/* Main Global Tab Bar */}
            <div className="border-b border-zinc-800 flex gap-6">
              {['overview', 'activity', 'resources'].map(t => (
                <button
                  key={t}
                  onClick={() => {
                    setActiveTab(t);
                    localStorage.setItem('pulse_control_active_tab', t);
                  }}
                  className={`pb-3 text-sm font-medium border-b-2 capitalize transition-colors ${activeTab === t ? 'border-white text-white' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div className="pt-4">
              {activeTab === 'overview' && (
                <OverviewTab
                  totalCount={summary.total_count}
                  runningCount={summary.running_count}
                  stoppedCount={summary.stopped_count}
                  terminatedCount={summary.terminated_count}
                  activeSchedulesCount={summary.active_schedules_count}
                  typeBreakdown={summary.type_breakdown}
                  regionBreakdown={summary.region_breakdown}
                  topFilters={topFilters}
                />
              )}
              {activeTab === 'activity' && <ActivityLogTab topFilters={topFilters} />}
              {activeTab === 'resources' && (
                <ResourcesTab
                  topFilters={topFilters}
                  onActionLogged={loadLogs}
                />
              )}
            </div>
          </div>
        )}

        {activeTab !== 'overview' && <ScrollToTopButton />}
      </div>
    </>
  );
}
