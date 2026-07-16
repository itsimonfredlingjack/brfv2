import { describe, it, expect } from 'vitest';
import { highlightClassName } from './pdfViewerHelpers';

// Pure unit tests for the overlay-class decision, kept separate from
// PdfViewer.jsx (which loads pdf.js and is not rendered in jsdom).
describe('highlightClassName', () => {
  it('returns the base class for an exact (digital-source) highlight', () => {
    expect(highlightClassName(false)).toBe('pdfviewer-highlight');
  });

  it('adds the approximate modifier for a scanned-source highlight', () => {
    expect(highlightClassName(true)).toBe('pdfviewer-highlight pdfviewer-highlight--approximate');
  });
});
