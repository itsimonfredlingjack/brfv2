import React from 'react';
import { Loader2, Sparkles, FileText, AlertCircle } from 'lucide-react';
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
          </div>
        </div>
      ))}
    </div>
  );
}

export default ChatMessageList;
