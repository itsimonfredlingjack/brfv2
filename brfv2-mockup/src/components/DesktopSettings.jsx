import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle, Archive, CheckCircle2, Cpu, HardDrive, Loader2, Plus, RotateCcw,
  Trash2, X,
} from 'lucide-react';
import { desktopApi } from '../api';
import './DesktopSettings.css';

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes)) return '';
  const units = ['B', 'kB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
};

const formatMoment = (iso) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString('sv-SE', { dateStyle: 'medium', timeStyle: 'short' });
};

/**
 * Operational surfaces that only exist for the installed application: which
 * model runtime it may talk to, local backups, additional associations, and
 * where the data actually lives.
 */
function DesktopSettings({ state, onClose, onStateChanged, onMembershipsChanged }) {
  const [baseUrl, setBaseUrl] = useState(state?.modelRuntime?.baseUrl || '');
  const [model, setModel] = useState(state?.modelRuntime?.model || 'gemma4:e12b');
  const [label, setLabel] = useState(state?.modelRuntime?.label || '');
  const [apiKey, setApiKey] = useState('');
  const [apiKeyTouched, setApiKeyTouched] = useState(false);
  const [savingModel, setSavingModel] = useState(false);
  const [probe, setProbe] = useState(null);

  const [backups, setBackups] = useState([]);
  const [backupDir, setBackupDir] = useState(state?.storage?.backupDir || '');
  const [backupBusy, setBackupBusy] = useState(false);
  const [pendingRestore, setPendingRestore] = useState(null);
  const [restoreStaged, setRestoreStaged] = useState(false);

  const [newBrf, setNewBrf] = useState('');
  const [brfBusy, setBrfBusy] = useState(false);

  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const refreshBackups = useCallback(async () => {
    try {
      const result = await desktopApi.listBackups();
      setBackups(result.backups);
      setBackupDir(result.backupDir);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { refreshBackups(); }, [refreshBackups]);

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const run = async (setBusy, action, successMessage) => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const result = await action();
      if (successMessage) setNotice(successMessage);
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const saveModelRuntime = () => run(setSavingModel, async () => {
    await desktopApi.putModelRuntime({
      baseUrl: baseUrl.trim(),
      model: model.trim(),
      label: label.trim(),
      // Untouched means "keep the stored token"; cleared means "remove it".
      apiKey: apiKeyTouched ? apiKey : null,
      timeoutS: state?.modelRuntime?.timeoutS ?? 300,
    });
    setApiKeyTouched(false);
    setApiKey('');
    const result = await desktopApi.testModelRuntime();
    setProbe(result);
    await onStateChanged();
    return result;
  }, 'Modelltjänsten sparad.');

  const createBackup = () => run(setBackupBusy, async () => {
    const created = await desktopApi.createBackup();
    await refreshBackups();
    return created;
  }, 'Säkerhetskopia skapad.');

  const removeBackup = (name) => run(setBackupBusy, async () => {
    await desktopApi.deleteBackup(name);
    await refreshBackups();
  }, 'Säkerhetskopian togs bort.');

  const stageRestore = (name) => run(setBackupBusy, async () => {
    await desktopApi.restoreBackup(name);
    setPendingRestore(null);
    setRestoreStaged(true);
  });

  const restartNow = () => run(setBackupBusy, async () => {
    await desktopApi.restart();
  });

  const addBrf = (event) => {
    event.preventDefault();
    return run(setBrfBusy, async () => {
      const created = await desktopApi.createBrf(newBrf.trim());
      setNewBrf('');
      onMembershipsChanged(created.memberships);
      await onStateChanged();
    }, 'Föreningen skapades.');
  };

  const runtime = state?.modelRuntime || {};
  // Changing the model service is an installation-level decision, so the form
  // is read-only for everyone else. The address stays visible: it is the
  // provenance shown next to every generated answer.
  const isInstallationAdmin = state?.installationAdmin === true;
  const modelLocked = savingModel || !isInstallationAdmin;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="desktop-settings glass-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="desktop-settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="ds-header">
          <h2 id="desktop-settings-title">Appinställningar</h2>
          <button type="button" className="ds-close" aria-label="Stäng" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        <div className="ds-body">
          {error && <div className="ds-banner bad"><AlertCircle size={15} /> {error}</div>}
          {notice && <div className="ds-banner ok"><CheckCircle2 size={15} /> {notice}</div>}

          <section className="ds-section">
            <h3><Cpu size={15} /> Modelltjänst</h3>
            <p className="ds-hint">
              Den enda tjänst applikationen kontaktar utanför datorn. Lämnas
              adressen tom kan AI-chatten inte generera svar — inget annat
              försök görs mot någon extern leverantör.
            </p>
            <p className="ds-hint">
              Tillåtna adresser: <code>localhost</code> och <code>127.0.0.0/8</code>
              {' '}(http eller https), eller en självhostad tjänst på eget nät —
              {' '}<code>10.0.0.0/8</code>, <code>172.16.0.0/12</code>,
              {' '}<code>192.168.0.0/16</code>, <code>fc00::/7</code> — och då bara
              över https. Domännamn och publika adresser avvisas.
            </p>
            {!isInstallationAdmin && (
              <div className="ds-banner warn" role="note">
                <AlertCircle size={15} />
                <span>
                  Modelltjänsten ändras bara av installationsadministratören —
                  kontot som konfigurerade den här datorn.
                </span>
              </div>
            )}
            <div className="ds-grid">
              <label className="ds-field ds-span">
                <span>Adress</span>
                <input
                  type="url"
                  placeholder="http://127.0.0.1:8000/v1"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  disabled={modelLocked}
                />
              </label>
              <label className="ds-field">
                <span>Modell</span>
                <input value={model} onChange={(e) => setModel(e.target.value)} disabled={modelLocked} />
              </label>
              <label className="ds-field">
                <span>Etikett</span>
                <input
                  placeholder="agenntserver"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  disabled={modelLocked}
                />
              </label>
              <label className="ds-field ds-span">
                <span>Åtkomsttoken (valfri)</span>
                <input
                  type="password"
                  placeholder={runtime.hasApiKey ? '•••••••• (sparad)' : 'Ingen token'}
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setApiKeyTouched(true); }}
                  disabled={modelLocked}
                />
                <small>Sparas bara på den här datorn och visas aldrig igen.</small>
              </label>
            </div>

            {probe && (
              <div className={probe.ok ? 'ds-banner ok' : 'ds-banner bad'}>
                {probe.ok ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                <span>
                  {probe.detail}
                  {probe.ok && probe.served?.length > 0 && ` Serverar: ${probe.served.join(', ')}`}
                </span>
              </div>
            )}

            <div className="ds-actions">
              <span className={`ds-state ${runtime.ready ? 'ok' : 'warn'}`}>
                {runtime.ready ? 'Konfigurerad' : 'Ingen modelltjänst konfigurerad'}
              </span>
              <button type="button" className="ds-primary" onClick={saveModelRuntime} disabled={modelLocked}>
                {savingModel ? (<><Loader2 size={15} className="spin" /> Sparar…</>) : 'Spara och testa'}
              </button>
            </div>
          </section>

          <section className="ds-section">
            <h3><Archive size={15} /> Säkerhetskopior</h3>
            <p className="ds-hint">
              En säkerhetskopia innehåller alla föreningar, dokument, index och
              konton. Filerna ligger i <code>{backupDir}</code> — kopiera dem
              till en annan disk för att skydda mot hårdvarufel.
            </p>

            {restoreStaged ? (
              <div className="ds-banner ok">
                <CheckCircle2 size={15} />
                <span>
                  Återställningen är förberedd och genomförs vid nästa start, innan
                  någon databas öppnas.
                </span>
              </div>
            ) : null}

            <div className="ds-actions">
              <button type="button" className="ds-primary" onClick={createBackup} disabled={backupBusy}>
                {backupBusy ? (<><Loader2 size={15} className="spin" /> Arbetar…</>) : 'Skapa säkerhetskopia nu'}
              </button>
              {restoreStaged && state?.restartSupported && (
                <button type="button" className="ds-secondary" onClick={restartNow} disabled={backupBusy}>
                  <RotateCcw size={15} /> Starta om nu
                </button>
              )}
            </div>

            {backups.length === 0 ? (
              <p className="ds-empty">Inga säkerhetskopior ännu.</p>
            ) : (
              <ul className="ds-backups">
                {backups.map((backup) => (
                  <li key={backup.name}>
                    <div className="ds-backup-meta">
                      <strong>{formatMoment(backup.createdAt)}</strong>
                      <span>{formatBytes(backup.bytes)} · {backup.name}</span>
                    </div>
                    <div className="ds-backup-actions">
                      <button
                        type="button"
                        onClick={() => setPendingRestore(backup)}
                        disabled={backupBusy}
                      >
                        <RotateCcw size={14} /> Återställ
                      </button>
                      <button
                        type="button"
                        className="danger"
                        aria-label={`Ta bort ${backup.name}`}
                        onClick={() => removeBackup(backup.name)}
                        disabled={backupBusy}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {pendingRestore && (
              <div className="ds-confirm" role="alertdialog" aria-label="Bekräfta återställning">
                <p>
                  Återställ från <strong>{formatMoment(pendingRestore.createdAt)}</strong>?
                  Allt som lagts till efter den tidpunkten försvinner. Bytet sker
                  vid nästa start.
                </p>
                <div className="ds-actions">
                  <button type="button" className="ds-secondary" onClick={() => setPendingRestore(null)}>
                    Avbryt
                  </button>
                  <button
                    type="button"
                    className="ds-primary danger"
                    onClick={() => stageRestore(pendingRestore.name)}
                    disabled={backupBusy}
                  >
                    Ja, återställ
                  </button>
                </div>
              </div>
            )}
          </section>

          <section className="ds-section">
            <h3><Plus size={15} /> Ny förening</h3>
            <p className="ds-hint">
              Varje förening får ett eget, helt separat dokumentarkiv och index.
            </p>
            <form className="ds-inline-form" onSubmit={addBrf}>
              <input
                placeholder="Brf Sjöutsikten 7"
                value={newBrf}
                onChange={(e) => setNewBrf(e.target.value)}
                disabled={brfBusy}
                aria-label="Föreningens namn"
              />
              <button type="submit" className="ds-primary" disabled={brfBusy || newBrf.trim().length < 2}>
                {brfBusy ? (<><Loader2 size={15} className="spin" /> Skapar…</>) : 'Lägg till'}
              </button>
            </form>
          </section>

          <section className="ds-section">
            <h3><HardDrive size={15} /> Lagring och version</h3>
            <dl className="ds-facts">
              <dt>Data</dt>
              <dd><code>{state?.storage?.dataDir}</code></dd>
              <dt>Säkerhetskopior</dt>
              <dd><code>{state?.storage?.backupDir}</code></dd>
              <dt>Textextrahering (OCR)</dt>
              <dd>{state?.ocr?.available
                ? `tesseract med svenskt språkstöd är installerat`
                : 'tesseract med svenskt språkstöd saknas — inlästa PDF:er kan inte tolkas'}</dd>
              <dt>Sökvektorer</dt>
              <dd>{state?.embedding?.provider}</dd>
              <dt>Version</dt>
              <dd>{state?.app?.name} {state?.app?.version}</dd>
              {state?.lastRestore && (
                <>
                  <dt>Senaste återställning</dt>
                  <dd>
                    {state.lastRestore.status === 'restored'
                      ? `Genomförd ${formatMoment(state.lastRestore.at)}`
                      : `Misslyckades ${formatMoment(state.lastRestore.at)}: ${state.lastRestore.detail}`}
                  </dd>
                </>
              )}
            </dl>
          </section>
        </div>
      </div>
    </div>
  );
}

export default DesktopSettings;
