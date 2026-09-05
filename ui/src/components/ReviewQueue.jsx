import React, { useState, useEffect } from 'react';
import { CheckCircle, Check, X } from 'lucide-react';
import { API_BASE, fetchAuth } from '../config';

const ReviewQueue = () => {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);

const toggleRow = (txn_ref) => {
  setExpandedRow(expandedRow === txn_ref ? null : txn_ref);
};

  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const res = await fetchAuth(`${API_BASE}/api/queue`);
        if (res.ok) {
          setQueue(await res.json());
        } else {
          setQueue([]);
        }
      } catch (err) {
        console.error('Error fetching queue:', err);
        setQueue([]);
      } finally {
        setLoading(false);
      }
    };
    fetchQueue();
  }, []);

  const handleAction = async (txn_ref, decision) => {
    try {
      await fetchAuth(`${API_BASE}/api/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ txn_ref, decision })
      });
    } catch (err) {
      console.error(err);
    }
    setQueue(prev => prev.filter(item => item.txn_ref !== txn_ref));
    setToast({ message: `${decision === 'approve' ? 'Approved' : 'Rejected'} ${txn_ref}`, type: decision });
    setTimeout(() => setToast(null), 3000);
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'REVIEW': return 'status-badge review';
      case 'EXCEPTION': return 'status-badge exception';
      case 'QUARANTINE': return 'status-badge quarantine';
      default: return 'status-badge';
    }
  };

  return (
    <div>
      {toast && (
        <div className="toast">
          {toast.type === 'approve'
            ? <Check size={16} />
            : <X size={16} />
          }
          {toast.message}
        </div>
      )}

      <header className="page-header">
        <h1>Review Queue <span className="count-badge">{queue.length}</span></h1>
        <p>Items flagged for human review by the reconciliation engine</p>
      </header>

      {loading ? (
        <div className="skeleton" style={{ height: '240px' }}></div>
      ) : queue.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">
              <CheckCircle size={24} />
            </div>
            <h2>All clear</h2>
            <p>No items require review at this time.</p>
          </div>
        </div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Status</th>
                <th>Category</th>
                <th>Age</th>
                <th>Reason</th>
                <th style={{ width: '160px' }}>Actions</th>
              </tr>
            </thead>
          <tbody>
  {queue.map((item) => (
    <React.Fragment key={item.txn_ref}>
      <tr
        onClick={() => toggleRow(item.txn_ref)}
        style={{ cursor: 'pointer', background: item.priority ? 'var(--color-warning-light)' : (expandedRow === item.txn_ref ? 'var(--bg-hover)' : undefined) }}
      >
        <td>{item.txn_ref}</td>
        <td><span className={getStatusClass(item.status || item.m4_action)}>{item.status || item.m4_action}</span></td>
        <td>{item.category || item.m2_category || '—'}</td>
        <td>
          {item.days_unresolved ?? 0}d
          {item.priority ? <span className="status-badge exception" style={{ marginLeft: '8px' }}>Priority</span> : null}
        </td>
        <td style={{ color: 'var(--text-secondary)', maxWidth: '300px' }}>{item.m4_reason || '—'}</td>
        <td>
          <div className="action-group" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => handleAction(item.txn_ref, 'approve')} className="btn btn-success btn-sm">Approve</button>
            <button onClick={() => handleAction(item.txn_ref, 'reject')} className="btn btn-danger-outline btn-sm">Reject</button>
          </div>
        </td>
      </tr>
      {expandedRow === item.txn_ref && (
        <tr style={{ background: 'var(--bg-surface-secondary)' }}>
          <td colSpan="6" style={{ padding: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '12.5px' }}>
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                <h4 style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>AI PROPOSAL</h4>
                {item.m3_extracted?.ai_proposal ? (
                  <div style={{ display: 'grid', gap: '6px' }}>
                    <div><span style={{ color: 'var(--text-secondary)' }}>Field: </span>{item.m3_extracted.ai_proposal.field}</div>
                    <div><span style={{ color: 'var(--text-secondary)' }}>Value: </span>{item.m3_extracted.ai_proposal.extracted_value}</div>
                    <div><span style={{ color: 'var(--text-secondary)' }}>Confidence: </span>{item.m3_extracted.ai_proposal.confidence}</div>
                    <div><span style={{ color: 'var(--text-secondary)' }}>Source span: </span><code>{item.m3_extracted.ai_proposal.source_span}</code></div>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-muted)', margin: 0 }}>No AI proposal for this item.</p>
                )}
              </div>
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                <h4 style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>RAW EVIDENCE</h4>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-primary)' }}>
                  {JSON.stringify(item.raw_evidence || 'No data', null, 2)}
                </pre>
              </div>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  ))}
</tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ReviewQueue;

