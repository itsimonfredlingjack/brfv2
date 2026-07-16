import React, { useEffect, useRef, useState, useCallback } from 'react';
import { X, ChevronLeft, ChevronRight, Loader2, AlertCircle } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { highlightClassName } from './pdfViewerHelpers';
import './PdfViewer.css';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

/**
 * Renders the real PDF page with highlight overlays.
 *
 * `rects` are in PDF points with TOP-LEFT origin (backend/PyMuPDF convention).
 * They are converted through the pdf.js viewport (y-flip into PDF user space
 * first) so scaling and page rotation are handled correctly.
 */
function PdfViewer({ url, title, page: initialPage = 1, rects = [], highlightPage = null, approximate = false, onClose }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const pdfRef = useRef(null);
  const renderTaskRef = useRef(null);
  const [pageNum, setPageNum] = useState(initialPage);
  const [numPages, setNumPages] = useState(0);
  const [overlays, setOverlays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const loadingTask = pdfjsLib.getDocument({ url: new URL(url, window.location.href).href });
    loadingTask.promise
      .then((pdf) => {
        if (cancelled) {
          // Cleanup already ran; make sure the late-resolved document is torn down.
          pdf.destroy().catch(() => {});
          return;
        }
        pdfRef.current = pdf;
        setNumPages(pdf.numPages);
        setPageNum(Math.min(Math.max(1, initialPage), pdf.numPages));
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
      // Destroys the worker/transport whether the load is still in flight or
      // already resolved (PDFDocumentProxy.destroy delegates here anyway).
      loadingTask.destroy().catch(() => {});
      pdfRef.current = null;
    };
  }, [url, initialPage]);

  const renderPage = useCallback(async () => {
    const pdf = pdfRef.current;
    const canvas = canvasRef.current;
    if (!pdf || !canvas) return;
    setLoading(true);
    setOverlays([]); // never let a previous page's highlights linger
    let task = null;
    try {
      const page = await pdf.getPage(pageNum);
      const containerWidth = containerRef.current?.clientWidth || 760;
      const baseViewport = page.getViewport({ scale: 1 });
      const scale = Math.min(1.6, (containerWidth - 32) / baseViewport.width);
      const viewport = page.getViewport({ scale });

      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      const ctx = canvas.getContext('2d');

      renderTaskRef.current?.cancel?.();
      task = page.render({
        canvasContext: ctx,
        viewport,
        transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
      });
      renderTaskRef.current = task;
      await task.promise;

      // Highlights: only on the cited page.
      const showHighlights = highlightPage == null || highlightPage === pageNum;
      if (showHighlights && rects.length) {
        const pageHeightPts = page.view[3] - page.view[1];
        const [a, b, c, d, e, f] = viewport.transform;
        const tx = (x, y) => [a * x + c * y + e, b * x + d * y + f];
        const boxes = rects.map(([x0, y0, x1, y1]) => {
          // top-left-origin points → PDF user space (y-up) → viewport CSS px
          const p1 = tx(x0, pageHeightPts - y1);
          const p2 = tx(x1, pageHeightPts - y0);
          return {
            left: Math.min(p1[0], p2[0]),
            top: Math.min(p1[1], p2[1]),
            width: Math.abs(p2[0] - p1[0]),
            height: Math.abs(p2[1] - p1[1]),
          };
        });
        setOverlays(boxes);
      } else {
        setOverlays([]);
      }
      setError(null);
    } catch (e) {
      if (e?.name !== 'RenderingCancelledException') setError(String(e?.message || e));
    } finally {
      // Only the most recent render owns the loading state — a cancelled
      // render's finally must not hide the spinner of its replacement.
      if (task === null || renderTaskRef.current === task) setLoading(false);
    }
  }, [pageNum, rects, highlightPage]);

  useEffect(() => {
    if (numPages > 0) renderPage();
  }, [numPages, renderPage]);

  return (
    <div className="pdfviewer-overlay" onClick={onClose}>
      <div className="pdfviewer-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <header className="pdfviewer-header">
          <div className="pdfviewer-title">{title}</div>
          <div className="pdfviewer-nav">
            <button
              className="icon-btn"
              disabled={pageNum <= 1}
              onClick={() => setPageNum((p) => p - 1)}
              aria-label="Föregående sida"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="pdfviewer-pageinfo">
              Sida {pageNum} av {numPages || '…'}
              {highlightPage && highlightPage !== pageNum && (
                <button className="pdfviewer-jump" onClick={() => setPageNum(highlightPage)}>
                  Till markeringen (s. {highlightPage})
                </button>
              )}
            </span>
            <button
              className="icon-btn"
              disabled={pageNum >= numPages}
              onClick={() => setPageNum((p) => p + 1)}
              aria-label="Nästa sida"
            >
              <ChevronRight size={18} />
            </button>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Stäng">
            <X size={18} />
          </button>
        </header>
        {approximate && (
          <div className="pdfviewer-approx-note">
            <AlertCircle size={13} />
            Inskannat dokument — markeringen är ungefärlig
          </div>
        )}
        <div className="pdfviewer-body" ref={containerRef}>
          {error && <div className="pdfviewer-error">Kunde inte visa PDF: {error}</div>}
          <div className="pdfviewer-canvas-wrap">
            <canvas ref={canvasRef} />
            {overlays.map((b, i) => (
              <div
                key={i}
                className={highlightClassName(approximate)}
                style={{ left: b.left, top: b.top, width: b.width, height: b.height }}
              />
            ))}
            {loading && (
              <div className="pdfviewer-loading">
                <Loader2 size={22} className="spin" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PdfViewer;
