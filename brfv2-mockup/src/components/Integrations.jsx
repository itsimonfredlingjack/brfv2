import React, { useCallback, useEffect, useState } from 'react';
import { Inbox, Loader2, Plug, RefreshCw, X } from 'lucide-react';
import { integrationsApi } from '../api';
import IntegrationConnections from './IntegrationConnections';
import IntakeQueue from './IntakeQueue';
import './Integrations.css';

/**
 * Inkommande — the board's review queue for material that has arrived, and the
 * connections it may arrive through.
 *
 * Two panes, one rule across them: nothing on this screen presents a system
 * proposal as an established fact, and nothing leaves it without a person.
 *
 * The invoice review used to live here as a third pane. It does not any more:
 * an invoice is worked for weeks after the post it arrived with has been dealt
 * with, so it is its own product area (**Fakturor**). What did not change is
 * that a message read out of a connected mailbox goes through the same format
 * check, the same hash, the same duplicate rule and the same queue as a file
 * somebody picked by hand — and neither is evidence until a person says so.
 */

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`integrations-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

export default function Integrations({ brfId, isAdmin = false, onOpenDocument, onDocumentsChanged }) {
  const [pane, setPane] = useState('inbox');

  const [events, setEvents] = useState([]);
  const [format, setFormat] = useState(null);
  const [connections, setConnections] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      const [e, fmt, conns] = await Promise.all([
        integrationsApi.listSourceEvents(brfId),
        integrationsApi.format(brfId),
        integrationsApi.connections(brfId),
      ]);
      setEvents(e);
      setFormat(fmt);
      setConnections(conns);
      setError('');
    } catch (err) {
      setError(err.message || 'Kunde inte hämta integrationsdata.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  const graph = connections?.['microsoft-graph'];
  const mailboxReady = graph?.connection?.status === 'connected';
  const openEvents = events.filter((e) => e.review_status === 'open').length;

  return (
    <div className="integrations">
      <div className="integrations-header">
        <div className="integrations-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'inbox'}
            className={pane === 'inbox' ? 'active' : ''}
            onClick={() => setPane('inbox')}
          >
            <Inbox size={16} /> Inkommande
            {openEvents > 0 && <span className="pill">{openEvents}</span>}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'connections'}
            className={pane === 'connections' ? 'active' : ''}
            onClick={() => setPane('connections')}
          >
            <Plug size={16} /> Anslutningar
          </button>
        </div>
        <button type="button" className="refresh" onClick={refresh} disabled={loading}>
          <RefreshCw size={15} /> Uppdatera
        </button>
      </div>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {loading && (
        <p className="integrations-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>
      )}

      {pane === 'inbox' && !loading && (
        <section className="pane">
          {/* The queue is its own component: it owns its own reads, its own
              filters and its own outcomes. What it does NOT own is anything
              downstream — preserving a message, adopting an attachment,
              creating work and putting a date on the board all land in the
              domains that already have them. */}
          <IntakeQueue
            brfId={brfId}
            isAdmin={isAdmin}
            mailboxConnected={mailboxReady}
            format={format}
            onOpenDocument={onOpenDocument}
            onChanged={() => { refresh(); onDocumentsChanged?.(); }}
          />
        </section>
      )}

      {pane === 'connections' && !loading && connections && (
        <section className="pane">
          <IntegrationConnections
            brfId={brfId}
            connections={connections}
            mailFolders={format?.mailFolders}
            onChanged={() => { setNotice(''); refresh(); }}
          />
        </section>
      )}
    </div>
  );
}
