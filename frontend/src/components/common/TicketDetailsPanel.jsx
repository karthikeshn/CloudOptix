import React from 'react';

export default function TicketDetailsPanel({ ticket, actionComponent, onSaveDetails }) {
  const [editableEvidence, setEditableEvidence] = React.useState({});
  const [isEditing, setIsEditing] = React.useState(false);

  React.useEffect(() => {
    if (ticket && ticket.details) {
      try {
        const raw = JSON.parse(ticket.details);
        const ev = { ...raw };
        
        Object.keys(ev).forEach(k => {
          const lowerK = k.toLowerCase();
          if (['region', 'location', 'tags', 'state', 'status', 'area path', 'areapath', 'comment count', 'commentcount', 'effort', 'effort level', 'effortlevel'].includes(lowerK)) {
            delete ev[k];
          }
          if ((lowerK === 'approvalcomments' || lowerK === 'reasonforrejection') && !ev[k]) {
            delete ev[k];
          }
        });

        if (ev.VolumeId === ticket.resource_id) delete ev.VolumeId;
        if (ev.InstanceId === ticket.resource_id) delete ev.InstanceId;

        // Force specific values
        let witKey = 'WorkItemType';
        let titleKey = 'Title';
        let catKey = 'Category';
        Object.keys(ev).forEach(k => {
          const lowerK = k.toLowerCase();
          if (lowerK === 'workitemtype') witKey = k;
          if (lowerK === 'title') titleKey = k;
          if (lowerK === 'category') catKey = k;
        });
        
        const scriptBase = ticket.script_name ? ticket.script_name.replace('.py', '') : 'Task';
        ev[witKey] = "Task";
        ev[titleKey] = scriptBase;
        ev[catKey] = scriptBase;

        // Enforce numeric unique ticket ID
        ev.id = ticket.id;
        raw.id = ticket.id;
        setEditableEvidence(ev);
        setIsEditing(false);
      } catch (e) {
        console.error(e);
      }
    }
  }, [ticket]);

  if (!ticket) {
    return (
      <div className="card" style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', background: 'rgba(15, 23, 42, 0.4)', border: '1px dashed rgba(255,255,255,0.1)' }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'rgba(255,255,255,0.2)' }}><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
        <span>Select a ticket to view detailed analysis.</span>
      </div>
    );
  }

  let rawDetails = {};
  try {
    rawDetails = JSON.parse(ticket.details);
  } catch (e) {
    console.error("Failed to parse ticket details JSON");
  }

  const region = rawDetails.Region || rawDetails.region || rawDetails.Location || null;
  const tags = rawDetails.Tags || rawDetails.tags || null;
  const state = rawDetails.State || rawDetails.state || rawDetails.Status || null;
  
  const evidence = { ...rawDetails };
  
  Object.keys(evidence).forEach(k => {
    const lowerK = k.toLowerCase();
    if (['region', 'location', 'tags', 'state', 'status', 'area path', 'areapath', 'comment count', 'commentcount', 'effort', 'effort level', 'effortlevel'].includes(lowerK)) {
      delete evidence[k];
    }
    if ((lowerK === 'approvalcomments' || lowerK === 'reasonforrejection') && !evidence[k]) {
      delete evidence[k];
    }
  });
  
  if (evidence.VolumeId === ticket.resource_id) delete evidence.VolumeId;
  if (evidence.InstanceId === ticket.resource_id) delete evidence.InstanceId;

  // Force specific values
  let witKeyRender = 'WorkItemType';
  let titleKeyRender = 'Title';
  let catKeyRender = 'Category';
  Object.keys(evidence).forEach(k => {
    const lowerK = k.toLowerCase();
    if (lowerK === 'workitemtype') witKeyRender = k;
    if (lowerK === 'title') titleKeyRender = k;
    if (lowerK === 'category') catKeyRender = k;
  });
  
  const scriptBaseRender = ticket.script_name ? ticket.script_name.replace('.py', '') : 'Task';
  evidence[witKeyRender] = "Task";
  evidence[titleKeyRender] = scriptBaseRender;
  evidence[catKeyRender] = scriptBaseRender;

  // Enforce numeric unique ticket ID
  evidence.id = ticket.id;

  const getStatusConfig = (status) => {
    switch (status) {
      case 'Pending': return { bg: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(217, 119, 6, 0.1))', color: '#fbbf24', border: 'rgba(245, 158, 11, 0.3)', shadow: '0 0 10px rgba(245, 158, 11, 0.2)' };
      case 'Approved': return { bg: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.1))', color: '#34d399', border: 'rgba(16, 185, 129, 0.3)', shadow: '0 0 10px rgba(16, 185, 129, 0.2)' };
      case 'In Progress': return { bg: 'linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(2, 132, 199, 0.1))', color: '#7dd3fc', border: 'rgba(56, 189, 248, 0.3)', shadow: '0 0 10px rgba(56, 189, 248, 0.2)' };
      case 'Completed': return { bg: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(79, 70, 229, 0.1))', color: '#818cf8', border: 'rgba(99, 102, 241, 0.3)', shadow: '0 0 10px rgba(99, 102, 241, 0.2)' };
      case 'Rejected': return { bg: 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1))', color: '#f87171', border: 'rgba(239, 68, 68, 0.3)', shadow: '0 0 10px rgba(239, 68, 68, 0.2)' };
      default: return { bg: 'rgba(255, 255, 255, 0.05)', color: '#fff', border: 'rgba(255,255,255,0.1)', shadow: 'none' };
    }
  };
  const stConfig = getStatusConfig(ticket.status);

  return (
    <div className="card" style={{ 
      position: 'sticky', 
      top: '1rem', 
      display: 'flex', 
      flexDirection: 'column', 
      background: 'rgba(15, 23, 42, 0.7)',
      backdropFilter: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
      overflow: 'hidden'
    }}>
      {/* Decorative Header Glow */}
      <div style={{ position: 'absolute', top: '-50px', left: '-50px', right: '-50px', height: '150px', background: 'radial-gradient(ellipse at top, rgba(37, 99, 235, 0.15), transparent 70%)', pointerEvents: 'none' }} />

      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', zIndex: 1 }}>
        {/* HEADER */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h3 style={{ margin: '0 0 0.4rem 0', fontSize: '1.4rem', fontWeight: '700', letterSpacing: '-0.5px', color: '#f8fafc' }}>
              Ticket #{ticket.id}
            </h3>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              {ticket.script_name.replace('.py', '')}
            </div>
          </div>
          <span style={{ 
            fontSize: '0.75rem', padding: '0.35rem 0.75rem', borderRadius: '20px', fontWeight: '600',
            background: stConfig.bg, color: stConfig.color, border: `1px solid ${stConfig.border}`,
            boxShadow: stConfig.shadow, textTransform: 'uppercase', letterSpacing: '0.05em'
          }}>
            {ticket.status}
          </span>
        </div>

        {/* PILLAR 1: RECOMMENDED ACTION */}
        {ticket.recommended_action && (
          <div style={{ 
            padding: '1rem', 
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(0,0,0,0))', 
            border: '1px solid rgba(239, 68, 68, 0.3)', 
            borderRadius: '10px',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <div style={{ position: 'absolute', top: 0, left: 0, bottom: 0, width: '4px', background: '#ef4444' }} />
            <div style={{ fontSize: '0.8rem', color: '#fca5a5', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '700', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
              Action Required
            </div>
            <div style={{ fontSize: '1.1rem', color: '#fff', fontWeight: '500', marginLeft: '0.2rem' }}>
              {ticket.recommended_action}
            </div>
          </div>
        )}

        {/* PILLAR 2: FINANCIAL IMPACT & RESOURCE IDENTIFIER */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div style={{ background: 'linear-gradient(145deg, rgba(16, 185, 129, 0.05), rgba(0,0,0,0.2))', padding: '1rem', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.15)' }}>
            <div style={{ fontSize: '0.7rem', color: '#a7f3d0', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '600' }}>Financial Impact</div>
            <div style={{ fontSize: '1.6rem', fontWeight: '800', color: '#34d399', textShadow: '0 0 20px rgba(52, 211, 153, 0.3)' }}>
              {ticket.potential_savings ? `$${String(ticket.potential_savings).replace('$', '')}` : 'Unknown'}
            </div>
          </div>
          
          <div style={{ background: 'linear-gradient(145deg, rgba(255,255,255,0.03), rgba(0,0,0,0.2))', padding: '1rem', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '600' }}>Resource ID</div>
            <div style={{ fontSize: '0.95rem', fontFamily: 'SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace', wordBreak: 'break-all', color: '#e2e8f0', fontWeight: '500' }}>
              {ticket.resource_id}
            </div>
          </div>
        </div>

        {/* METADATA STRIP */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
          {((evidence.accountId || evidence.ACCOUNTID || evidence.AccountId) || ticket.aws_account_id || ticket.account_id) && (
            <span style={{ fontSize: '0.75rem', background: 'rgba(56, 189, 248, 0.1)', color: '#7dd3fc', padding: '0.3rem 0.6rem', borderRadius: '6px', border: '1px solid rgba(56, 189, 248, 0.2)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{opacity: 0.7}}>ACC:</span> {evidence.accountId || evidence.ACCOUNTID || evidence.AccountId || ticket.aws_account_id || ticket.account_id}
            </span>
          )}
          {region && (
            <span style={{ fontSize: '0.75rem', background: 'rgba(168, 85, 247, 0.1)', color: '#c084fc', padding: '0.3rem 0.6rem', borderRadius: '6px', border: '1px solid rgba(168, 85, 247, 0.2)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{opacity: 0.7}}>REG:</span> {region}
            </span>
          )}
          {state && (
            <span style={{ fontSize: '0.75rem', background: 'rgba(251, 146, 60, 0.1)', color: '#fdba74', padding: '0.3rem 0.6rem', borderRadius: '6px', border: '1px solid rgba(251, 146, 60, 0.2)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{opacity: 0.7}}>STS:</span> {state}
            </span>
          )}
          {tags && (
            <span style={{ fontSize: '0.75rem', background: 'rgba(244, 114, 182, 0.1)', color: '#f9a8d4', padding: '0.3rem 0.6rem', borderRadius: '6px', border: '1px solid rgba(244, 114, 182, 0.2)', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{opacity: 0.7}}>TAG:</span> {typeof tags === 'string' ? tags : JSON.stringify(tags)}
            </span>
          )}
        </div>

        {/* PILLAR 3: EVIDENCE & TELEMETRY */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <div style={{ fontSize: '0.9rem', color: '#f8fafc', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              Evidence &amp; Telemetry
            </div>
            <button 
              onClick={() => {
                if (isEditing) {
                  // Done Editing - merge back with uneditable properties and save
                  const newFullDetails = { ...rawDetails, ...editableEvidence };
                  if (onSaveDetails) onSaveDetails(newFullDetails);
                }
                setIsEditing(!isEditing);
              }} 
              style={{ background: isEditing ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255,255,255,0.05)', color: isEditing ? '#38bdf8' : '#cbd5e1', border: isEditing ? '1px solid rgba(56, 189, 248, 0.3)' : '1px solid rgba(255,255,255,0.1)', padding: '0.35rem 0.75rem', borderRadius: '6px', fontSize: '0.7rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem', transition: 'all 0.2s', fontWeight: '600' }}
            >
              {isEditing ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> Done Editing</> : <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> Edit Fields</>}
            </button>
          </div>
          <div style={{ background: 'rgba(0,0,0,0.4)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)', overflow: 'hidden', boxShadow: 'inset 0 2px 10px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
              {Object.entries(editableEvidence).slice(0, 6).map(([key, val], idx) => (
                <div key={key} style={{ 
                  padding: '0.75rem 1rem', 
                  borderBottom: idx < 4 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                  borderRight: idx % 2 === 0 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                  transition: 'background 0.2s ease'
                }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                  <div style={{ fontSize: '0.65rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '600', marginBottom: '0.4rem' }}>{key}</div>
                  
                  {isEditing ? (
                    <input 
                      type="text" 
                      value={val === null || val === undefined ? '' : typeof val === 'object' ? JSON.stringify(val) : val}
                      onChange={(e) => setEditableEvidence({...editableEvidence, [key]: e.target.value})}
                      style={{ width: '100%', padding: '0.4rem 0.5rem', background: 'rgba(15, 23, 42, 0.9)', border: '1px solid rgba(56, 189, 248, 0.4)', borderRadius: '4px', color: '#f8fafc', fontSize: '0.85rem', outline: 'none', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.3)' }}
                    />
                  ) : (
                    <div style={{ fontSize: '0.9rem', color: '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: '500' }}>
                      {val === null || val === '' ? <span style={{ color: '#475569', fontStyle: 'italic' }}>N/A</span> : typeof val === 'object' ? JSON.stringify(val) : String(val)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {Object.keys(evidence).length > 6 && (
              <div style={{ padding: '0.75rem 1rem', background: 'rgba(37, 99, 235, 0.05)', borderTop: '1px solid rgba(37, 99, 235, 0.2)' }}>
                <details>
                  <summary style={{ fontSize: '0.75rem', color: '#60a5fa', cursor: 'pointer', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.3rem', userSelect: 'none' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    View All {Object.keys(evidence).length} Properties
                  </summary>
                  <div style={{ margin: '0.85rem 0 0 0', padding: '1rem', background: 'rgba(0,0,0,0.25)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '400px', overflowY: 'auto' }}>
                    {Object.entries(editableEvidence).slice(6).map(([key, val]) => (
                      <div key={key} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1.5rem', alignItems: 'center', padding: '0.6rem 0.8rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.03)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '600' }}>{key}</span>
                        
                        {isEditing ? (
                          <input 
                            type="text" 
                            value={val === null || val === undefined ? '' : typeof val === 'object' ? JSON.stringify(val) : val}
                            onChange={(e) => setEditableEvidence({...editableEvidence, [key]: e.target.value})}
                            style={{ width: '100%', padding: '0.5rem 0.75rem', background: 'rgba(15, 23, 42, 0.9)', border: '1px solid rgba(56, 189, 248, 0.4)', borderRadius: '6px', color: '#f8fafc', fontSize: '0.85rem', outline: 'none', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.3)' }}
                          />
                        ) : (
                          typeof val === 'boolean' ? (
                            <span style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderRadius: '4px', background: val ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)', color: val ? '#34d399' : '#f87171', width: 'max-content', fontWeight: '600', border: `1px solid ${val ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}` }}>
                              {val ? '✓ TRUE' : '✕ FALSE'}
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.85rem', color: '#f8fafc', fontWeight: '500', wordBreak: 'break-word', fontFamily: (typeof val === 'string' && val.includes('-') && val.length < 40 && !val.includes(' ')) ? 'SFMono-Regular, Consolas, monospace' : 'inherit', lineHeight: '1.4' }}>
                              {val === null || val === '' ? <span style={{ color: '#475569', fontStyle: 'italic' }}>N/A</span> : typeof val === 'object' ? JSON.stringify(val) : String(val)}
                            </span>
                          )
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>

        {/* PILLAR 5: AUDIT TRAIL */}
        {(ticket.assigned_at || ticket.completed_at || ticket.approved_at) && (
          <div>
            <div style={{ fontSize: '0.9rem', color: '#f8fafc', fontWeight: '600', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
              Audit Trail
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)', padding: '1rem' }}>
              {ticket.assigned_at && (
                <div style={{ fontSize: '0.8rem', marginBottom: ticket.completed_at ? '0.75rem' : '0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#38bdf8' }} />
                    <span style={{ color: '#94a3b8' }}>Assigned to <strong style={{ color: '#f8fafc' }}>{ticket.assigned_to_name || 'Unknown'}</strong> by <strong style={{ color: '#f8fafc' }}>{ticket.assigned_by_name || 'System'}</strong></span>
                  </div>
                  <div style={{ color: '#64748b', marginLeft: '0.9rem', fontSize: '0.75rem' }}>
                    {new Date(ticket.assigned_at).toLocaleString()}
                  </div>
                </div>
              )}
              {ticket.completed_at && (
                <div style={{ fontSize: '0.8rem', paddingTop: ticket.assigned_at ? '0.75rem' : '0', borderTop: ticket.assigned_at ? '1px dashed rgba(255,255,255,0.1)' : 'none' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10b981', boxShadow: '0 0 5px #10b981' }} />
                    <span style={{ color: '#94a3b8' }}>Completed by <strong style={{ color: '#10b981' }}>{ticket.completed_by_name || 'Unknown'}</strong></span>
                  </div>
                  <div style={{ color: '#64748b', marginLeft: '0.9rem', fontSize: '0.75rem' }}>
                    {new Date(ticket.completed_at).toLocaleString()}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ACTION COMPONENT */}
      {actionComponent && (
        <div style={{ padding: '1.5rem', background: 'rgba(0,0,0,0.3)', borderTop: '1px solid rgba(255,255,255,0.08)', zIndex: 1 }}>
          {actionComponent}
        </div>
      )}
    </div>
  );
}
