import { describe, it, expect } from 'vitest';
import { parseCitationMarkers } from './citationMarkers';

// Proves the marker <-> citation mapping in isolation, per
// cleanup-task-2-brief.md's test list: "no-marker answers get no injected
// markers" and unmatched-token handling. ChatMessageList.test.jsx composes
// this with the real component to prove the full render path.

describe('parseCitationMarkers', () => {
  it('a plain answer with no bracket tokens is returned as a single unmodified text segment', () => {
    const content = 'Jag kan tyvärr inte svara på det utifrån de verifierade källorna.';

    expect(parseCitationMarkers(content, [])).toEqual([{ type: 'text', text: content }]);
  });

  it('a [<n>] token that maps to citations[n-1] becomes a marker segment carrying that exact citation object', () => {
    const citations = [
      { document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning...', chunk_id: 'a1', rects: [[1, 2, 3, 4]], score: 0.81 },
    ];

    const segments = parseCitationMarkers('Enligt [1] gäller detta.', citations);

    expect(segments).toEqual([
      { type: 'text', text: 'Enligt ' },
      { type: 'marker', text: '[1]', citation: citations[0] },
      { type: 'text', text: ' gäller detta.' },
    ]);
  });

  it('a [K<n>] token maps the same way as [<n>], keeping the original "K" text verbatim', () => {
    const citations = [
      { document_name: 'A.pdf', page: 1, quote: 'a' },
      { document_name: 'B.pdf', page: 2, quote: 'b' },
    ];

    const segments = parseCitationMarkers('Se [K2] för detaljer.', citations);

    expect(segments).toEqual([
      { type: 'text', text: 'Se ' },
      { type: 'marker', text: '[K2]', citation: citations[1] },
      { type: 'text', text: ' för detaljer.' },
    ]);
  });

  it('a token whose index has no matching citation stays plain text, verbatim, not injected as a marker', () => {
    const citations = [{ document_name: 'A.pdf', page: 1, quote: 'a' }];

    const segments = parseCitationMarkers('Se [9] för detaljer.', citations);

    expect(segments).toEqual([{ type: 'text', text: 'Se [9] för detaljer.' }]);
  });

  it('mixes matched and unmatched tokens in one string, leaving only the unmatched one as plain text', () => {
    const citations = [{ document_name: 'A.pdf', page: 1, quote: 'a' }];

    const segments = parseCitationMarkers('[1] är sant men [3] finns inte.', citations);

    expect(segments).toEqual([
      { type: 'marker', text: '[1]', citation: citations[0] },
      { type: 'text', text: ' är sant men [3] finns inte.' },
    ]);
  });

  it('with no citations at all, every bracket token is left as plain text', () => {
    const segments = parseCitationMarkers('Se [1] och [2].', []);

    expect(segments).toEqual([{ type: 'text', text: 'Se [1] och [2].' }]);
  });

  it('handles empty/undefined content without throwing', () => {
    expect(parseCitationMarkers('', [])).toEqual([]);
    expect(parseCitationMarkers(undefined, [])).toEqual([]);
  });
});
