import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatMessageList from './ChatMessageList';
import { buildAnswerMessage, buildErrorMessage } from '../chatResponseMapping';

// Render-path proof for cleanup-global-constraints.md #1: no citation/source
// may render unless it came 1:1 from the real api.ask() AskResponse.
//
// Seam: rather than mocking fetch and mounting the whole <App> (blocked by
// auth gating + pdf.js — see cleanup-task-1-report.md), each test builds an
// AskResponse-shaped fixture exactly as api.ask() would return it, runs it
// through the *real* chatResponseMapping functions App.jsx's askQuestion
// uses (not a reimplementation), and renders the *real* extracted
// <ChatMessageList>. This exercises the same response -> message -> DOM
// chain the live app runs, end to end, without needing to fake HTTP.

describe('ChatMessageList render path', () => {
  it('(a) a refusal response with zero citations renders zero chips and no source metadata', () => {
    const askResponse = {
      answer: 'Jag kan tyvärr inte svara på det utifrån de verifierade källorna.',
      citations: [],
      rejected_citations: [],
      refusal: true,
      warning: null,
    };
    const messages = [buildAnswerMessage(askResponse)];

    const { container } = render(
      <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
    );

    expect(screen.getByText('Avstår från att svara')).toBeInTheDocument();
    expect(screen.getByText(askResponse.answer)).toBeInTheDocument();
    expect(container.querySelectorAll('.citation-chip')).toHaveLength(0);
    expect(container.querySelector('.chat-citations')).toBeNull();
  });

  it('(b) a response with N citations renders exactly N chips matching the response fields verbatim', () => {
    const askResponse = {
      answer: 'Enligt stadgarna gäller följande.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning kräver styrelsens samtycke.', chunk_id: 'hash-real-1', rects: [[10, 20, 30, 40]], score: 0.81 },
        { document_name: 'Årsredovisning 2024.pdf', page: 12, quote: 'Föreningens resultat uppgick till...', chunk_id: 'hash-real-2', rects: [[5, 6, 7, 8]], score: 0.74 },
      ],
      rejected_citations: [],
      refusal: false,
      warning: null,
    };
    const openDocViewer = vi.fn();
    const messages = [buildAnswerMessage(askResponse)];

    const { container } = render(
      <ChatMessageList messages={messages} userInitials="AB" openDocViewer={openDocViewer} />
    );

    const chips = container.querySelectorAll('.citation-chip');
    expect(chips).toHaveLength(askResponse.citations.length);

    askResponse.citations.forEach((c, i) => {
      expect(chips[i].textContent).toContain(c.document_name);
      expect(chips[i].textContent).toContain(`s.${c.page}`);
      expect(chips[i].getAttribute('title')).toBe(`"${c.quote}"`);
    });

    // Clicking a chip must hand back the exact citation object from the
    // response — proves the click path can't substitute fabricated page/rects.
    chips[0].click();
    expect(openDocViewer).toHaveBeenCalledWith(askResponse.citations[0], {
      page: askResponse.citations[0].page,
      rects: askResponse.citations[0].rects,
      highlightPage: askResponse.citations[0].page,
    });
  });

  it('(c) an api.ask network error renders the error state with zero citations', () => {
    const networkError = new Error('Failed to fetch');
    const messages = [buildErrorMessage(networkError)];

    const { container } = render(
      <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
    );

    expect(screen.getByText('Tekniskt fel: Failed to fetch')).toBeInTheDocument();
    expect(screen.getByText('Avstår från att svara')).toBeInTheDocument();
    expect(container.querySelectorAll('.citation-chip')).toHaveLength(0);
  });
});
