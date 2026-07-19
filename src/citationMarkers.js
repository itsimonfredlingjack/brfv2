// Parses an AI answer string into a sequence of text/marker segments,
// linkifying ONLY explicit [K<n>]/[<n>] tokens already present in the
// string that map 1:1 (1-based index) to an entry in `citations`. A
// token whose index has no matching citation is left as plain text,
// verbatim — this function never injects a marker that wasn't already
// in the source string (cleanup-global-constraints.md #2,
// cleanup-task-2-brief.md: "unmatched tokens render as plain text").
//
// Pure function — no rendering — so the mapping can be proven in
// isolation, the same way chatResponseMapping.js's extraction lets the
// response -> message mapping be tested without mounting a component.

const MARKER_RE = /\[K?(\d+)\]/g;

export function parseCitationMarkers(content, citations = []) {
  const text = content ?? '';
  const segments = [];
  let lastIndex = 0;
  MARKER_RE.lastIndex = 0;
  let match;
  while ((match = MARKER_RE.exec(text))) {
    const n = parseInt(match[1], 10);
    const citation = citations[n - 1];
    if (!citation) continue; // unmatched token: left embedded in surrounding text below

    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: 'marker', text: match[0], citation });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', text: text.slice(lastIndex) });
  }
  return segments;
}
