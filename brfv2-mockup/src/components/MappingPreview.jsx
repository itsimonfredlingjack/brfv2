import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Search } from 'lucide-react';
import { integrationsApi } from '../api';
import './MappingPreview.css';

/**
 * Which field in the accounting system became which of ours, with both values
 * side by side.
 *
 * This is the screen a first live connection is verified on, and it is meant to
 * be read next to the invoice as it looks in Fortnox. "Beloppen såg rätt ut" is
 * not a check; comparing a named source field against a named target field, row
 * by row, is. A field the mapping could not fill is shown as loudly as one it
 * could — an empty column is exactly the thing a summary would hide.
 */

const OBSERVED_LABEL = {
  Booked: 'Bokförd',
  Cancelled: 'Annullerad',
  Balance: 'Kvar att betala',
  VoucherNumber: 'Verifikationsnummer',
  VoucherSeries: 'Verifikationsserie',
  VoucherYear: 'Verifikationsår',
};

const observedValue = (value) => {
  if (value === true) return 'ja';
  if (value === false) return 'nej';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
};

export default function MappingPreview({ brfId, initialRef = '' }) {
  const [externalRef, setExternalRef] = useState(initialRef);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function load(ref) {
    const wanted = (ref ?? externalRef).trim();
    if (!wanted) return;
    setBusy(true);
    setError('');
    try {
      setPreview(await integrationsApi.mappingPreview(brfId, wanted));
    } catch (err) {
      setPreview(null);
      setError(err.message || 'Fältmappningen kunde inte hämtas.');
    } finally {
      setBusy(false);
    }
  }

  const observed = Object.entries(preview?.observedNotChanged || {});
  const rowLabels = preview?.rows?.[0]?.map((cell) => cell.label) || [];

  return (
    <div className="mp">
      <div className="pane-intro">
        <p>
          Varje fält nedan är en översättning: ett fält i ekonomisystemet har
          blivit ett fält hos oss. Läs tabellen bredvid fakturan som den ser ut i
          Fortnox och kontrollera värde för värde. Det behöver göras en gång per
          installation — efter det är mappningen kontrollerad i stället för
          antagen.
        </p>
        <div className="mp-lookup">
          <label className="mp-field">
            <span>Fakturans dokumentnummer i Fortnox</span>
            <input
              value={externalRef}
              onChange={(e) => setExternalRef(e.target.value)}
              placeholder="1042"
              onKeyDown={(e) => { if (e.key === 'Enter') load(); }}
            />
          </label>
          <button type="button" disabled={busy || !externalRef.trim()} onClick={() => load()}>
            {busy ? <Loader2 size={15} className="spin" /> : <Search size={15} />} Hämta fältmappning
          </button>
        </div>
      </div>

      {error && <div className="integrations-banner error" role="alert"><span>{error}</span></div>}

      {preview && (
        <section className="mp-result">
          <header className="mp-result-head">
            <h4>Faktura {preview.externalRef} · {preview.adapter}</h4>
          </header>

          <p className="mp-note">{preview.note}</p>

          <h5>Fält</h5>
          <table className="mp-fields">
            <thead>
              <tr>
                <th>Vårt fält</th>
                <th>Fält i Fortnox</th>
                <th>Värde vi läste</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {preview.fields.map((field) => (
                <tr key={field.target} className={field.matched ? 'matched' : 'unmatched'}>
                  <td>
                    {field.label}
                    {/* A field the source simply does not have is labelled with
                        its own name; repeating it under itself says nothing. */}
                    {field.target !== field.label && (
                      <span className="mp-target"><code>{field.target}</code></span>
                    )}
                  </td>
                  <td>{field.sourceField ? <code>{field.sourceField}</code> : '—'}</td>
                  <td className="mp-value">{field.value ?? '—'}</td>
                  <td>
                    {field.matched ? (
                      <span className="mp-flag ok"><CheckCircle2 size={13} /> läst</span>
                    ) : (
                      <span className="mp-flag missing"><AlertTriangle size={13} /> inget värde</span>
                    )}
                    {field.note && <span className="mp-fieldnote">{field.note}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h5>Rader</h5>
          {preview.rows.length === 0 ? (
            <p className="muted">Fakturan har inga rader i källan.</p>
          ) : (
            <table className="mp-rows">
              <thead>
                <tr>
                  <th>#</th>
                  {rowLabels.map((label) => <th key={label}>{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, index) => (
                  <tr key={index}>
                    <td>{index + 1}</td>
                    {row.map((cell) => (
                      <td key={cell.target}>
                        <span className="mp-value">{cell.value ?? '—'}</span>
                        <span className="mp-source">ur <code>{cell.sourceField}</code></span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h5>Läses och visas — ändras aldrig</h5>
          {observed.length === 0 ? (
            <p className="muted">Fakturan bär ingen bokföringsstatus i källan.</p>
          ) : (
            <dl className="mp-observed">
              {observed.map(([key, value]) => (
                <div key={key}>
                  <dt>{OBSERVED_LABEL[key] || key}</dt>
                  <dd>{observedValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      )}
    </div>
  );
}
