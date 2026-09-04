import React, { useState, useEffect } from 'react';
import { Search, Inbox } from 'lucide-react';
import { API_BASE } from '../config';

const Transactions = () => {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchTransactions = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/transactions`);
        if (res.ok) {
          setTransactions(await res.json());
        } else {
          throw new Error('Failed to fetch transactions');
        }
      } catch {
        setTransactions([
          { txn_ref: 'TXN-9001', match_result: 'MATCHED', category: 'Settlement', action: 'AUTO', reason: 'Exact match' },
          { txn_ref: 'TXN-1001', match_result: 'MANUAL', category: 'Settlement', action: 'APPROVE', reason: 'Amount mismatch ($0.05)' },
          { txn_ref: 'TXN-8002', match_result: 'MATCHED', category: 'Funding', action: 'AUTO', reason: 'Fuzzy match on date' }
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchTransactions();
  }, []);

  const getBadgeClass = (value) => {
    switch (value) {
      case 'MATCHED':
      case 'AUTO':
      case 'APPROVE': return 'status-badge success';
      case 'MANUAL': return 'status-badge review';
      case 'EXCEPTION':
      case 'REJECT': return 'status-badge exception';
      default: return 'status-badge';
    }
  };

  const getSourceBadge = (source) => {
    switch (source) {
      case 'LIVE_WEBHOOK':
        return <span className="status-badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.3)' }}>⚡ Live Webhook</span>;
      case 'SIMULATION':
        return <span className="status-badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', border: '1px solid rgba(245, 158, 11, 0.3)' }}>🧪 Simulation</span>;
      default:
        return <span className="status-badge" style={{ background: 'rgba(107, 114, 128, 0.15)', color: '#9ca3af', border: '1px solid rgba(107, 114, 128, 0.3)' }}>📊 Batch Pipeline</span>;
    }
  };

  const filtered = transactions.filter(txn => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (txn.txn_ref || '').toLowerCase().includes(q) ||
      (txn.source || '').toLowerCase().includes(q) ||
      (txn.match_result || txn.m1_match_result || txn.m1_match_status || '').toLowerCase().includes(q) ||
      (txn.category || txn.m2_category || '').toLowerCase().includes(q) ||
      (txn.action || txn.m4_action || '').toLowerCase().includes(q) ||
      (txn.reason || txn.m4_reason || '').toLowerCase().includes(q)
    );
  });

  const [expandedRow, setExpandedRow] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Reset to page 1 whenever search or pageSize changes
  useEffect(() => { setPage(1); }, [search, pageSize]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * pageSize;
  const pageEnd = Math.min(pageStart + pageSize, filtered.length);
  const paginated = filtered.slice(pageStart, pageEnd);

  const toggleRow = (txn_ref) => {
    setExpandedRow(expandedRow === txn_ref ? null : txn_ref);
  };

  const paginationStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderTop: '1px solid var(--border-default)',
    fontSize: '13px',
    color: 'var(--text-secondary)',
    flexWrap: 'wrap',
    gap: '8px',
  };

  const btnStyle = (disabled) => ({
    padding: '4px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
    background: disabled ? 'transparent' : 'var(--bg-surface)',
    color: disabled ? 'var(--text-tertiary)' : 'var(--text-primary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: '13px',
  });

  return (
    <div>
      <header className="page-header">
        <h1>Transactions <span className="count-badge">{transactions.length}</span></h1>
        <p>Complete audit log of all processed transactions</p>
      </header>

      <div className="filter-bar">
        <div className="filter-input-wrapper">
          <Search size={15} />
          <input
            className="filter-input"
            type="text"
            placeholder="Search by reference, source, status, or category…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          <label htmlFor="page-size">Rows:</label>
          <select
            id="page-size"
            value={pageSize}
            onChange={e => setPageSize(Number(e.target.value))}
            style={{ padding: '4px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)', color: 'var(--text-primary)', fontSize: '13px' }}
          >
            {[25, 50, 100, 250].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: '240px' }}></div>
      ) : filtered.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon" style={{ background: 'var(--color-neutral-light)', color: 'var(--color-neutral)' }}>
              <Inbox size={24} />
            </div>
            <h2>{search ? 'No results' : 'No transactions'}</h2>
            <p>{search ? `No transactions match "${search}"` : 'Run the pipeline or trigger a transaction to see data.'}</p>
          </div>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Source</th>
                <th>Match Result</th>
                <th>Category</th>
                <th>Action</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((txn) => (
                <React.Fragment key={txn.txn_ref}>
                  <tr 
                    onClick={() => toggleRow(txn.txn_ref)} 
                    style={{ cursor: 'pointer', background: expandedRow === txn.txn_ref ? 'var(--bg-hover)' : '' }}
                  >
                    <td><code>{txn.txn_ref}</code></td>
                    <td>{getSourceBadge(txn.source)}</td>
                    <td><span className={getBadgeClass(txn.match_result || txn.m1_match_result || txn.m1_match_status)}>{txn.match_result || txn.m1_match_result || txn.m1_match_status || '—'}</span></td>
                    <td>{txn.category || txn.m2_category || '—'}</td>
                    <td><span className={getBadgeClass(txn.action || txn.m4_action)}>{txn.action || txn.m4_action || '—'}</span></td>
                    <td style={{ color: 'var(--text-secondary)' }}>{txn.reason || txn.m4_reason || '—'}</td>
                  </tr>
                  {expandedRow === txn.txn_ref && (
                    <tr style={{ background: 'var(--bg-surface-secondary)' }}>
                      <td colSpan="6" style={{ padding: '20px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', fontSize: '12.5px' }}>
                          <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                            <h4 style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>GATEWAY RECORD</h4>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-primary)' }}>
                              {JSON.stringify(txn.raw_evidence?.gateway_record || 'No data', null, 2)}
                            </pre>
                          </div>
                          <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                            <h4 style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>BANK RECORD</h4>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-primary)' }}>
                              {JSON.stringify(txn.raw_evidence?.bank_record || 'No data', null, 2)}
                            </pre>
                          </div>
                          <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                            <h4 style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>LEDGER RECORD</h4>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-primary)' }}>
                              {JSON.stringify(txn.raw_evidence?.ledger_record || 'No data', null, 2)}
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

          {/* Pagination controls */}
          <div style={paginationStyle}>
            <span>
              Showing <strong>{filtered.length === 0 ? 0 : pageStart + 1}–{pageEnd}</strong> of <strong>{filtered.length}</strong>
              {search && ` (filtered from ${transactions.length} total)`}
            </span>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <button style={btnStyle(safePage === 1)} disabled={safePage === 1} onClick={() => setPage(1)}>«</button>
              <button style={btnStyle(safePage === 1)} disabled={safePage === 1} onClick={() => setPage(p => Math.max(1, p - 1))}>‹ Prev</button>
              <span style={{ padding: '4px 8px' }}>Page {safePage} of {totalPages}</span>
              <button style={btnStyle(safePage === totalPages)} disabled={safePage === totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Next ›</button>
              <button style={btnStyle(safePage === totalPages)} disabled={safePage === totalPages} onClick={() => setPage(totalPages)}>»</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Transactions;
