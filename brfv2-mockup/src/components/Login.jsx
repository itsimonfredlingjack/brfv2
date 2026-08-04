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
      <div className="login-panel glass-panel">
        {/* §05 Lockup: the mark stands before the name at cap height. This is
            the first thing anyone sees, so it says who is speaking before it
            asks for anything. */}
        <div className="login-lockup">
          <TraffMark size={30} decorative />
          <h1 className="login-title">Träff</h1>
        </div>
        <p className="login-subtitle">Frågor om föreningens dokument, besvarade ur föreningens dokument.</p>
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

        {import.meta.env.DEV && (
          <div className="login-demo-hint">
            Demo: anna@gjutformen12.se / gjutformen-demo-2026
          </div>
        )}
      </div>
    </div>
  );
}

export default Login;
