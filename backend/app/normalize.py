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


def canonical_stream(raw_tokens: list[str]) -> list[tuple[str, list[int]]]:
    """Map raw whitespace tokens to canonical tokens with provenance.

    Returns [(canonical_token, [original_indices]), ...]. A token ending in a
    hyphen merges with the following token (linebreak hyphenation); because
    both sides of a comparison pass through this function, grammatical
    suspended hyphens ("vatten- och ...") merge identically on both sides.
    Tokens that normalize to nothing (pure punctuation) are skipped.
    """
    out: list[tuple[str, list[int]]] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        t = norm_token(raw_tokens[i])
        if not t or not _hyphen_free(t):
            i += 1
            continue
        if t.endswith("-") and len(t) > 1:
            # find the next non-empty token to merge with
            j = i + 1
            while j < n and not _hyphen_free(norm_token(raw_tokens[j])):
                j += 1
            if j < n:
                merged = t[:-1] + norm_token(raw_tokens[j])
                out.append((merged, [i, j]))
                i = j + 1
                continue
        out.append((t, [i]))
        i += 1
    return out


def _tokens_equal(a: str, b: str) -> bool:
    return a == b or _hyphen_free(a) == _hyphen_free(b)


def find_spans(source_words: list[str], quote: str) -> list[tuple[int, int]]:
    """Find every occurrence of `quote` in `source_words`.

    Returns inclusive (start_word_index, end_word_index) spans in the original
    word list, in order of occurrence. Empty list when the quote (after
    canonicalization) is empty or not present.
    """
    quote_stream = canonical_stream(quote.split())
    q_tokens = [t for t, _ in quote_stream]
    if not q_tokens:
        return []

    src_stream = canonical_stream(list(source_words))
    spans: list[tuple[int, int]] = []
    m = len(q_tokens)
    for start in range(len(src_stream) - m + 1):
        if all(_tokens_equal(src_stream[start + k][0], q_tokens[k]) for k in range(m)):
            first_idx = src_stream[start][1][0]
            last_idx = src_stream[start + m - 1][1][-1]
            spans.append((first_idx, last_idx))
    return spans
