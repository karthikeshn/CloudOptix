import React from 'react';

export default function Settings({ token }) {
  return (
    <div className="card" style={{ maxWidth: '500px' }}>
      <div className="card-header">
        <h2>Settings</h2>
      </div>
      <div className="card-body">
        <p style={{ color: 'var(--text-muted)' }}>Additional settings will be available here soon.</p>
      </div>
    </div>
  );
}
