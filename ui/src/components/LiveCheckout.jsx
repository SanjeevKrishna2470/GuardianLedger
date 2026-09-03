import React, { useState } from 'react';
import { CreditCard, CheckCircle, XCircle, Loader } from 'lucide-react';
import { API_BASE } from '../config';

function LiveCheckout() {
  const [amount, setAmount] = useState(500);
  const [currency, setCurrency] = useState('INR');
  const [status, setStatus] = useState('idle'); // idle | loading | success | error
  const [message, setMessage] = useState('');
  const [lastPayment, setLastPayment] = useState(null);

  const handlePay = async () => {
    setStatus('loading');
    setMessage('');

    try {
      // Step 1: Create an order via our backend
      const orderRes = await fetch(`${API_BASE}/api/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: amount * 100, currency }), // Razorpay expects paise
      });

      let orderData;
      const text = await orderRes.text();
      try {
        orderData = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(text || `Server returned HTTP ${orderRes.status}`);
      }

      if (!orderRes.ok) {
        throw new Error(orderData.detail || orderData.message || `Failed to create order (HTTP ${orderRes.status})`);
      }

      const razorpayKey = import.meta.env.VITE_RAZORPAY_KEY_ID || orderData.key_id || '';
      if (!razorpayKey) {
        throw new Error('Razorpay Key ID is missing. Please set RAZORPAY_KEY_ID in backend environment variables or VITE_RAZORPAY_KEY_ID in frontend environment.');
      }

      // Step 2: Open Razorpay Checkout
      const options = {
        key: razorpayKey,
        amount: orderData.amount,
        currency: orderData.currency,
        name: 'Guardian Ledger',
        description: 'Test Transaction',
        order_id: orderData.order_id,
        handler: function (response) {
          // Payment was successful
          setStatus('success');
          setLastPayment({
            payment_id: response.razorpay_payment_id,
            order_id: response.razorpay_order_id,
            signature: response.razorpay_signature,
          });
          setMessage(`Payment successful! ID: ${response.razorpay_payment_id}`);
        },
        prefill: {
          name: 'Test User',
          email: 'test@guardianledger.dev',
          contact: '9999999999',
        },
        theme: {
          color: '#6366f1',
        },
        modal: {
          ondismiss: function () {
            setStatus('idle');
            setMessage('Payment cancelled by user.');
          },
        },
      };

      if (!window.Razorpay) {
        throw new Error(
          'Razorpay SDK not loaded. Ensure the checkout script is in index.html.'
        );
      }

      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (response) {
        setStatus('error');
        setMessage(
          `Payment failed: ${response.error.description} (${response.error.code})`
        );
      });
      rzp.open();
    } catch (err) {
      setStatus('error');
      setMessage(`Error: ${err.message}`);
    }
  };

  return (
    <div>
      <header className="page-header">
        <h1>Live Checkout</h1>
        <p>Create a real Razorpay test transaction to exercise the full webhook pipeline</p>
      </header>

      <div className="card" style={{ maxWidth: '520px' }}>
        <div className="card-header">
          <h2>
            <CreditCard size={18} style={{ marginRight: '8px', verticalAlign: 'text-bottom' }} />
            New Payment
          </h2>
        </div>
        <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Amount (₹)
            </label>
            <input
              type="number"
              min="1"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="filter-input"
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Currency
            </label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-default)',
                background: 'var(--bg-surface)',
                color: 'var(--text-primary)',
                fontSize: '13px',
              }}
            >
              <option value="INR">INR — Indian Rupee</option>
              <option value="USD">USD — US Dollar</option>
            </select>
          </div>

          <button
            onClick={handlePay}
            disabled={status === 'loading' || amount <= 0}
            className="btn btn-success"
            style={{ width: '100%', padding: '10px', fontSize: '14px', marginTop: '4px' }}
          >
            {status === 'loading' ? (
              <>
                <Loader size={14} style={{ marginRight: '6px', animation: 'spin 1s linear infinite' }} />
                Creating order…
              </>
            ) : (
              <>Pay ₹{amount} with Razorpay</>
            )}
          </button>
        </div>
      </div>

      {/* Feedback area */}
      {message && (
        <div
          className="card"
          style={{
            maxWidth: '520px',
            marginTop: '16px',
            borderLeft: `3px solid ${status === 'success' ? 'var(--color-success)' : status === 'error' ? 'var(--color-danger)' : 'var(--color-neutral)'}`,
          }}
        >
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {status === 'success' ? (
              <CheckCircle size={18} style={{ color: 'var(--color-success)', flexShrink: 0 }} />
            ) : status === 'error' ? (
              <XCircle size={18} style={{ color: 'var(--color-danger)', flexShrink: 0 }} />
            ) : null}
            <span style={{ fontSize: '13px' }}>{message}</span>
          </div>
        </div>
      )}

      {/* Last Payment Details */}
      {lastPayment && (
        <div className="card" style={{ maxWidth: '520px', marginTop: '16px' }}>
          <div className="card-header">
            <h2>Payment Details</h2>
          </div>
          <div className="card-body" style={{ fontSize: '12.5px' }}>
            <div style={{ display: 'grid', gap: '8px' }}>
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Payment ID: </span>
                <code>{lastPayment.payment_id}</code>
              </div>
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Order ID: </span>
                <code>{lastPayment.order_id}</code>
              </div>
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Signature: </span>
                <code style={{ wordBreak: 'break-all' }}>{lastPayment.signature}</code>
              </div>
            </div>
            <p style={{ marginTop: '12px', color: 'var(--text-muted)', fontSize: '11.5px' }}>
              The Razorpay webhook will deliver a <code>payment.captured</code> event to the backend.
              Check the Transactions page to see it reconciled.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default LiveCheckout;
