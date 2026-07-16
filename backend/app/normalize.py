"""Canonical text normalization and token-level span matching.

Everything the citation verifier does rests on these primitives. Both the
source words (from PDF extraction) and the LLM's quotes pass through the same
canonicalization, so systematic quirks (typographic quotes, NBSP, ligatures,
Swedish suspended hyphens) cancel out, while linebreak hyphenation is handled
by an explicit merge rule.
"""

from __future__ import annotations

import unicodedata

_CHAR_MAP = str.maketrans(
    {
        "­": "",  # soft hyphen
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "‘": "'",
        "’": "'",
        "‚": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
    }
)

# Stripped from token edges. Hyphen is deliberately absent: a trailing hyphen
# carries hyphenation information and internal hyphens are meaningful.
_EDGE_PUNCT = ".,;:!?\"'()[]{}«»§•·*/\\|<>=…"


def normalize_text(s: str) -> str:
    """Character-level canonical form: explicit folds, NFKC, casefold."""
    s = s.translate(_CHAR_MAP)
    s = unicodedata.normalize("NFKC", s)
    return s.casefold()


def norm_token(s: str) -> str:
    """Token-level canonical form. Keeps trailing/internal hyphens."""
    t = normalize_text(s).strip()
    # Strip edge punctuation, but keep a trailing hyphen (hyphenation signal)
    # and a leading hyphen only if it's the entire token remnant.
    t = t.strip(_EDGE_PUNCT)
    t = t.lstrip("-") if len(t) > 1 else t
    return t


def _hyphen_free(t: str) -> str:
    return t.replace("-", "")


# Characters that signal linebreak hyphenation when they end a raw token:
# hyphen-minus, U+2010 hyphen, U+2011 non-breaking hyphen, soft hyphen.
# Em/en dashes are deliberately absent — they are punctuation, not
# hyphenation, even though _CHAR_MAP folds them to "-" for equality.
_MERGE_SIGNALS = "-‐‑­"


def _merge_signal(raw: str) -> bool:
    r = raw.strip().rstrip(_EDGE_PUNCT)
    return bool(r) and r[-1] in _MERGE_SIGNALS


def canonical_stream(raw_tokens: list[str], *, merge: bool = True) -> list[tuple[str, list[int]]]:
    """Map raw whitespace tokens to canonical tokens with provenance.

    Returns [(canonical_token, [original_indices]), ...]. A token whose raw
    form ends in a hyphenation character merges with the following token —
    chained, so a word split across 3+ lines still folds into one token.
    Because both sides of a comparison pass through this function,
    grammatical suspended hyphens ("vatten- och ...") merge identically on
    both sides. Em/en dashes never trigger a merge (they fold to '-' for
    equality only). Tokens that normalize to nothing (pure punctuation) are
    skipped. merge=False yields the unmerged stream — the fallback matcher
    for quotes that begin or end inside a merged word.
    """
    out: list[tuple[str, list[int]]] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        t = norm_token(raw_tokens[i])
        if not t or not _hyphen_free(t):
            i += 1
            continue
        idxs = [i]
        merged = t
        j = i
        while merge and _merge_signal(raw_tokens[j]):
            k = j + 1
            while k < n and not _hyphen_free(norm_token(raw_tokens[k])):
                k += 1
            if k >= n:
                break
            if merged.endswith("-") and len(merged) > 1:
                merged = merged[:-1]
            merged = merged + norm_token(raw_tokens[k])
            idxs.append(k)
            j = k
        out.append((merged, idxs))
        i = (j + 1) if len(idxs) > 1 else i + 1
    return out


def _tokens_equal(a: str, b: str) -> bool:
    return a == b or _hyphen_free(a) == _hyphen_free(b)


def _match_streams(src_stream: list[tuple[str, list[int]]], q_tokens: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    m = len(q_tokens)
    for start in range(len(src_stream) - m + 1):
        if all(_tokens_equal(src_stream[start + k][0], q_tokens[k]) for k in range(m)):
            first_idx = src_stream[start][1][0]
            last_idx = src_stream[start + m - 1][1][-1]
            spans.append((first_idx, last_idx))
    return spans


def find_spans(source_words: list[str], quote: str) -> list[tuple[int, int]]:
    """Find every occurrence of `quote` in `source_words`.

    Returns inclusive (start_word_index, end_word_index) spans in the original
    word list, in order of occurrence. Empty list when the quote (after
    canonicalization) is empty or not present. Matching runs on the merged
    canonical streams first; if that finds nothing, an unmerged pass catches
    quotes that begin or end inside a hyphenation merge (e.g. a quote starting
    at "valtningen" where the source reads "för-⏎valtningen").
    """
    q_tokens = [t for t, _ in canonical_stream(quote.split())]
    if not q_tokens:
        return []
    spans = _match_streams(canonical_stream(list(source_words)), q_tokens)
    if spans:
        return spans
    q_unmerged = [t for t, _ in canonical_stream(quote.split(), merge=False)]
    if not q_unmerged:
        return []
    return _match_streams(canonical_stream(list(source_words), merge=False), q_unmerged)
