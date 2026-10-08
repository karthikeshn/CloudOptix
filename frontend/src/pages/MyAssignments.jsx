import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import axios from 'axios';
import TicketDetailsPanel from '../components/common/TicketDetailsPanel';

export default function MyAssignments({ token }) {
  const { activeAccount } = useOutletContext() || {};
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [engineerComment, setEngineerComment] = useState('');

  useEffect(() => {
    if (selectedTicket) {
      try {
        const detailsObj = JSON.parse(selectedTicket.details || '{}');
        setEngineerComment(detailsObj['Engineer Comments'] || '');
      } catch (e) {
        setEngineerComment('');
      }
    } else {
      setEngineerComment('');
    }
  }, [selectedTicket]);

  useEffect(() => {
    // Need current user ID to fetch assigned tickets
    axios.get('http://localhost:8000/api/users/me', {
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      setCurrentUser(res.data);
    }).catch(err => console.error(err));
  }, [token]);

  useEffect(() => {
    if (currentUser) {
      fetchTickets();
    }
  }, [activeAccount, token, currentUser]);

  const fetchTickets = async () => {
    setLoading(true);
    setError('');
    try {
      const params = { assigned_to: currentUser.id };
      if (activeAccount?.aws_account_id) {
        params.aws_account_id = activeAccount.aws_account_id;
      }
      const res = await axios.get('http://localhost:8000/api/tickets', {
        headers: { Authorization: `Bearer ${token}` },
        params
      });
      setTickets(res.data);
    } catch (err) {
      console.error(err);
      setError('Failed to load assignments.');
    } finally {
      setLoading(false);
    }
  };

  const updateTicketStatus = async (ticketId, newStatus) => {
    try {
      await axios.put(`http://localhost:8000/api/tickets/${ticketId}/status`, 
        { status: newStatus },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      // Refresh list
      fetchTickets();
      if (selectedTicket && selectedTicket.id === ticketId) {
        setSelectedTicket({ ...selectedTicket, status: newStatus });
      }
    } catch (err) {
      console.error(err);
      alert('Failed to complete ticket. Only managers can update status directly.');
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
      alert('Failed to save details.');
    }
  };

  const handleSaveComment = async () => {
    if (!selectedTicket) return;
    try {
      const detailsObj = JSON.parse(selectedTicket.details || '{}');
      detailsObj['Engineer Comments'] = engineerComment;
      await updateTicketDetailsData(selectedTicket.id, detailsObj);
      alert('Comment saved successfully!');
    } catch (e) {
      console.error(e);
      alert('Failed to parse or save comment.');
    }
  };

  // Group tickets by status
  const inProgressTickets = tickets.filter(t => t.status === 'In Progress');
  const otherTickets = tickets.filter(t => t.status !== 'In Progress');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: '800', margin: 0, background: 'linear-gradient(135deg, #fff 0%, #38bdf8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            My Assignments
          </h2>
          <p style={{ color: 'var(--text-muted)', margin: '0.15rem 0 0 0', fontSize: '0.8rem' }}>
            Action items assigned to you for manual remediation.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
        {/* Left Side: Ticket List */}
        <div style={{ flex: '1', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          
          <div className="card" style={{ padding: '1rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem' }}>Active Tasks ({inProgressTickets.length})</h3>
            {loading ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading assignments...</div>
            ) : inProgressTickets.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active assignments!</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {inProgressTickets.map(ticket => (
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
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: '600', fontSize: '0.9rem' }}>{ticket.script_name.replace('.py', '')}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ticket.resource_id}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ padding: '1rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem' }}>Completed History ({otherTickets.length})</h3>
            {otherTickets.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No completed tickets.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {otherTickets.map(ticket => (
                  <div 
                    key={ticket.id} 
                    onClick={() => setSelectedTicket(ticket)}
                    style={{ 
                      padding: '0.75rem', 
                      borderRadius: '8px', 
                      background: 'rgba(255, 255, 255, 0.02)', 
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: '600', fontSize: '0.9rem', color: 'var(--text-muted)' }}>{ticket.script_name.replace('.py', '')}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ticket.resource_id}</div>
                    </div>
                    <div>
                      <span style={{ 
                        fontSize: '0.7rem', padding: '0.2rem 0.4rem', borderRadius: '4px',
                        background: ticket.status === 'Completed' ? 'rgba(56, 189, 248, 0.1)' : 'rgba(255, 255, 255, 0.1)',
                        color: ticket.status === 'Completed' ? '#38bdf8' : '#fff'
                      }}>
                        {ticket.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Right Side: Ticket Details Panel */}
        <div style={{ flex: '1' }}>
          <TicketDetailsPanel 
            ticket={selectedTicket}
            actionComponent={
              selectedTicket?.status === 'In Progress' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <textarea 
                    placeholder="Provide a reason if it cannot be completed, or general notes..."
                    value={engineerComment}
                    onChange={(e) => setEngineerComment(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '0.85rem', resize: 'vertical', minHeight: '60px' }}
                  />
                  <div style={{ display: 'flex', gap: '1rem' }}>
                    <button 
                      onClick={handleSaveComment}
                      style={{ 
                        flex: '1',
                        background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.2) 100%)', 
                        color: '#fbbf24', border: '1px solid rgba(245, 158, 11, 0.4)', borderRadius: '8px', 
                        padding: '0.75rem', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 'bold' 
                      }}
                    >
                      Save Notes
                    </button>
                    <button 
                      onClick={() => updateTicketStatus(selectedTicket.id, 'Completed')}
                      style={{ 
                        flex: '1',
                        background: 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)', 
                        color: '#fff', border: 'none', borderRadius: '8px', 
                        padding: '0.75rem', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 'bold' 
                      }}
                    >
                      Mark as Completed
                    </button>
                  </div>
                </div>
              ) : null
            }
          />
        </div>

      </div>
    </div>
  );
}
