import React, { useState } from 'react';
import { Loader2, AlertCircle, CheckCircle2, HardDrive } from 'lucide-react';
import TraffMark from './TraffMark';
import { desktopApi } from '../api';
import './Setup.css';

const MIN_PASSWORD_LENGTH = 12;

/**
 * §05 Lockup, primary horizontal: the mark stands before the name at cap
 * height. This is the first screen the product is ever seen on, so it is the
 * one place the full lockup earns its space.
 */
function Lockup() {
  return (
    <div className="setup-lockup">
      <TraffMark size={32} />
      <span className="setup-lockup-name">Träff</span>
    </div>
  );
}

/**
 * First-run provisioning for the installed application.
 *
 * The product ships with no accounts and no seeded associations, so this is
 * the only way an installation gets its first owner. It never invents data:
 * the association is created empty and the model runtime is left unconfigured
 * unless the user supplies an address here.
 */
function Setup({ state, onProvisioned }) {
  const [step, setStep] = useState('account');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [brfName, setBrfName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [session, setSession] = useState(null);

  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('gemma4:e12b');
  const [label, setLabel] = useState('');
  const [probe, setProbe] = useState(null);

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  const passwordMismatch = repeat.length > 0 && repeat !== password;

  const submitAccount = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (password !== repeat) {
      setError('Lösenorden är inte lika.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await desktopApi.setup({
        name: name.trim(),
        email: email.trim(),
        password,
        brfName: brfName.trim(),
      });
      setSession(result);
      setStep('model');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const saveModelRuntime = async () => {
    setError(null);
    setBusy(true);
    try {
      await desktopApi.putModelRuntime({
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        label: label.trim(),
        timeoutS: 300,
      });
      const result = await desktopApi.testModelRuntime();
      setProbe(result);
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const finish = () => onProvisioned(session);

  if (step === 'model') {
    return (
      <div className="setup-screen">
        <div className="setup-panel">
          <Lockup />
          <h1 className="setup-title">Föreningen är skapad</h1>
          <p className="setup-subtitle">
            Sista steget: peka ut den självhostade modelltjänst som ska generera
            svaren. Applikationen kontaktar aldrig någon annan tjänst än den du
            anger här.
          </p>

          <div className="setup-form">
            <label className="ui-field">
              <span>Modelltjänstens adress</span>
              <input
                className="ui-input"
                type="url"
                autoFocus
                placeholder="http://127.0.0.1:8000/v1"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                disabled={busy}
              />
              <small className="ui-hint">
                OpenAI-kompatibel adress på den här datorn (<code>localhost</code>,
                {' '}<code>127.0.0.0/8</code> — till exempel en SSH-forward) eller en
                självhostad tjänst på ditt eget privata nät över https. Domännamn
                och publika adresser avvisas.
              </small>
            </label>
            <div className="setup-row">
              <label className="ui-field">
                <span>Modell</span>
                <input className="ui-input" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy} />
              </label>
              <label className="ui-field">
                <span>Etikett (valfri)</span>
                <input
                  className="ui-input"
                  placeholder="agenntserver"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  disabled={busy}
                />
              </label>
            </div>

            {probe && (
              <div className={probe.ok ? 'setup-probe ok' : 'setup-probe bad'}>
                {probe.ok ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                <span>{probe.detail}</span>
              </div>
            )}
            {error && <div className="setup-error"><AlertCircle size={15} /> {error}</div>}

            <div className="setup-actions">
              <button
                type="button"
                className="ui-btn ui-btn--outline ui-btn--lg"
                onClick={finish}
                disabled={busy}
              >
                Hoppa över
              </button>
              <button
                type="button"
                className="ui-btn ui-btn--primary ui-btn--lg"
                onClick={async () => {
                  const result = await saveModelRuntime();
                  if (result?.ok) finish();
                }}
                disabled={busy || !baseUrl.trim()}
              >
                {busy ? (<><Loader2 size={16} className="spin" /> Testar…</>) : 'Testa och fortsätt'}
              </button>
            </div>
            <p className="setup-note">
              Utan modelltjänst fungerar uppladdning, indexering och dokumentvisning
              som vanligt, men AI-chatten kan inte generera svar. Du kan ställa in
              adressen när som helst under Appinställningar.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="setup-screen">
      <div className="setup-panel">
        <Lockup />
        <h1 className="setup-title">Välkommen</h1>
        <p className="setup-subtitle">
          Den här datorn har ingen förening ännu. Skapa ditt administratörskonto
          och föreningen — allt sparas lokalt på den här datorn.
        </p>

        <form className="setup-form" onSubmit={submitAccount}>
          <label className="ui-field">
            <span>Föreningens namn</span>
            <input
              className="ui-input"
              autoFocus
              required
              placeholder="Brf Gjutformen 12"
              value={brfName}
              onChange={(e) => setBrfName(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="ui-field">
            <span>Ditt namn</span>
            <input
              className="ui-input"
              placeholder="Maria Andersson"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="ui-field">
            <span>E-postadress</span>
            <input
              className="ui-input"
              type="email"
              required
              autoComplete="username"
              placeholder="namn@forening.se"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={busy}
            />
          </label>
          <div className="setup-row">
            <label className="ui-field">
              <span>Lösenord</span>
              <input
                className="ui-input"
                type="password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
              />
              <small className={passwordTooShort ? 'ui-hint warn' : 'ui-hint'}>
                Minst {MIN_PASSWORD_LENGTH} tecken.
              </small>
            </label>
            <label className="ui-field">
              <span>Upprepa lösenord</span>
              <input
                className="ui-input"
                type="password"
                required
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                disabled={busy}
              />
              {passwordMismatch && <small className="ui-hint warn">Lösenorden är inte lika.</small>}
            </label>
          </div>

          {error && <div className="setup-error"><AlertCircle size={15} /> {error}</div>}

          <button
            type="submit"
            className="ui-btn ui-btn--primary ui-btn--lg"
            disabled={busy || passwordTooShort || passwordMismatch}
          >
            {busy ? (<><Loader2 size={16} className="spin" /> Skapar…</>) : 'Skapa förening'}
          </button>
        </form>

        {state?.storage?.dataDir && (
          <div className="setup-storage">
            <HardDrive size={14} />
            <span>Sparas i <code>{state.storage.dataDir}</code></span>
          </div>
        )}
      </div>
    </div>
  );
}

export default Setup;
