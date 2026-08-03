"""Recording the component vocabulary, so the two declarations of it cannot drift.

:mod:`app.website.components` is the authority on what a BRF page may contain.
``brfv2-mockup/src/components/website/websiteConfig.jsx`` declares the same
vocabulary again in React, because the backend has to *validate* a vocabulary
and the browser has to *draw* one, and neither can do the other's job.

Two declarations of one thing drift. When they do, the failure is quiet and
unpleasant: the editor offers a field the backend refuses, or the backend
accepts a block the editor cannot render, and the first person to find out is a
board member whose page will not save. So the pair is locked to a recorded file
that both sides are tested against — the backend in ``test_website.py``, the
editor in ``websiteVocabulary.test.js``.

Same discipline as ``app.invoices.rules``: changing the vocabulary is meant to
be deliberate, and re-recording the lock is the deliberate part.

    make website-vocabulary-lock
"""

from __future__ import annotations

import json
from pathlib import Path

from .components import vocabulary

LOCK_PATH = Path(__file__).resolve().parent / "VOCABULARY.lock.json"


def serialise() -> str:
    """The vocabulary as the lock file holds it.

    ``sort_keys`` and a trailing newline so the file is stable byte-for-byte
    across machines and Python versions — a lock that reordered itself would
    fail the build for no reason and teach everyone to re-record it reflexively.
    """
    return json.dumps(vocabulary(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def record() -> Path:
    LOCK_PATH.write_text(serialise(), encoding="utf-8")
    return LOCK_PATH


def matches() -> bool:
    try:
        return LOCK_PATH.read_text(encoding="utf-8") == serialise()
    except FileNotFoundError:
        return False


def _main(argv: list[str]) -> int:  # pragma: no cover - operator entry point
    write = "--write" in argv
    current = vocabulary()
    print(f"Blocktyper: {len(current['components'])}")
    for name, spec in current["components"].items():
        print(f"  · {name} ({spec['label']}) — {len(spec['fields'])} fält")

    if write:
        path = record()
        print(f"\nSkrev {path.name}")
        print(
            "Kom ihåg att websiteConfig.jsx ska deklarera samma sak — "
            "kör `npm test` i brfv2-mockup."
        )
        return 0

    if matches():
        print("\nOrdlistan stämmer med den inspelade låsfilen.")
        return 0

    print(
        "\nOrdlistan skiljer sig från VOCABULARY.lock.json. Ändra båda sidorna "
        "(components.py och websiteConfig.jsx) och kör om med --write."
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import sys

    raise SystemExit(_main(sys.argv[1:]))


__all__ = ["LOCK_PATH", "matches", "record", "serialise"]
