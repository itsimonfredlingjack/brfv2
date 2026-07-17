import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CitationsPanel from './CitationsPanel';

// Component tests per cleanup-task-2-brief.md's test list: "panel renders
// exactly the response's citations; click payload carries the response's
// page/rects verbatim; multi-span excerpt keeps the marker". Fixtures are
// plain AskResponse.citations[]-shaped objects — no HTTP mocked, matching
// ChatMessageList.test.jsx's fixture-based style.

describe('CitationsPanel', () => {
  it('renders exactly the given citations, in order, with document name/page/quote', () => {
    const citations = [
      { document_id: 'd1', document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning kräver styrelsens samtycke.', chunk_id: 'hash-1', rects: [[10, 20, 30, 40]], score: 0.81 },
      { document_id: 'd2', document_name: 'Årsredovisning 2024.pdf', page: 12, quote: 'Föreningens resultat uppgick till...', chunk_id: 'hash-2', rects: [[5, 6, 7, 8]], score: 0.74 },
    ];

    const { container } = render(<CitationsPanel citations={citations} openDocViewer={vi.fn()} />);

    const cards = container.querySelectorAll('.citation-card');
    expect(cards).toHaveLength(citations.length);
    citations.forEach((c, i) => {
      expect(cards[i].textContent).toContain(c.document_name);
      expect(cards[i].textContent).toContain(String(c.page));
      expect(cards[i].textContent).toContain(c.quote);
    });
  });

  it('renders an empty state and zero cards when there are no citations', () => {
    const { container } = render(<CitationsPanel citations={[]} openDocViewer={vi.fn()} />);

    expect(container.querySelectorAll('.citation-card')).toHaveLength(0);
    expect(container.querySelector('.citations-panel-empty')).not.toBeNull();
  });

  it('clicking a card opens the real source with the page/rects/highlightPage taken verbatim from that citation', () => {
    const citations = [
      { document_id: 'd1', document_name: 'Stadgar.pdf', page: 4, quote: 'q1', chunk_id: 'hash-1', rects: [[10, 20, 30, 40]], score: 0.81 },
      { document_id: 'd2', document_name: 'B.pdf', page: 9, quote: 'q2', chunk_id: 'hash-2', rects: [[1, 1, 2, 2]], score: 0.5 },
    ];
    const openDocViewer = vi.fn();

    const { container } = render(<CitationsPanel citations={citations} openDocViewer={openDocViewer} />);

    container.querySelectorAll('.citation-card-action')[1].click();

    expect(openDocViewer).toHaveBeenCalledTimes(1);
    expect(openDocViewer).toHaveBeenCalledWith(citations[1], {
      page: citations[1].page,
      rects: citations[1].rects,
      highlightPage: citations[1].page,
    });
  });

  it('renders a multi-span excerpt\'s " […] " display quote as-is, never joined into a seamless sentence', () => {
    const multiSpan = {
      document_id: 'd1', document_name: 'Protokoll.pdf', page: 2,
      quote: 'Årsavgiften höjs med 5% […] gäller från 1 januari 2025.',
      quotes: ['Årsavgiften höjs med 5%', 'gäller från 1 januari 2025.'],
      chunk_id: 'hash-3', rects: [[1, 2, 3, 4], [5, 6, 7, 8]], score: 0.9,
    };

    const { container } = render(<CitationsPanel citations={[multiSpan]} openDocViewer={vi.fn()} />);

    expect(screen.getByText(multiSpan.quote, { exact: false })).toBeInTheDocument();
    expect(container.querySelector('.citation-card-quote').textContent).toContain('[…]');
  });
});
