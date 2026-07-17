// Pure mappers between the backend's AskResponse (src/api.js `api.ask`) and
// the chat UI's message shape. Extracted verbatim from App.jsx's askQuestion
// (cleanup/verified-ui Task 1) so the render-path tests can drive the exact
// mapping the live chat flow uses, without mocking fetch or mounting the
// whole app (which has auth gating and pdf.js dependencies).
//
// Invariant (cleanup-global-constraints.md #1): every field here is copied
// 1:1 from the verified AskResponse; nothing is invented, and citations/
// rejected default to an empty array rather than any placeholder content.

// Builds the rendered "ai" message from a successful api.ask() response.
export function buildAnswerMessage(resp) {
  return {
    role: 'ai',
    content: resp.answer,
    citations: resp.citations || [],
    rejected: resp.rejected_citations || [],
    refusal: resp.refusal,
    warning: resp.warning,
  };
}

// Builds the rendered "ai" message for an api.ask() failure (network/HTTP
// error that isn't a 401 session expiry, which App.jsx handles separately
// via handleApiError).
export function buildErrorMessage(error) {
  return { role: 'ai', content: `Tekniskt fel: ${error.message}`, refusal: true };
}

// Finds the source panel's current citations (cleanup/verified-ui Task 2):
// the most recent *completed* ai message's citations[], skipping any
// trailing pending placeholder. Design choice — the panel tracks the
// latest verified response rather than accumulating every message's
// citations, matching how the salvaged dual-pane concept in
// .superpowers/quarantine/INVENTORY.md §3(a) reads `lastAiMessage.citations`.
export function latestCitations(messages) {
  const lastAi = [...messages].reverse().find((m) => m.role === 'ai' && !m.pending);
  return lastAi?.citations || [];
}
