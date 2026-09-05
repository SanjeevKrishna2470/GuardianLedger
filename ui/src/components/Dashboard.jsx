import { useState, useEffect } from 'react';
import { TrendingUp, AlertTriangle, ShieldAlert, Users } from 'lucide-react';
import { API_BASE, fetchAuth } from '../config';

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningPipeline, setRunningPipeline] = useState(false);

  const fetchData = async () => {
    try {
      const res = await fetchAuth(`${API_BASE}/api/dashboard`);
      if (res.ok) {
        const json = await res.json();
        if (!json.error) {
          setData(json);
        } else {
          setData(null);
        }
      } else {
        setData(null);
      }
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRunPipeline = async () => {
    setRunningPipeline(true);
    try {
      const res = await fetchAuth(`${API_BASE}/api/run-pipeline`, { method: 'POST' });
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (err) {
      console.error('Error running pipeline:', err);
    } finally {
      setRunningPipeline(false);
    }
  };

  const now = new Date();
  const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening';
  const dateStr = now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  if (loading) {
    return (
      <div>
        <header className="page-header">
          <p className="text-secondary" style={{ marginBottom: '2px' }}>{greeting}</p>
          <h1>Reconciliation Dashboard</h1>
        </header>
        <div className="metrics-grid">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="skeleton" style={{ height: '120px' }}></div>
          ))}
        </div>
        <div className="skeleton" style={{ height: '200px' }}></div>
      </div>
    );
  }

  const breakdownEntries = data?.exception_breakdown ? Object.entries(data.exception_breakdown) : [];
  const maxCount = Math.max(...breakdownEntries.map(([, c]) => c), 1);

  return (
    <div>
      <header className="page-header">
        <p className="text-secondary" style={{ marginBottom: '2px' }}>{greeting}</p>
        <div className="page-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>Reconciliation Dashboard</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className="text-muted" style={{ fontSize: '12px' }}>
              Last updated: {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} Â· {dateStr}
            </span>
            <button
              onClick={handleRunPipeline}
              disabled={runningPipeline}
              className="btn btn-brand btn-sm"
              style={{ padding: '6px 14px', fontSize: '13px' }}
            >
              {runningPipeline ? 'Running Pipeline...' : 'â–¶ Run Pipeline'}
            </button>
          </div>
        </div>
      </header>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon brand"><TrendingUp size={20} /></div>
          <div className="metric-value">{data?.match_rate ?? 0}%</div>
          <div className="metric-label">Match Rate</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon warning"><AlertTriangle size={20} /></div>
          <div className="metric-value">{data?.total_exceptions ?? data?.total_processed ?? 0}</div>
          <div className="metric-label">Exceptions</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon danger"><ShieldAlert size={20} /></div>
          <div className="metric-value">{data?.total_quarantined ?? data?.quarantine_count ?? 0}</div>
          <div className="metric-label">Quarantined</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon info"><Users size={20} /></div>
          <div className="metric-value">{data?.human_agreement_rate ?? '—'}{data?.human_agreement_rate != null ? '%' : ''}</div>
          <div className="metric-label">Human Agreement{data?.human_decision_count ? ` (${data.human_decision_count})` : ''}</div>
        </div>
      </div>

      <div className="card" style={{ animation: 'fadeIn 0.4s ease both', animationDelay: '120ms', marginBottom: '16px' }}>
        <div className="card-header">
          <h2>Unmatched pile</h2>
          <span className="text-muted" style={{ fontSize: '12px' }}>Incremental reconciliation</span>
        </div>
        <div className="card-body" style={{ display: 'flex', gap: '24px' }}>
          <div>
            <div className="metric-value" style={{ fontSize: '22px' }}>{data?.unmatched_payments ?? 0}</div>
            <div className="metric-label">Unmatched payments</div>
          </div>
          <div>
            <div className="metric-value" style={{ fontSize: '22px' }}>{data?.unmatched_bank ?? 0}</div>
            <div className="metric-label">Unmatched bank lines</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ animation: 'fadeIn 0.4s ease both', animationDelay: '200ms' }}>
        <div className="card-header">
          <h2>Exception Breakdown</h2>
          <span className="text-muted" style={{ fontSize: '12px' }}>{breakdownEntries.reduce((s, [, c]) => s + c, 0)} total</span>
        </div>
        <div className="card-body">
          <div className="breakdown-list">
            {breakdownEntries.map(([reason, count]) => (
              <div key={reason} className="breakdown-item">
                <div className="breakdown-item-header">
                  <span className="breakdown-item-label">{reason}</span>
                  <span className="breakdown-item-count">{count}</span>
                </div>
                <div className="breakdown-bar">
                  <div
                    className="breakdown-bar-fill"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;

