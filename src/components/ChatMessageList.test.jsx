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

  it('(d) [<n>] tokens already present in the answer that map to a citation render as clickable inline markers', () => {
    const askResponse = {
      answer: 'Enligt [1] gäller detta, se även [2] för mer.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'q1', chunk_id: 'hash-1', rects: [[1, 2, 3, 4]], score: 0.81 },
        { document_name: 'B.pdf', page: 9, quote: 'q2', chunk_id: 'hash-2', rects: [[5, 6, 7, 8]], score: 0.5 },
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

    const markers = container.querySelectorAll('.inline-citation');
    expect(markers).toHaveLength(2);
    expect(markers[0].textContent).toBe('[1]');
    expect(markers[1].textContent).toBe('[2]');
    // The surrounding plain text must render exactly as returned, unmodified.
    expect(container.querySelector('.chat-answer-text').textContent).toBe(askResponse.answer);

    // Clicking the marker opens the exact citation it maps to — verbatim page/rects.
    markers[1].click();
    expect(openDocViewer).toHaveBeenCalledWith(askResponse.citations[1], {
      page: askResponse.citations[1].page,
      rects: askResponse.citations[1].rects,
      highlightPage: askResponse.citations[1].page,
    });
  });

  it('(e) an answer with no bracket tokens gets zero injected inline markers', () => {
    const askResponse = {
      answer: 'Enligt stadgarna gäller följande utan några referenser.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'q1', chunk_id: 'hash-1', rects: [[1, 2, 3, 4]], score: 0.81 },
      ],
      rejected_citations: [],
      refusal: false,
      warning: null,
    };
    const messages = [buildAnswerMessage(askResponse)];

    const { container } = render(
      <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
    );

    expect(container.querySelectorAll('.inline-citation')).toHaveLength(0);
    expect(screen.getByText(askResponse.answer)).toBeInTheDocument();
  });

  it('(f) a bracket token with no matching citation index stays plain text, not a marker', () => {
    const askResponse = {
      answer: 'Se [9] för mer information.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'q1', chunk_id: 'hash-1', rects: [[1, 2, 3, 4]], score: 0.81 },
      ],
      rejected_citations: [],
      refusal: false,
      warning: null,
    };
    const messages = [buildAnswerMessage(askResponse)];

    const { container } = render(
      <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
    );

    expect(container.querySelectorAll('.inline-citation')).toHaveLength(0);
    expect(container.querySelector('.chat-answer-text').textContent).toBe(askResponse.answer);
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

  // cleanup-task-3-brief.md: considered no-answer state with real near-matches.
  // Fixtures use exactly the backend/app/schemas.py RetrievalHit fields
  // (chunk_id, score, confidence, bm25, dense, document_id, document_name,
  // page, text) — no invented relevance label, no search count.
  describe('(g) near-matches (Task 3)', () => {
    const retrievalHits = [
      { chunk_id: 'c1', score: 0.42, confidence: 0.3, bm25: 0.5, dense: 0.35, document_id: 'd1', document_name: 'Stadgar.pdf', page: 7, text: 'Föreningen ansvarar för yttre underhåll av fastigheten.' },
      { chunk_id: 'c2', score: 0.31, confidence: 0.22, bm25: 0.4, dense: 0.2, document_id: 'd2', document_name: 'Årsredovisning 2024.pdf', page: 3, text: 'Styrelsen föreslår ingen förändring av avgiften.' },
    ];

    it('a refusal with real retrieval hits renders a labeled near-matches section with exactly the hits\' fields', () => {
      const askResponse = {
        answer: 'Jag hittar inget i de uppladdade dokumenten som verkar besvara den frågan.',
        citations: [],
        rejected_citations: [],
        refusal: true,
        warning: null,
        retrieval: retrievalHits,
      };
      const messages = [buildAnswerMessage(askResponse)];

      const { container } = render(
        <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
      );

      const section = container.querySelector('.near-matches-section');
      expect(section).not.toBeNull();
      expect(section.textContent).toContain('inte använda för svaret');

      const cards = container.querySelectorAll('.near-match-card');
      expect(cards).toHaveLength(retrievalHits.length);
      retrievalHits.forEach((hit, i) => {
        expect(cards[i].textContent).toContain(hit.document_name);
        expect(cards[i].textContent).toContain(String(hit.page));
        expect(cards[i].textContent).toContain(hit.text);
        expect(cards[i].textContent).toContain(String(hit.score));
      });

      // Must be visually distinct from verified citations — no citation-chip
      // class anywhere on a near-match card.
      cards.forEach((c) => expect(c.classList.contains('citation-chip')).toBe(false));
      expect(container.querySelectorAll('.citation-chip')).toHaveLength(0);
    });

    it('clicking a near-match opens the document at its page WITHOUT rects (no verified rects exist for retrieval hits)', () => {
      const askResponse = {
        answer: 'Jag hittar inget i de uppladdade dokumenten som verkar besvara den frågan.',
        citations: [],
        rejected_citations: [],
        refusal: true,
        warning: null,
        retrieval: retrievalHits,
      };
      const openDocViewer = vi.fn();
      const messages = [buildAnswerMessage(askResponse)];

      const { container } = render(
        <ChatMessageList messages={messages} userInitials="AB" openDocViewer={openDocViewer} />
      );

      container.querySelectorAll('.near-match-card')[1].click();

      expect(openDocViewer).toHaveBeenCalledTimes(1);
      const [doc, opts] = openDocViewer.mock.calls[0];
      expect(doc).toBe(retrievalHits[1]);
      expect(opts.page).toBe(retrievalHits[1].page);
      expect(opts.rects).toBeUndefined();
    });

    it('a refusal with empty retrieval renders no near-matches section', () => {
      const askResponse = {
        answer: 'Det finns inga dokument uppladdade ännu.',
        citations: [],
        rejected_citations: [],
        refusal: true,
        warning: null,
        retrieval: [],
      };
      const messages = [buildAnswerMessage(askResponse)];

      const { container } = render(
        <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
      );

      expect(container.querySelector('.near-matches-section')).toBeNull();
      expect(container.querySelectorAll('.near-match-card')).toHaveLength(0);
    });

    it('a normal answered (non-refusal) response does NOT render near-matches, even though AskResponse.retrieval is populated on success too', () => {
      const askResponse = {
        answer: 'Enligt stadgarna gäller följande.',
        citations: [
          { document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning kräver styrelsens samtycke.', chunk_id: 'hash-real-1', rects: [[10, 20, 30, 40]], score: 0.81 },
        ],
        rejected_citations: [],
        refusal: false,
        warning: null,
        retrieval: retrievalHits,
      };
      const messages = [buildAnswerMessage(askResponse)];

      const { container } = render(
        <ChatMessageList messages={messages} userInitials="AB" openDocViewer={vi.fn()} />
      );

      expect(container.querySelector('.near-matches-section')).toBeNull();
      expect(container.querySelectorAll('.near-match-card')).toHaveLength(0);
    });
  });
});
