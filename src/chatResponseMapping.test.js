import { describe, it, expect } from 'vitest';
import { buildAnswerMessage, buildErrorMessage } from './chatResponseMapping';

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
    });
  });

  it('defaults citations/rejected to empty arrays, never a placeholder value, when absent', () => {
    const resp = { answer: 'Jag kan inte svara utifrån de verifierade källorna.', refusal: true };

    expect(buildAnswerMessage(resp)).toEqual({
      role: 'ai',
      content: resp.answer,
      citations: [],
      rejected: [],
      refusal: true,
      warning: undefined,
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
