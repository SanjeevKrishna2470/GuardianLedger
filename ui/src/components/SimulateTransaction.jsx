import React, { useState } from 'react';
import { API_BASE } from '../config';

function SimulateTransaction({ onSimulate }) {
  const [isOpen, setIsOpen] = useState(false);
  const [type, setType] = useState('CLEAN');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleSimulate = async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/simulate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ type }),
      });
      if (response.ok) {
        const data = await response.json();
        setMessage(`Success! Simulated ${data.txn_ref} (${data.action})`);
        if (onSimulate) {
          onSimulate();
        }
      } else {
        setMessage('Simulation failed.');
      }
    } catch (error) {
      setMessage(`Error: ${error.message}`);
    }
    setLoading(false);
  };

  return (
    <div className="simulate-container">
      {!isOpen ? (
        <button className="fab-button" onClick={() => setIsOpen(true)}>
          + Simulate
        </button>
      ) : (
        <div className="simulate-panel">
          <div className="simulate-header">
            <h4>Simulate Transaction</h4>
            <button onClick={() => setIsOpen(false)}>x</button>
          </div>
          <div className="simulate-body">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="CLEAN">Clean Match</option>
              <option value="FEE_MISMATCH">Amount / Fee Mismatch</option>
              <option value="TIMING_LAG">Timing Lag</option>
              <option value="ORPHAN">Orphan (Missing in Bank/Ledger)</option>
            </select>
            <button onClick={handleSimulate} disabled={loading}>
              {loading ? 'Simulating...' : 'Simulate'}
            </button>
          </div>
          {message && <div className="simulate-message">{message}</div>}
        </div>
      )}
    </div>
  );
}

export default SimulateTransaction;
