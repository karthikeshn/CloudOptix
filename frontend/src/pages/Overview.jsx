import React, { useState, useEffect } from 'react';
import axios from 'axios';
import DynamicTable from '../components/common/DynamicTable';
import { useOutletContext, useNavigate } from 'react-router-dom';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Legend, BarChart, Bar, LabelList } from 'recharts';

const mockSavingsData = [
  { name: 'Compute & Management', value: 4500, color: '#8b5cf6' },
  { name: 'Storage & Volumes', value: 2100, color: '#3b82f6' },
  { name: 'Networking & IP', value: 1200, color: '#06b6d4' },
  { name: 'Databases & Cache', value: 800, color: '#10b981' }
];

const mockTrendData = [
  { month: 'Apr', spend: 12400 },
  { month: 'May', spend: 13200 },
  { month: 'Jun', spend: 12800 },
  { month: 'Jul', spend: 14500 },
  { month: 'Aug', spend: 13900 },
  { month: 'Sep', spend: 11200 }
];

const mockTopOptimizations = [
  { name: 'AMI Snapshots', value: 4500, color: '#8b5cf6' },
  { name: 'Idle ELB', value: 2100, color: '#3b82f6' },
  { name: 'Unattached EBS', value: 1800, color: '#06b6d4' },
  { name: 'Idle RDS', value: 1200, color: '#10b981' },
  { name: 'Old Snapshots', value: 900, color: '#f59e0b' }
];

const mockHealthData = [
  { name: 'Optimized', value: 85, color: '#10b981' },
  { name: 'Wasted', value: 15, color: '#64748b' }
];

export default function Overview({ token }) {
  const { activeAccount } = useOutletContext() || {};
  const [configsCount, setConfigsCount] = useState(0);
  const [scriptsCount, setScriptsCount] = useState(0);
  const [pendingTicketsCount, setPendingTicketsCount] = useState(0);
  const [pendingFindingsByScript, setPendingFindingsByScript] = useState({});
  const [isFindingsModalOpen, setIsFindingsModalOpen] = useState(false);
  const [savingsByService, setSavingsByService] = useState({});
  const [achievedByService, setAchievedByService] = useState({});
  const [isSavingsModalOpen, setIsSavingsModalOpen] = useState(false);
  const [activeSavingsTab, setActiveSavingsTab] = useState('potential');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const [latestData, setLatestData] = useState(null);
  const [latestScriptName, setLatestScriptName] = useState(null);
  const [latestTimestamp, setLatestTimestamp] = useState(null);
  const [latestFilename, setLatestFilename] = useState(null);

  const [spend, setSpend] = useState("$0");
  const [savings, setSavings] = useState("$0");
  const [savingsData, setSavingsData] = useState([]);
  const [topOptimizations, setTopOptimizations] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      if (!token) return;
      try {
        setLoading(true);
        // Fetch Active Cloud Configs
        const configsRes = await axios.get('http://127.0.0.1:8000/api/cloud-config', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setConfigsCount(configsRes.data.length);

        // Fetch Available Scripts
        const scriptsRes = await axios.get('http://127.0.0.1:8000/api/scripts', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setScriptsCount(scriptsRes.data.scripts?.length || 0);

        if (activeAccount && activeAccount.id) {
          // Fetch Pending Tickets
          try {
            const ticketsRes = await axios.get(`http://127.0.0.1:8000/api/tickets?account_id=${activeAccount.id}`, {
              headers: { Authorization: `Bearer ${token}` }
            });
            const pendingTickets = ticketsRes.data.filter(t => t.status === 'Pending');
            setPendingTicketsCount(pendingTickets.length);
            
            const grouped = {};
            pendingTickets.forEach(t => {
              const scriptName = t.script_name.replace('.py', '');
              grouped[scriptName] = (grouped[scriptName] || 0) + 1;
            });
            setPendingFindingsByScript(grouped);
          } catch (e) {
            console.error("Error fetching tickets for KPI", e);
          }

          // Fetch Stats
          const statsRes = await axios.get(`http://127.0.0.1:8000/api/dashboard/stats/${activeAccount.id}`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          setSpend(statsRes.data.spend);
          setSavings(statsRes.data.savings);
          
          // Map backend top optimizations to colors
          const colors = ['#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b'];
          if (statsRes.data.topOptimizations) {
             const tops = statsRes.data.topOptimizations.map((item, idx) => ({
                 name: item.name,
                 value: item.value,
                 color: colors[idx % colors.length]
             }));
             setTopOptimizations(tops);
          }

          // Map script savings to category slices
          if (statsRes.data.scriptSavings) {
             const catTotals = {
                'Compute & Management': 0,
                'Storage & Volumes': 0,
                'Networking & IP': 0,
                'Databases & Cache': 0,
                'Other': 0
             };
             
             for (const [scriptName, val] of Object.entries(statsRes.data.scriptSavings)) {
                let cat = 'Other';
                const lower = scriptName.toLowerCase();
                if (lower.includes('ec2') || lower.includes('lambda') || lower.includes('ami')) cat = 'Compute & Management';
                else if (lower.includes('ebs') || lower.includes('s3') || lower.includes('snapshot')) cat = 'Storage & Volumes';
                else if (lower.includes('vpc') || lower.includes('eip') || lower.includes('elb') || lower.includes('load_balancer')) cat = 'Networking & IP';
                else if (lower.includes('rds') || lower.includes('dynamo')) cat = 'Databases & Cache';
                
                if (catTotals[cat] !== undefined) {
                    catTotals[cat] += val;
                } else {
                    catTotals[cat] = val;
                }
             }

             const serviceMap = {
                'EC2': {}, 'EBS': {}, 'S3': {}, 'Lambda': {}, 'RDS': {}, 'VPC & Networking': {}, 'Other': {}
             };
             for (const [scriptName, val] of Object.entries(statsRes.data.scriptSavings)) {
                const lower = scriptName.toLowerCase();
                let svc = 'Other';
                if (lower.includes('ec2') || lower.includes('ami')) svc = 'EC2';
                else if (lower.includes('ebs') || lower.includes('snapshot')) svc = 'EBS';
                else if (lower.includes('s3')) svc = 'S3';
                else if (lower.includes('lambda')) svc = 'Lambda';
                else if (lower.includes('rds') || lower.includes('dynamo')) svc = 'RDS';
                else if (lower.includes('vpc') || lower.includes('eip') || lower.includes('elb') || lower.includes('load_balancer')) svc = 'VPC & Networking';
                serviceMap[svc][scriptName] = val;
             }
             
             Object.keys(serviceMap).forEach(key => {
                if (Object.keys(serviceMap[key]).length === 0) delete serviceMap[key];
             });
             setSavingsByService(serviceMap);
             
             if (statsRes.data.achievedScriptSavings) {
                const achievedMap = {
                   'EC2': {}, 'EBS': {}, 'S3': {}, 'Lambda': {}, 'RDS': {}, 'VPC & Networking': {}, 'Other': {}
                };
                for (const [scriptName, val] of Object.entries(statsRes.data.achievedScriptSavings)) {
                   const lower = scriptName.toLowerCase();
                   let svc = 'Other';
                   if (lower.includes('ec2') || lower.includes('ami')) svc = 'EC2';
                   else if (lower.includes('ebs') || lower.includes('snapshot')) svc = 'EBS';
                   else if (lower.includes('s3')) svc = 'S3';
                   else if (lower.includes('lambda')) svc = 'Lambda';
                   else if (lower.includes('rds') || lower.includes('dynamo')) svc = 'RDS';
                   else if (lower.includes('vpc') || lower.includes('eip') || lower.includes('elb') || lower.includes('load_balancer')) svc = 'VPC & Networking';
                   achievedMap[svc][scriptName] = val;
                }
                
                Object.keys(achievedMap).forEach(key => {
                   if (Object.keys(achievedMap[key]).length === 0) delete achievedMap[key];
                });
                setAchievedByService(achievedMap);
             }
             
             const mappedData = [
                { name: 'Compute & Management', value: catTotals['Compute & Management'], color: '#8b5cf6' },
                { name: 'Storage & Volumes', value: catTotals['Storage & Volumes'], color: '#3b82f6' },
                { name: 'Networking & IP', value: catTotals['Networking & IP'], color: '#06b6d4' },
                { name: 'Databases & Cache', value: catTotals['Databases & Cache'], color: '#10b981' }
             ].filter(item => item.value > 0);
             
             setSavingsData(mappedData.length > 0 ? mappedData : [{ name: 'No Savings Found', value: 1, color: '#27272a' }]);
          }

          // Fetch Latest Run Data
          const latestRes = await axios.get(`http://127.0.0.1:8000/api/scripts/latest-run?aws_account_id=${activeAccount.id}`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          if (latestRes.data.data) {
            setLatestData(latestRes.data.data);
            setLatestScriptName(latestRes.data.scriptName);
            setLatestTimestamp(latestRes.data.timestamp);
            setLatestFilename(latestRes.data.filename);
          } else {
            setLatestData(null);
            setLatestScriptName(null);
            setLatestTimestamp(null);
            setLatestFilename(null);
          }
        } else {
          setSpend("$0");
          setSavings("$0");
          setPendingTicketsCount(0);
          setPendingFindingsByScript({});
          setSavingsByService({});
          setAchievedByService({});
          setLatestData(null);
          setLatestScriptName(null);
          setLatestTimestamp(null);
          setLatestFilename(null);
        }
      } catch (error) {
        console.error("Error fetching overview data:", error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [token, activeAccount]);

  const downloadFile = async (filename) => {
    if (!filename) return;
    try {
      const response = await axios.get(`http://127.0.0.1:8000/api/scripts/download/${filename}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Error downloading file:", error);
    }
  };

  return (
    <div className="overview-container">
      <div className="page-header" style={{ marginBottom: '1.25rem' }}>
        <div className="page-title">
          <h2 style={{ fontSize: '1.45rem', margin: '0 0 0.25rem 0', fontWeight: '700' }}>Dashboard</h2>
          <p className="subtitle" style={{ color: 'var(--text-muted)', margin: 0, fontSize: '0.82rem' }}>AI-driven right-sizing recommendations overview</p>
        </div>
      </div>

      <svg width="0" height="0" style={{ position: 'absolute' }}>
        <defs>
          <linearGradient id="gradPink" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ff007a" />
            <stop offset="100%" stopColor="#7928ca" />
          </linearGradient>
          <linearGradient id="gradCyan" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f0ff" />
            <stop offset="100%" stopColor="#003fff" />
          </linearGradient>
          <linearGradient id="gradGold" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffea00" />
            <stop offset="100%" stopColor="#ff7a00" />
          </linearGradient>
          <linearGradient id="gradGreen" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00ff88" />
            <stop offset="100%" stopColor="#0080ff" />
          </linearGradient>
          <linearGradient id="gradOrange" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ff5c00" />
            <stop offset="100%" stopColor="#ff0040" />
          </linearGradient>
        </defs>
      </svg>

      <div className="kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
        {/* KPI 1: Potential Savings */}
        <div 
          className="kpi-card" 
          onClick={() => setIsSavingsModalOpen(true)}
          style={{ background: '#121212', borderRadius: '10px', padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', border: '1px solid #27272a', cursor: 'pointer', transition: 'border-color 0.2s' }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = '#22c55e'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = '#27272a'}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.68rem', color: '#94a3b8', fontWeight: '600', letterSpacing: '0.05em' }}>POTENTIAL SAVINGS</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', color: '#22c55e', lineHeight: '1' }}>
            {savings}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Click for breakdown</div>
        </div>

        {/* KPI 2: Total Cloud Spend */}
        <div className="kpi-card" style={{ background: '#121212', borderRadius: '10px', padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', border: '1px solid #27272a' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.68rem', color: '#94a3b8', fontWeight: '600', letterSpacing: '0.05em' }}>CURRENT SPEND</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f8fafc" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="M7 15h0M2 9.5h20"></path></svg>
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', color: '#f8fafc', lineHeight: '1' }}>
            {spend}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Month-to-date expenses</div>
        </div>

        {/* KPI 3: Active Cloud Configs */}
        <div className="kpi-card" style={{ background: '#121212', borderRadius: '10px', padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', border: '1px solid #27272a' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.68rem', color: '#94a3b8', fontWeight: '600', letterSpacing: '0.05em' }}>ACCOUNT ID</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#eab308" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path><line x1="16" y1="8" x2="2" y2="22"></line><line x1="17.5" y1="15" x2="9" y2="15"></line></svg>
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', color: '#eab308', lineHeight: '1' }}>
            {activeAccount ? (activeAccount.aws_account_id || activeAccount.id) : "-"}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Currently selected account</div>
        </div>

        <div 
          className="kpi-card" 
          onClick={() => setIsFindingsModalOpen(true)}
          style={{ background: '#121212', borderRadius: '10px', padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', border: '1px solid #27272a', cursor: 'pointer', transition: 'border-color 0.2s' }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = '#ef4444'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = '#27272a'}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.68rem', color: '#94a3b8', fontWeight: '600', letterSpacing: '0.05em' }}>PENDING FINDINGS</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', color: '#ef4444', lineHeight: '1' }}>
            {loading ? "..." : pendingTicketsCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Awaiting your approval</div>
        </div>
      </div>

      {/* Charts Section */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginTop: '1.5rem' }}>
        
        {/* Savings Donut Chart */}
        <div style={{ background: '#121212', borderRadius: '12px', padding: '1rem', border: '1px solid #27272a' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '0.5rem', color: '#f8fafc' }}>Potential Savings</h3>
          <div style={{ width: '100%', height: 150 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie 
                  data={savingsData} 
                  innerRadius={35} 
                  outerRadius={55} 
                  cy="45%"
                  paddingAngle={2} 
                  dataKey="value" 
                  stroke="none"
                  onClick={(data) => navigate('/approvals', { state: { selectedCategory: data.name } })}
                  style={{ cursor: 'pointer' }}
                >
                  {savingsData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.color} />)}
                </Pie>
                <RechartsTooltip formatter={(value) => [`$${value.toFixed(2)}`, 'Savings']} contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', color: '#f8fafc' }} />
                <Legend verticalAlign="bottom" height={20} wrapperStyle={{ fontSize: '0.7rem', color: '#94a3b8' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Spend Trend Area Chart */}
        <div style={{ background: '#121212', borderRadius: '12px', padding: '1rem', border: '1px solid #27272a' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '0.5rem', color: '#f8fafc' }}>Monthly Spend Trend</h3>
          <div style={{ width: '100%', height: 150 }}>
            <ResponsiveContainer>
              <AreaChart data={mockTrendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorSpend" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="lineColor" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#3b82f6" />
                    <stop offset="100%" stopColor="#3b82f6" />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value/1000}k`} />
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <RechartsTooltip formatter={(value) => [`$${value}`, 'Spend']} contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', color: '#f8fafc' }} itemStyle={{ color: '#f8fafc' }} />
                <Area type="monotone" dataKey="spend" stroke="url(#lineColor)" strokeWidth={2} fillOpacity={1} fill="url(#colorSpend)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top 5 Optimizations Bar Chart */}
        <div style={{ background: '#121212', borderRadius: '12px', padding: '1rem', border: '1px solid #27272a' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '0.5rem', color: '#f8fafc' }}>Top Opportunities</h3>
          <div style={{ width: '100%', height: Math.max(80, topOptimizations.length * 35 + 20) }}>
            <ResponsiveContainer>
              <BarChart data={topOptimizations} layout="vertical" margin={{ top: 5, right: 50, left: 0, bottom: 5 }}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} width={115} />
                <Bar 
                  dataKey="value" 
                  radius={[0, 4, 4, 0]} 
                  barSize={12}
                  onClick={(data) => navigate('/approvals', { state: { selectedScript: data.name.replace('.py', '') } })}
                  style={{ cursor: 'pointer' }}
                >
                  {topOptimizations.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.color} />)}
                  <LabelList 
                    dataKey="value" 
                    position="right" 
                    fill="#fff" 
                    fontSize={10} 
                    formatter={(val) => typeof val === 'number' ? `$${val.toFixed(2)}` : val} 
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      {/* Savings Modal */}
      {isSavingsModalOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999
        }} onClick={() => setIsSavingsModalOpen(false)}>
          <div style={{
            background: '#121212', borderRadius: '12px', width: '450px', maxWidth: '90vw',
            border: '1px solid #27272a', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
            display: 'flex', flexDirection: 'column', maxHeight: '80vh', overflow: 'hidden'
          }} onClick={e => e.stopPropagation()}>
            <div style={{
              padding: '1.25rem', borderBottom: '1px solid #27272a',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>Savings by Service</h3>
              <button 
                onClick={() => setIsSavingsModalOpen(false)}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1.5rem', padding: '0.2rem', lineHeight: 1 }}
              >×</button>
            </div>
            
            {/* Tabs Header */}
            <div style={{ display: 'flex', borderBottom: '1px solid #27272a' }}>
              <div 
                onClick={() => setActiveSavingsTab('potential')}
                style={{ 
                  flex: 1, textAlign: 'center', padding: '0.75rem', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
                  color: activeSavingsTab === 'potential' ? '#22c55e' : '#94a3b8',
                  borderBottom: activeSavingsTab === 'potential' ? '2px solid #22c55e' : '2px solid transparent',
                  transition: 'all 0.2s'
                }}
              >
                Potential Savings
              </div>
              <div 
                onClick={() => setActiveSavingsTab('achieved')}
                style={{ 
                  flex: 1, textAlign: 'center', padding: '0.75rem', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
                  color: activeSavingsTab === 'achieved' ? '#3b82f6' : '#94a3b8',
                  borderBottom: activeSavingsTab === 'achieved' ? '2px solid #3b82f6' : '2px solid transparent',
                  transition: 'all 0.2s'
                }}
              >
                Estimated Savings Achieved
              </div>
            </div>
            
            <div style={{ padding: '0.5rem 1rem 1rem', overflowY: 'auto', flex: 1 }}>
              {Object.keys(activeSavingsTab === 'potential' ? savingsByService : achievedByService).length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
                  No savings data available.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '0.75rem' }}>
                  {Object.entries(activeSavingsTab === 'potential' ? savingsByService : achievedByService).map(([serviceName, scripts]) => (
                    <div key={serviceName}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.25rem' }}>
                        {serviceName}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        {Object.entries(scripts).map(([scriptName, savingsVal]) => (
                          <div 
                            key={scriptName}
                            onClick={() => navigate('/approvals', { 
                              state: { 
                                selectedScript: scriptName.replace('.py', ''),
                                selectedStatus: activeSavingsTab === 'achieved' ? 'Completed' : 'Pending'
                              } 
                            })}
                            style={{
                              padding: '0.65rem 0.85rem', borderRadius: '8px',
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              cursor: 'pointer', background: 'transparent', transition: 'background 0.2s'
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                          >
                            <div style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: '1rem' }}>
                              {scriptName.replace('.py', '')}
                            </div>
                            <div style={{
                              background: activeSavingsTab === 'potential' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(59, 130, 246, 0.15)', 
                              color: activeSavingsTab === 'potential' ? '#22c55e' : '#3b82f6', 
                              padding: '0.25rem 0.6rem', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 600
                            }}>
                              ${savingsVal.toFixed(2)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Findings Modal */}
      {isFindingsModalOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999
        }} onClick={() => setIsFindingsModalOpen(false)}>
          <div style={{
            background: '#121212', borderRadius: '12px', width: '400px', maxWidth: '90vw',
            border: '1px solid #27272a', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
            display: 'flex', flexDirection: 'column', maxHeight: '80vh', overflow: 'hidden'
          }} onClick={e => e.stopPropagation()}>
            <div style={{
              padding: '1.25rem', borderBottom: '1px solid #27272a',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>Pending Findings</h3>
              <button 
                onClick={() => setIsFindingsModalOpen(false)}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1.5rem', padding: '0.2rem', lineHeight: 1 }}
              >×</button>
            </div>
            
            <div style={{ padding: '0.5rem', overflowY: 'auto', flex: 1 }}>
              {Object.keys(pendingFindingsByScript).length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
                  No pending findings available.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  {Object.entries(pendingFindingsByScript).map(([scriptName, count]) => (
                    <div 
                      key={scriptName}
                      onClick={() => navigate('/approvals', { state: { selectedScript: scriptName } })}
                      style={{
                        padding: '0.85rem 1rem', borderRadius: '8px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        cursor: 'pointer', background: 'transparent', transition: 'background 0.2s'
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <div style={{ color: '#e2e8f0', fontSize: '0.9rem', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: '1rem' }}>
                        {scriptName}
                      </div>
                      <div style={{
                        background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', 
                        padding: '0.25rem 0.6rem', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 600
                      }}>
                        {count} Ticket{count !== 1 ? 's' : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
