// Pure helpers for PdfViewer.jsx, split out so they're unit-testable
// without mounting pdf.js in jsdom (PdfViewer.jsx loads a real pdf.js
// worker at import time, which this module must not).

/**
 * CSS class(es) for a highlight overlay. Scanned-source citations resolve
 * against OCR word boxes, which clip ~9-27% of the time vs. exact on
 * born-digital PDFs (never misplaced -- reality-check condition 3). The
 * approximate variant renders the highlight as dashed / reduced-opacity so
 * the user isn't misled into treating it as pixel-exact.
 */
export function highlightClassName(approximate) {
  return approximate ? 'pdfviewer-highlight pdfviewer-highlight--approximate' : 'pdfviewer-highlight';
}
