import React, { useState, useEffect } from 'react';
import { useOutletContext, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import TicketDetailsPanel from '../components/common/TicketDetailsPanel';
import CategoryFilter from '../components/tickets/CategoryFilter';
import ScriptFilter from '../components/tickets/ScriptFilter';
import { getScriptCategory, SCRIPT_CATEGORIES } from '../utils/ticketUtils';

export default function ApprovalDashboard({ token }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { activeAccount } = useOutletContext() || {};
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [selectedTickets, setSelectedTickets] = useState(new Set());
  const [engineers, setEngineers] = useState([]);
  const [selectedEngineer, setSelectedEngineer] = useState('');
  const [approvalComments, setApprovalComments] = useState('');
  const [reasonForRejection, setReasonForRejection] = useState('');

  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [isCategoryDropdownOpen, setIsCategoryDropdownOpen] = useState(false);
  const [isScriptDropdownOpen, setIsScriptDropdownOpen] = useState(false);
  const [selectedScriptFilter, setSelectedScriptFilter] = useState("All Scripts");
  const [statusTab, setStatusTab] = useState("Pending");

  const [leftPanelWidth, setLeftPanelWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      const newWidth = (e.clientX / window.innerWidth) * 100;
      if (newWidth > 25 && newWidth < 75) {
        setLeftPanelWidth(newWidth);
      }
    };
    const handleMouseUp = () => setIsResizing(false);
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  useEffect(() => {
    if (!activeAccount) return;
    fetchTickets();
    fetchEngineers();
  }, [activeAccount, token]);

  useEffect(() => {
    if (location.state?.selectedScript) {
      setSelectedScriptFilter(location.state.selectedScript);
      const cat = getScriptCategory(location.state.selectedScript);
      if (cat) setSelectedCategory(cat);
      if (location.state.selectedStatus) {
        setStatusTab(location.state.selectedStatus);
      }
    } else if (location.state?.selectedCategory) {
      setSelectedCategory(location.state.selectedCategory);
      setSelectedScriptFilter("All Scripts");
    }
  }, [location.state]);

  const fetchEngineers = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/users/engineers', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setEngineers(res.data);
    } catch (err) {
      console.error('Failed to load engineers', err);
    }
  };

  const fetchTickets = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (activeAccount?.id) {
        params.account_id = activeAccount.id;
      }
      const res = await axios.get('http://localhost:8000/api/tickets', {
        headers: { Authorization: `Bearer ${token}` },
        params
      });
      setTickets(res.data);
    } catch (err) {
      console.error(err);
      setError('Failed to load tickets.');
    } finally {
      setLoading(false);
    }
  };

  const updateTicketStatus = async (ticketId, newStatus) => {
    try {
      let payload = { status: newStatus };
      if (newStatus === 'Approved') payload.approvalComments = approvalComments;
      if (newStatus === 'Rejected') payload.reasonForRejection = reasonForRejection;

      await axios.put(`http://localhost:8000/api/tickets/${ticketId}/status`, 
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      // Refresh list
      fetchTickets();
      if (selectedTicket && selectedTicket.id === ticketId) {
        let updatedDetails = selectedTicket.details;
        try {
           let parsed = JSON.parse(selectedTicket.details);
           if (newStatus === 'Approved') parsed.approvalComments = approvalComments;
           if (newStatus === 'Rejected') parsed.reasonForRejection = reasonForRejection;
           updatedDetails = JSON.stringify(parsed);
        } catch(e) {}
        setSelectedTicket({ ...selectedTicket, status: newStatus, details: updatedDetails });
      }
      setApprovalComments('');
      setReasonForRejection('');
    } catch (err) {
      console.error(err);
      alert('Failed to update ticket status. Ensure you have proper permissions.');
    }
  };

  const handleBulkAction = async (newStatus) => {
    try {
      const promises = Array.from(selectedTickets).map(ticketId => 
        axios.put(`http://localhost:8000/api/tickets/${ticketId}/status`, 
          { status: newStatus },
          { headers: { Authorization: `Bearer ${token}` } }
        )
      );
      await Promise.all(promises);
      setSelectedTickets(new Set());
      fetchTickets();
    } catch (err) {
      console.error(err);
      alert('Failed to update some tickets in bulk.');
    }
  };

  const assignTicket = async (ticketId, engineerId) => {
    if (!engineerId) return;
    try {
      const res = await axios.put(`http://localhost:8000/api/tickets/${ticketId}/assign`, 
        { engineer_id: parseInt(engineerId) },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      fetchTickets();
      if (selectedTicket && selectedTicket.id === ticketId) {
        setSelectedTicket(res.data);
      }
      setSelectedEngineer('');
    } catch (err) {
      console.error(err);
      alert('Failed to assign ticket.');
    }
  };

  const updateTicketDetailsData = async (ticketId, newDetailsObj) => {
    try {
      const detailsStr = JSON.stringify(newDetailsObj);
      const res = await axios.put(`http://localhost:8000/api/tickets/${ticketId}/details`, 
        { details: detailsStr },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      setTickets(prevTickets => prevTickets.map(t => t.id === ticketId ? res.data : t));
      if (selectedTicket && selectedTicket.id === ticketId) {
        setSelectedTicket(res.data);
      }
    } catch (err) {
      console.error(err);
      alert('Failed to save ticket details.');
    }
  };

  // Derive unique scripts and filter tickets
  const uniqueScripts = Array.from(new Set(tickets.map(t => t.script_name.replace('.py', '')))).sort();
  
  const filteredTickets = tickets.filter(t => {
    const scriptName = t.script_name.replace('.py', '');
    const categoryMatch = selectedCategory === "All Categories" || getScriptCategory(scriptName) === selectedCategory;
    const scriptMatch = selectedScriptFilter === "All Scripts" || scriptName === selectedScriptFilter;
    return categoryMatch && scriptMatch;
  });

  // Group tickets by status
  const displayedTickets = filteredTickets.filter(t => t.status === statusTab);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      
      {/* Unified Control Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
        
        {/* Status Tabs (Left) */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {['Pending', 'Approved', 'Rejected', 'In Progress', 'Completed'].map(status => {
            const count = filteredTickets.filter(t => t.status === status).length;
            return (
              <button
                key={status}
                onClick={() => {
                  setStatusTab(status);
                  setSelectedTickets(new Set());
                }}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '8px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: statusTab === status ? 'rgba(56, 189, 248, 0.4)' : 'transparent',
                  background: statusTab === status ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                  color: statusTab === status ? '#38bdf8' : 'var(--text-muted)',
                  transition: 'all 0.2s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem'
                }}
              >
                {status}
                <span style={{ 
                  background: statusTab === status ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255,255,255,0.05)', 
                  padding: '0.1rem 0.4rem', 
                  borderRadius: '12px', 
                  fontSize: '0.65rem' 
                }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Filters (Right) */}
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          
          <div style={{ minWidth: '180px', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
              Category:
            </label>
            <div style={{ flex: 1 }}>
              <CategoryFilter 
                categories={SCRIPT_CATEGORIES}
                selectedCategory={selectedCategory}
                onSelectCategory={(cat) => {
                  setSelectedCategory(cat);
                  setSelectedScriptFilter("All Scripts");
                }}
                isOpen={isCategoryDropdownOpen}
                setIsOpen={setIsCategoryDropdownOpen}
              />
            </div>
          </div>

          <div style={{ minWidth: '180px', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
              Script:
            </label>
            <div style={{ flex: 1 }}>
              <ScriptFilter 
                scripts={uniqueScripts.filter(s => selectedCategory === "All Categories" || getScriptCategory(s) === selectedCategory)}
                selectedScript={selectedScriptFilter}
                onSelectScript={(val) => {
                  setSelectedScriptFilter(val);
                  setIsScriptDropdownOpen(false);
                }}
                isOpen={isScriptDropdownOpen}
                setIsOpen={setIsScriptDropdownOpen}
                formatLabel={(s) => s.replace('.py', '')}
              />
            </div>
          </div>

          <button 
            onClick={() => navigate('/results')}
            style={{ 
              background: 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.4)', 
              color: '#38bdf8', padding: '0.6rem 1rem', borderRadius: '8px', 
              fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem',
              fontSize: '0.8rem', transition: 'all 0.2s', marginLeft: '0.5rem'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(56, 189, 248, 0.2)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(56, 189, 248, 0.1)'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            View Raw Results
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', userSelect: isResizing ? 'none' : 'auto' }}>
        {/* Left Side: Ticket List */}
        <div style={{ width: `calc(${leftPanelWidth}% - 8px)`, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          <div className="card" style={{ padding: '1rem' }}>
            {loading ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading tickets...</div>
            ) : displayedTickets.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No {statusTab.toLowerCase()} tickets found.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '600px', overflowY: 'auto', paddingRight: '0.5rem' }}>
                {displayedTickets.map(ticket => (
                  <div 
                    key={ticket.id} 
                    onClick={() => setSelectedTicket(ticket)}
                    style={{ 
                      padding: '0.75rem', 
                      borderRadius: '8px', 
                      background: selectedTicket?.id === ticket.id ? 'rgba(56, 189, 248, 0.1)' : 'rgba(255, 255, 255, 0.03)', 
                      border: `1px solid ${selectedTicket?.id === ticket.id ? 'rgba(56, 189, 248, 0.3)' : 'rgba(255, 255, 255, 0.05)'}`,
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <div 
                        onClick={(e) => {
                          e.stopPropagation();
                          const newSet = new Set(selectedTickets);
                          if (newSet.has(ticket.id)) newSet.delete(ticket.id);
                          else newSet.add(ticket.id);
                          setSelectedTickets(newSet);
                        }}
                        style={{
                          width: '18px', height: '18px', borderRadius: '4px',
                          border: `1px solid ${selectedTickets.has(ticket.id) ? '#38bdf8' : 'rgba(255,255,255,0.2)'}`,
                          background: selectedTickets.has(ticket.id) ? '#38bdf8' : 'transparent',
                          display: 'flex', justifyContent: 'center', alignItems: 'center',
                          cursor: 'pointer', flexShrink: 0
                        }}
                      >
                        {selectedTickets.has(ticket.id) && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>}
                      </div>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.9rem', color: selectedTicket?.id === ticket.id ? '#f8fafc' : 'var(--text-main)' }}>#{ticket.id} - {ticket.script_name.replace('.py', '')}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ticket.resource_id}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      {statusTab === 'Pending' ? (
                        <>
                          <button 
                            onClick={(e) => { e.stopPropagation(); updateTicketStatus(ticket.id, 'Approved'); }}
                            style={{ background: '#10b981', color: '#fff', border: 'none', borderRadius: '4px', padding: '0.25rem 0.5rem', cursor: 'pointer', fontSize: '0.75rem' }}
                          >
                            Approve
                          </button>
                          <button 
                            onClick={(e) => { e.stopPropagation(); updateTicketStatus(ticket.id, 'Rejected'); }}
                            style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', padding: '0.25rem 0.5rem', cursor: 'pointer', fontSize: '0.75rem' }}
                          >
                            Reject
                          </button>
                        </>
                      ) : (
                        <span style={{ 
                          fontSize: '0.7rem', padding: '0.25rem 0.5rem', borderRadius: '4px',
                          background: ticket.status === 'Approved' ? 'rgba(16, 185, 129, 0.1)' : ticket.status === 'Rejected' ? 'rgba(239, 68, 68, 0.1)' : ticket.status === 'Completed' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                          color: ticket.status === 'Approved' ? '#10b981' : ticket.status === 'Rejected' ? '#ef4444' : ticket.status === 'Completed' ? '#3b82f6' : '#f59e0b',
                          fontWeight: 600
                        }}>
                          {ticket.status}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Resizer Handle */}
        <div
          onMouseDown={() => setIsResizing(true)}
          style={{
            width: '16px',
            cursor: 'col-resize',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            alignSelf: 'stretch',
            zIndex: 10
          }}
        >
          <div style={{ 
            width: '4px', 
            height: '50px', 
            background: isResizing ? '#38bdf8' : 'rgba(255,255,255,0.1)', 
            borderRadius: '4px',
            transition: 'background 0.2s'
          }} />
        </div>

        {/* Right Side: Ticket Details Panel */}
        <div style={{ width: `calc(${100 - leftPanelWidth}% - 8px)`, flexShrink: 0 }}>
          <TicketDetailsPanel 
            ticket={selectedTicket}
            onSaveDetails={(newDetailsObj) => updateTicketDetailsData(selectedTicket.id, newDetailsObj)}
            actionComponent={
              selectedTicket?.status === 'Pending' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <textarea 
                    placeholder="Optional: Approval or Rejection comments..."
                    value={approvalComments || reasonForRejection}
                    onChange={(e) => {
                      setApprovalComments(e.target.value);
                      setReasonForRejection(e.target.value);
                    }}
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '0.85rem', resize: 'vertical', minHeight: '60px' }}
                  />
                  <div style={{ display: 'flex', gap: '1rem' }}>
                    <button onClick={() => updateTicketStatus(selectedTicket.id, 'Approved')} className="btn btn-primary" style={{ flex: 1, background: '#10b981', border: 'none', color: '#fff' }}>Approve</button>
                    <button onClick={() => updateTicketStatus(selectedTicket.id, 'Rejected')} className="btn" style={{ flex: 1, background: 'rgba(239, 68, 68, 0.2)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.5)' }}>Reject</button>
                  </div>
                </div>
              ) : selectedTicket?.status === 'Approved' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div>
                    <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', color: '#f8fafc' }}>Assign to Engineer</h4>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <select 
                        className="form-input" 
                        value={selectedEngineer}
                        onChange={(e) => setSelectedEngineer(e.target.value)}
                        style={{ flex: 1, padding: '0.5rem', background: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', borderRadius: '6px' }}
                      >
                        <option value="">Select Engineer...</option>
                        {engineers.map(eng => (
                          <option key={eng.id} value={eng.id}>{eng.username}</option>
                        ))}
                      </select>
                      <button 
                        className="btn btn-primary"
                        disabled={!selectedEngineer}
                        onClick={() => assignTicket(selectedTicket.id, selectedEngineer)}
                        style={{ padding: '0.5rem 1rem', background: '#38bdf8', color: '#0f172a', fontWeight: '700', border: 'none', borderRadius: '6px' }}
                      >
                        Assign
                      </button>
                    </div>
                  </div>

                  <div style={{ borderTop: '1px dashed rgba(255,255,255,0.15)', paddingTop: '1rem' }}>
                    <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Change Decision</h4>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input 
                        type="text"
                        placeholder="Reason for rejection (optional)..."
                        value={reasonForRejection}
                        onChange={(e) => setReasonForRejection(e.target.value)}
                        style={{ flex: 1, padding: '0.5rem 0.75rem', background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '6px', color: '#f8fafc', fontSize: '0.85rem', outline: 'none' }}
                      />
                      <button 
                        onClick={() => updateTicketStatus(selectedTicket.id, 'Rejected')} 
                        style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.4)', padding: '0.5rem 1rem', borderRadius: '6px', fontSize: '0.85rem', cursor: 'pointer', fontWeight: '600', transition: 'all 0.2s' }}
                        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.25)'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.15)'}
                      >
                        Reject Ticket
                      </button>
                    </div>
                  </div>
                </div>
              ) : selectedTicket?.status === 'Rejected' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div>
                    <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Change Decision</h4>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input 
                        type="text"
                        placeholder="Approval comments (optional)..."
                        value={approvalComments}
                        onChange={(e) => setApprovalComments(e.target.value)}
                        style={{ flex: 1, padding: '0.5rem 0.75rem', background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '6px', color: '#f8fafc', fontSize: '0.85rem', outline: 'none' }}
                      />
                      <button 
                        onClick={() => updateTicketStatus(selectedTicket.id, 'Approved')} 
                        style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.4)', padding: '0.5rem 1rem', borderRadius: '6px', fontSize: '0.85rem', cursor: 'pointer', fontWeight: '600', transition: 'all 0.2s' }}
                        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(16, 185, 129, 0.25)'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(16, 185, 129, 0.15)'}
                      >
                        Approve Ticket
                      </button>
                    </div>
                  </div>
                </div>
              ) : null
            }
          />
        </div>

      </div>

      {/* Floating Bulk Action Bar */}
      {selectedTickets.size > 0 && (
        <div style={{
          position: 'fixed', bottom: '2rem', left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(15, 23, 42, 0.95)', backdropFilter: 'blur(10px)',
          border: '1px solid rgba(56, 189, 248, 0.4)', borderRadius: '50px',
          padding: '0.75rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1.5rem',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)', zIndex: 1000
        }}>
          <span style={{ color: '#f8fafc', fontWeight: 600, fontSize: '0.9rem' }}>
            {selectedTickets.size} Ticket{selectedTickets.size !== 1 ? 's' : ''} Selected
          </span>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button 
              onClick={() => handleBulkAction('Approved')}
              style={{ background: '#10b981', color: '#fff', border: 'none', borderRadius: '20px', padding: '0.4rem 1rem', fontWeight: 600, fontSize: '0.8rem', cursor: 'pointer' }}
            >
              Approve All
            </button>
            <button 
              onClick={() => handleBulkAction('Rejected')}
              style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: '20px', padding: '0.4rem 1rem', fontWeight: 600, fontSize: '0.8rem', cursor: 'pointer' }}
            >
              Reject All
            </button>
            <button 
              onClick={() => setSelectedTickets(new Set())}
              style={{ background: 'transparent', color: '#94a3b8', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '20px', padding: '0.4rem 1rem', fontWeight: 600, fontSize: '0.8rem', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

    </div>
  );
}
