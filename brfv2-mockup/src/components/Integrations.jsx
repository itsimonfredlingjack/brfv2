import React, { useCallback, useEffect, useState } from 'react';
import { Inbox, Loader2, Plug, RefreshCw, X } from 'lucide-react';
import { integrationsApi } from '../api';
import IntegrationConnections from './IntegrationConnections';
import IntakeQueue from './IntakeQueue';
import Instrument from './Instrument';
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
  // Bumped by the band's Uppdatera; the queue watches it and reloads itself.
  const [reload, setReload] = useState(0);

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
  const awaitingEvents = events.filter((e) => e.awaiting_reply).length;
  // Three counts taken from an array the fetch has not filled are three
  // fabrications. While it is loading the band is told so and keeps its row.
  const matt = loading ? {} : {
    avgora: openEvents, vantar: awaitingEvents, inkommet: events.length,
  };

  return (
    <div className="integrations">
      <div className="integrations-header page-header">
        {/* The two panes used to be tabs sitting where the title goes, both at
            masthead scale, one grey and one ink. Read left to right at 44px
            that is "Inkommande Anslutningar" — a headline with a word missing
            from it, and the only workspace in the product whose title was not
            its name. They are also not peers: Inkommande is the work, and
            Anslutningar is the setup behind it.

            So the band states which screen you are on, in its own name, and
            the way across is a control in the actions row — the same shape and
            the same place as every other band's secondary control. */}
        <div className="integrations-header-text">
          <h2 className="page-title">{pane === 'inbox' ? 'Inkommande' : 'Anslutningar'}</h2>
          <p className="page-header-sub">
            {pane === 'inbox'
              ? 'Post som kommit in, innan någon tagit ställning.'
              : 'Brevlådor och system Träff läser ifrån.'}
          </p>
        </div>
        {/* Uppdatera belongs here, where it is on every other screen.
            It used to sit inside the queue's own filter row — the same word,
            the same glyph, the same job, in the one place on the screen a
            reader would not look for it, because Uppgifter and Bevakningar
            both put it top right. A verb that moves between screens has to be
            relearned on each of them.
            So the band asks for the reload and the queue answers: `reload` is
            a counter the queue watches. The alternative was hoisting the
            queue's fetches up here, which would have moved five state hooks
            out of the component that uses them to satisfy a layout. */}
        <div className="page-header-actions">
          {pane === 'connections' ? (
            <>
              <button type="button" className="refresh" onClick={refresh} disabled={loading}>
                <RefreshCw size={15} /> Uppdatera
              </button>
              <button type="button" onClick={() => setPane('inbox')}>
                <Inbox size={15} /> Inkommande
                {openEvents > 0 && <span className="tab-count">{openEvents}</span>}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="refresh"
                onClick={() => { refresh(); setReload((n) => n + 1); }}
                disabled={loading}
              >
                <RefreshCw size={15} /> Uppdatera
              </button>
              <button type="button" onClick={() => setPane('connections')}>
                <Plug size={15} /> Anslutningar
              </button>
            </>
          )}
        </div>

        {/* Inkommande's instrument is the queue's own standing: what is waiting
            for a decision, what has been answered and is waiting on someone
            else, and how much has come in altogether. */}
        {pane === 'inbox' && (
          <Instrument
            label="Att avgöra"
            value={matt.avgora}
            readings={[
              { label: 'Väntar svar', value: matt.vantar },
              { label: 'Inkommet', value: matt.inkommet },
            ]}
          />
        )}
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
            reload={reload}
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
