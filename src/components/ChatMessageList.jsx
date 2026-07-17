import React from 'react';
import { Loader2, Sparkles, FileText, AlertCircle, Info } from 'lucide-react';
import { parseCitationMarkers } from '../citationMarkers';

// Pure rendering of the chat message list — extracted verbatim from
// App.jsx's inline chat tab markup (cleanup/verified-ui Task 1) so the
// render path can be tested in isolation. Receives `messages` built
// exclusively from api.ask() responses via chatResponseMapping.js and
// renders citation chips 1:1 from message.citations — it never invents,
// reorders, or defaults citation data of its own
// (cleanup-global-constraints.md #1-2).
//
// Inline [K<n>]/[<n>] markers (cleanup/verified-ui Task 2, salvaging the
// concept from .superpowers/quarantine/INVENTORY.md §3(b)): parseCitationMarkers
// linkifies ONLY tokens already present in msg.content that map to a real
// entry in msg.citations; unmatched tokens and answers with no markers at
// all render exactly as returned — nothing is injected.
//
// Near-matches on refusal (cleanup/verified-ui Task 3, salvaging the concept
// from .superpowers/quarantine/INVENTORY.md §3(c) while dropping its
// fabrications): when the backend refuses AND AskResponse.retrieval is
// non-empty, shows the real RetrievalHit fields (document_name, page,
// score, text — backend/app/schemas.py) as "found but not used" evidence.
// No invented relevance label ("Mest relevant"), no search count — those
// were the quarantined stash's fabrications. Gated on msg.refusal, not just
// retrieval.length, because AskResponse.retrieval is populated on every
// path including successful answers (backend/app/answer.py) — a normal
// answer must never show near-matches. Opens via openDocViewer with only
// { page }, no rects: retrieval hits carry no verified on-page geometry, so
// passing none is the honest state (cleanup-global-constraints.md #2).
function ChatMessageList({ messages, userInitials, openDocViewer }) {
  return (
    <div className="chat-messages-area">
      {messages.map((msg, idx) => (
        <div key={idx} className={`chat-message ${msg.role} ${msg.refusal ? 'refusal' : ''} ${msg.pending ? 'pending' : ''}`}>
          <div className="chat-avatar">
            {msg.role === 'ai' ? (msg.pending ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />) : userInitials}
          </div>
          <div className="chat-content">
            {msg.refusal && <div className="chat-refusal-tag"><AlertCircle size={13} /> Avstår från att svara</div>}
            <span className="chat-answer-text">
              {parseCitationMarkers(msg.content, msg.citations).map((seg, i) => seg.type === 'marker' ? (
                <button
                  key={i}
                  className="inline-citation"
                  title={seg.citation.document_name}
                  onClick={() => openDocViewer(seg.citation, { page: seg.citation.page, rects: seg.citation.rects, highlightPage: seg.citation.page })}
                >
                  {seg.text}
                </button>
              ) : (
                <span key={i}>{seg.text}</span>
              ))}
            </span>
            {msg.warning && <div className="chat-warning"><AlertCircle size={13} /> {msg.warning}</div>}
            {msg.citations?.length > 0 && (
              <div className="chat-citations">
                {msg.citations.map((c, i) => (
                  <button
                    key={i}
                    className="citation-chip"
                    title={`"${c.quote}"`}
                    onClick={() => openDocViewer(c, { page: c.page, rects: c.rects, highlightPage: c.page })}
                  >
                    <FileText size={12} />
                    {c.document_name} · s.{c.page}
                  </button>
                ))}
              </div>
            )}
            {msg.rejected?.length > 0 && (
              <div className="chat-warning">
                <AlertCircle size={13} /> {msg.rejected.length} källhänvisning(ar) kunde inte verifieras mot dokumenten och visas inte.
              </div>
            )}
            {msg.refusal && msg.retrieval?.length > 0 && (
              <div className="near-matches-section">
                <div className="near-matches-header">
                  <Info size={13} /> Hittade avsnitt — räckte inte för ett säkert svar
                </div>
                <p className="near-matches-caption">Dessa avsnitt är inte använda för svaret.</p>
                <div className="near-matches-list">
                  {msg.retrieval.map((hit, i) => (
                    <button
                      key={i}
                      className="near-match-card"
                      onClick={() => openDocViewer(hit, { page: hit.page })}
                    >
                      <span className="near-match-title" title={hit.document_name}>{hit.document_name} · s.{hit.page}</span>
                      <span className="near-match-score">Poäng: {hit.score}</span>
                      <span className="near-match-text">{hit.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ChatMessageList;
