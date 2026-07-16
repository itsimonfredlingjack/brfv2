import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CitationChip from './CitationChip';

// Mirrors backend/app/schemas.py CitationOut shape.
const baseCitation = {
  document_id: 'doc1',
  document_name: 'Stadgar.pdf',
  page: 3,
  quote: 'Årsavgiften fastställs av styrelsen',
  quotes: ['Årsavgiften fastställs av styrelsen'],
  chunk_id: 'K1',
  rects: [[10, 20, 100, 40]],
  score: 0.9,
  approximate: false,
};

describe('CitationChip', () => {
  it('renders document name and page', () => {
    render(<CitationChip citation={baseCitation} onOpen={() => {}} />);
    const button = screen.getByRole('button');
    expect(button).toHaveTextContent('Stadgar.pdf');
    expect(button).toHaveTextContent('s.3');
  });

  it('does not render the approximate affordance for a digital-source citation', () => {
    render(<CitationChip citation={baseCitation} onOpen={() => {}} />);
    expect(screen.queryByText('Ungefärlig markering')).not.toBeInTheDocument();
  });

  it('renders the approximate affordance for a scanned-source citation', () => {
    render(<CitationChip citation={{ ...baseCitation, approximate: true }} onOpen={() => {}} />);
    expect(screen.getByText('Ungefärlig markering')).toBeInTheDocument();
  });

  it('calls onOpen with page/rects/highlightPage/approximate on click (approximate case)', () => {
    const onOpen = vi.fn();
    const citation = { ...baseCitation, approximate: true };
    render(<CitationChip citation={citation} onOpen={onOpen} />);
    screen.getByRole('button').click();
    expect(onOpen).toHaveBeenCalledWith(citation, {
      page: citation.page,
      rects: citation.rects,
      highlightPage: citation.page,
      approximate: true,
    });
  });

  it('calls onOpen with approximate: false for a digital-source citation', () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={baseCitation} onOpen={onOpen} />);
    screen.getByRole('button').click();
    expect(onOpen).toHaveBeenCalledWith(baseCitation, {
      page: baseCitation.page,
      rects: baseCitation.rects,
      highlightPage: baseCitation.page,
      approximate: false,
    });
  });
});
