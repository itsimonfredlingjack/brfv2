import { describe, it, expect } from 'vitest';
import { buildAnswerMessage, buildErrorMessage, latestCitations } from './chatResponseMapping';

// Proves the mapping between api.ask()'s AskResponse and the rendered chat
// message copies fields 1:1 and invents nothing (cleanup-global-constraints
// #1). ChatMessageList.test.jsx composes these same functions with
// <ChatMessageList> to prove the full response -> render pipeline.

describe('buildAnswerMessage', () => {
  it('passes citations through verbatim without adding or dropping fields', () => {
    const resp = {
      answer: 'Enligt stadgarna §12 gäller andrahandsuthyrning i max ett år.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning...', chunk_id: 'a1b2c3', rects: [[1, 2, 3, 4]], score: 0.81 },
      ],
      rejected_citations: [],
      refusal: false,
      warning: null,
    };

    expect(buildAnswerMessage(resp)).toEqual({
      role: 'ai',
      content: resp.answer,
      citations: resp.citations,
      rejected: [],
      refusal: false,
      warning: null,
      retrieval: [],
    });
  });

  it('defaults citations/rejected/retrieval to empty arrays, never a placeholder value, when absent', () => {
    const resp = { answer: 'Jag kan inte svara utifrån de verifierade källorna.', refusal: true };

    expect(buildAnswerMessage(resp)).toEqual({
      role: 'ai',
      content: resp.answer,
      citations: [],
      rejected: [],
      refusal: true,
      warning: undefined,
      retrieval: [],
    });
  });

  it('passes retrieval hits through verbatim (Task 3: feeds the near-matches no-answer state)', () => {
    const resp = {
      answer: 'Jag hittar inget i de uppladdade dokumenten som verkar besvara den frågan.',
      refusal: true,
      refusal_reason: 'low_relevance',
      retrieval: [
        { chunk_id: 'c1', score: 0.42, confidence: 0.3, bm25: 0.5, dense: 0.35, document_id: 'd1', document_name: 'Stadgar.pdf', page: 7, text: 'Föreningen ansvarar för...' },
      ],
    };

    expect(buildAnswerMessage(resp)).toEqual({
      role: 'ai',
      content: resp.answer,
      citations: [],
      rejected: [],
      refusal: true,
      warning: undefined,
      retrieval: resp.retrieval,
    });
  });
});

describe('buildErrorMessage', () => {
  it('renders a technical-error refusal with zero citations, carrying only the error message text', () => {
    const error = new Error('Failed to fetch');

    const msg = buildErrorMessage(error);

    expect(msg).toEqual({ role: 'ai', content: 'Tekniskt fel: Failed to fetch', refusal: true });
    expect(msg.citations).toBeUndefined();
  });
});

describe('latestCitations', () => {
  // Feeds the dual-pane source panel (cleanup/verified-ui Task 2): the panel
  // tracks the most recent *completed* AI message's verified citations[],
  // never anything invented — see cleanup-global-constraints.md #1.

  it('returns the citations of the most recent completed ai message', () => {
    const messages = [
      { role: 'ai', content: 'Hej!' },
      { role: 'user', content: 'Fråga 1' },
      buildAnswerMessage({ answer: 'Svar 1', citations: [{ document_name: 'A.pdf', page: 1, quote: 'a' }] }),
      { role: 'user', content: 'Fråga 2' },
      buildAnswerMessage({ answer: 'Svar 2', citations: [{ document_name: 'B.pdf', page: 2, quote: 'b' }] }),
    ];

    expect(latestCitations(messages)).toEqual([{ document_name: 'B.pdf', page: 2, quote: 'b' }]);
  });

  it('skips a trailing pending message and uses the last completed one instead', () => {
    const messages = [
      buildAnswerMessage({ answer: 'Svar 1', citations: [{ document_name: 'A.pdf', page: 1, quote: 'a' }] }),
      { role: 'user', content: 'Fråga 2' },
      { role: 'ai', pending: true, content: 'Söker i dokumenten…' },
    ];

    expect(latestCitations(messages)).toEqual([{ document_name: 'A.pdf', page: 1, quote: 'a' }]);
  });

  it('returns an empty array (never a placeholder) when there is no completed ai message yet', () => {
    expect(latestCitations([{ role: 'user', content: 'Fråga' }])).toEqual([]);
    expect(latestCitations([])).toEqual([]);
  });

  it('returns an empty array when the latest completed ai message has no citations (refusal)', () => {
    const messages = [buildAnswerMessage({ answer: 'Nej.', refusal: true })];

    expect(latestCitations(messages)).toEqual([]);
  });
});
