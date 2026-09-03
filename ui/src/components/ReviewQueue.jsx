import { useState, useEffect } from 'react';
import { CheckCircle, Check, X } from 'lucide-react';

const ReviewQueue = () => {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/queue');
        if (res.ok) {
          setQueue(await res.json());
        } else {
          throw new Error('Failed to fetch queue');
        }
      } catch {
        setQueue([
          { txn_ref: 'TXN-1001', status: 'REVIEW', category: 'Settlement', m4_reason: 'Amount mismatch ($0.05)' },
          { txn_ref: 'TXN-1002', status: 'EXCEPTION', category: 'Funding', m4_reason: 'Missing reference ID' },
          { txn_ref: 'TXN-1003', status: 'QUARANTINE', category: 'Transfer', m4_reason: 'Potential duplicate' }
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchQueue();
  }, []);

  const handleAction = async (txn_ref, decision) => {
    try {
      await fetch('http://localhost:8000/api/action', {
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
                <th>Reason</th>
                <th style={{ width: '160px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((item) => (
                <tr key={item.txn_ref}>
                  <td>{item.txn_ref}</td>
                  <td><span className={getStatusClass(item.status || item.m4_action)}>{item.status || item.m4_action}</span></td>
                  <td>{item.category || item.m2_category || '—'}</td>
                  <td style={{ color: 'var(--text-secondary)', maxWidth: '300px' }}>{item.m4_reason || '—'}</td>
                  <td>
                    <div className="action-group">
                      <button onClick={() => handleAction(item.txn_ref, 'approve')} className="btn btn-success btn-sm">Approve</button>
                      <button onClick={() => handleAction(item.txn_ref, 'reject')} className="btn btn-danger-outline btn-sm">Reject</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ReviewQueue;
