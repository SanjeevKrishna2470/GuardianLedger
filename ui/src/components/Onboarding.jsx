import React, { useState, useEffect } from 'react';
import { Settings, Shield, Key } from 'lucide-react';
import { API_BASE, fetchAuth } from '../config';

const Onboarding = ({ token }) => {
  const [hasKeys, setHasKeys] = useState(false);
  const [keyPreview, setKeyPreview] = useState(null);
  
  const [keyId, setKeyId] = useState('');
  const [keySecret, setKeySecret] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/merchant/keys`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(data => {
        if (data.has_keys) {
          setHasKeys(true);
          setKeyPreview(data.key_id_preview);
        }
      })
      .finally(() => setLoading(false));
  }, [token]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetchAuth(`${API_BASE}/api/merchant/keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          key_id: keyId,
          key_secret: keySecret,
          webhook_secret: webhookSecret
        })
      });
      if (res.ok) {
        setHasKeys(true);
        setMessage({ type: 'success', text: 'Keys saved securely!' });
        setKeyPreview(keyId.substring(0, 8) + '...');
        setKeyId('');
        setKeySecret('');
        setWebhookSecret('');
      } else {
        setMessage({ type: 'error', text: 'Failed to save keys.' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error.' });
    }
    setSaving(false);
  };

  if (loading) return <div style={{ padding: '24px' }}>Loading settings...</div>;

  return (
    <div>
      <header className="page-header">
        <h1><Settings size={20} style={{ verticalAlign: '-4px', marginRight: '8px' }} /> Settings & Integration</h1>
        <p>Configure your Razorpay credentials for live reconciliation.</p>
      </header>

      <div className="card" style={{ maxWidth: '600px', margin: '0' }}>
        <div className="card-header">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Key size={18} /> Razorpay Credentials</h2>
          {hasKeys && <span className="status-badge success">Configured</span>}
        </div>
        <div className="card-body">
          {hasKeys && (
            <div style={{ background: 'var(--bg-surface-secondary)', padding: '16px', borderRadius: '8px', marginBottom: '24px' }}>
              <p style={{ margin: 0, fontSize: '14px' }}>
                <Shield size={14} style={{ verticalAlign: '-2px', marginRight: '4px', color: 'var(--color-success)' }} />
                Your credentials are encrypted at rest. Current Key ID: <code>{keyPreview}</code>
              </p>
            </div>
          )}
          
          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', fontWeight: 500 }}>Razorpay Key ID</label>
              <input type="text" value={keyId} onChange={e => setKeyId(e.target.value)} required={!hasKeys} placeholder={hasKeys ? "Leave blank to keep unchanged" : "rzp_live_..."} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid var(--border-default)', fontSize: '14px' }} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', fontWeight: 500 }}>Razorpay Key Secret</label>
              <input type="password" value={keySecret} onChange={e => setKeySecret(e.target.value)} required={!hasKeys} placeholder={hasKeys ? "••••••••" : ""} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid var(--border-default)', fontSize: '14px' }} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', fontWeight: 500 }}>Webhook Secret</label>
              <input type="password" value={webhookSecret} onChange={e => setWebhookSecret(e.target.value)} required={!hasKeys} placeholder={hasKeys ? "••••••••" : ""} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid var(--border-default)', fontSize: '14px' }} />
            </div>
            
            <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '16px' }}>
              <button type="submit" disabled={saving || (!keyId && hasKeys)} className="btn btn-brand">
                {saving ? 'Saving...' : (hasKeys ? 'Update Keys' : 'Save Keys')}
              </button>
              {message && (
                <span style={{ fontSize: '13px', color: message.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)' }}>
                  {message.text}
                </span>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Onboarding;

