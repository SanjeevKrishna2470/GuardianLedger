import { useState, useEffect } from 'react';
import { TrendingUp, AlertTriangle, ShieldAlert, Zap } from 'lucide-react';

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/dashboard');
        if (res.ok) {
          setData(await res.json());
        } else {
          throw new Error('Failed to fetch');
        }
      } catch {
        setData({
          match_rate: 98.5,
          total_exceptions: 12,
          total_quarantined: 3,
          throughput: 1450,
          exception_breakdown: {
            'Amount Mismatch': 5,
            'Date Mismatch': 4,
            'Missing in Source B': 3
          }
        });
      } finally {
        setLoading(false);
      }
    };
    fetch('http://localhost:8000/api/queue').catch(() => {});
    fetchData();
  }, []);

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
        <div className="page-header-row">
          <h1>Reconciliation Dashboard</h1>
          <span className="text-muted" style={{ fontSize: '12px' }}>
            Last updated: {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} · {dateStr}
          </span>
        </div>
      </header>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon brand"><TrendingUp size={20} /></div>
          <div className="metric-value">{data?.match_rate || '0'}%</div>
          <div className="metric-label">Match Rate</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon warning"><AlertTriangle size={20} /></div>
          <div className="metric-value">{data?.total_exceptions || '0'}</div>
          <div className="metric-label">Exceptions</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon danger"><ShieldAlert size={20} /></div>
          <div className="metric-value">{data?.total_quarantined || '0'}</div>
          <div className="metric-label">Quarantined</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon info"><Zap size={20} /></div>
          <div className="metric-value">{data?.throughput || '0'}<span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginLeft: '4px' }}>/s</span></div>
          <div className="metric-label">Throughput</div>
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
