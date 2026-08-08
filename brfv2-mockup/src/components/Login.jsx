import React, { useState } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import TraffMark from './TraffMark';
import { api } from '../api';
import './Login.css';

function Login({ onLoggedIn, modelStatus = null }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const result = await api.login(email.trim(), password);
      // No setBusy(false) on success — the app swaps this screen out.
      onLoggedIn(result);
    } catch (err) {
      setError(err?.status === 401
        ? 'Fel e-post eller lösenord.'
        : `Kunde inte logga in: ${err.message}`);
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      {/* §05 Lockup, moved to full scale: the mark stands before the name at
          cap height, now large enough to actually be seen once instead of
          glimpsed at 30px. The panel it sits on is ink, not a plate behind
          the ring itself — the ring's own gap (§02) stays untouched: no
          tint, no gradient inside the circle. */}
      <div className="login-brand">
        <div className="login-brand-inner">
          <div className="login-brand-qualifier">BRF &amp; STYRELSE</div>
          <TraffMark size={84} decorative />
          <h1 className="login-brand-title">Träff</h1>
          <p className="login-brand-tagline">
            Frågor om föreningens dokument, besvarade ur föreningens dokument.
          </p>
        </div>
      </div>

      <div className="login-form-col">
        <div className="login-panel glass-panel">
          <div className="login-lockup-compact">
            <TraffMark size={26} decorative />
            <h1 className="login-title">Träff</h1>
          </div>

          {modelStatus && <div className="login-model-status">{modelStatus}</div>}

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="login-field">
              <span>E-postadress</span>
              <input
                type="email"
                autoComplete="email"
                autoFocus
                required
                placeholder="namn@forening.se"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
              />
            </label>
            <label className="login-field">
              <span>Lösenord</span>
              <input
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
              />
            </label>

            {error && (
              <div className="login-error">
                <AlertCircle size={15} /> {error}
              </div>
            )}

            <button type="submit" className="login-submit" disabled={busy}>
              {busy ? (<><Loader2 size={16} className="spin" /> Loggar in…</>) : 'Logga in'}
            </button>
          </form>

          {/* DEMO.md's own premise is "runnable without Simon in the room" —
              gating this to dev builds only worked against that in exactly
              the pilot build people actually use to try the demo. */}
          <div className="login-demo-hint">
            Demo: anna@gjutformen12.se / gjutformen-demo-2026
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;
