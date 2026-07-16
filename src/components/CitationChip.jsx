import React from 'react';
import { FileText, AlertCircle } from 'lucide-react';

/**
 * A single citation chip in the chat citations list. Opens the PDF viewer
 * on click, scrolled to the cited page with its rects highlighted.
 *
 * Reality-check condition 3: citations resolved against a scanned-source
 * document (OCR word boxes) clip ~9-27% of the time vs. exact on
 * born-digital PDFs (never misplaced). `citation.approximate` carries that
 * distinction from the backend (CitationOut.approximate); the chip renders
 * a small amber affordance so the user isn't misled into treating an
 * OCR-derived highlight as exact, and forwards `approximate` to `onOpen` so
 * the PDF viewer can render the highlight accordingly.
 */
function CitationChip({ citation, onOpen }) {
  const handleClick = () => {
    onOpen(citation, {
      page: citation.page,
      rects: citation.rects,
      highlightPage: citation.page,
      approximate: citation.approximate,
    });
  };

  return (
    <button className="citation-chip" title={`"${citation.quote}"`} onClick={handleClick}>
      <FileText size={12} />
      {citation.document_name} · s.{citation.page}
      {citation.approximate && (
        <span className="citation-chip-approx">
          <AlertCircle size={11} />
          Ungefärlig markering
        </span>
      )}
    </button>
  );
}

export default CitationChip;
