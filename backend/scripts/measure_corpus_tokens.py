"""Per-association token volume with the generator tokenizer.

Stdout is numbers only — never document text, never filenames in a committed
artefact. --folder is required.

Usage (from backend/):
    uv run python -m scripts.measure_corpus_tokens --folder /path/to/pdfs
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import _CITATION_HEADROOM_TOKENS, _render_excerpts, _system_prompt  # noqa: E402
from app.full_corpus import CorpusRuntime, LlamaCppRuntime, decide_fit, hits_for_full_corpus, measure_tokens  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402

COLUMNS = (
    "association",
    "documents",
    "pages",
    "chunks",
    "chunk_token_sum",
    "unique_tokens",
    "spill",
    "p50",
    "p95",
    "max",
)


def association_paths(folder: Path) -> list[Path]:
    """Each immediate subdirectory with PDFs is an association; a flat PDF folder is one."""
    folder = folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"--folder är ingen katalog: {folder}")
    subdirs = sorted(
        p for p in folder.iterdir() if p.is_dir() and any(p.glob("*.pdf"))
    )
    here = list(folder.glob("*.pdf"))
    if subdirs:
        return subdirs
    if here:
        return [folder]
    raise SystemExit(f"Inga PDF:er under {folder}")


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    idx = (p / 100.0) * (len(xs) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(xs) - 1)
    frac = idx - lo
    return int(round(xs[lo] * (1 - frac) + xs[hi] * frac))


def report_association(name: str, store: Store, runtime: CorpusRuntime) -> dict:
    """chunk_token_sum double-counts overlap; unique_tokens uses the chunker join."""
    chunk_counts = [runtime.count(chunk.text) for chunk in store.chunks.values()]
    chunk_token_sum = sum(chunk_counts)
    unique_tokens = 0
    pages_n = 0
    for page_list in store.pages.values():
        for page in page_list:
            pages_n += 1
            unique_tokens += runtime.count(" ".join(w.text for w in page.words))
    return {
        "association": name,
        "documents": len(store.documents),
        "pages": pages_n,
        "chunks": len(store.chunks),
        "chunk_token_sum": chunk_token_sum,
        "unique_tokens": unique_tokens,
        "spill": chunk_token_sum - unique_tokens,
        "p50": _percentile(chunk_counts, 50),
        "p95": _percentile(chunk_counts, 95),
        "max": max(chunk_counts) if chunk_counts else 0,
    }


def format_report(rows: list[dict]) -> str:
    lines = [" ".join(COLUMNS)]
    for row in rows:
        lines.append(" ".join(str(row[c]) for c in COLUMNS))
    return "\n".join(lines)


def _ingest_folder(store: Store, folder: Path) -> None:
    for pdf in sorted(folder.glob("*.pdf")):
        store.add_document(pdf.name, pdf.read_bytes())


def _enforce_loopback(audit_log: list[dict]) -> None:
    external = [e for e in audit_log if not e.get("allowed", False)]
    if external:
        hosts = sorted({f"{e['host']}:{e['port']}" for e in external})
        raise SystemExit(
            f"NÄTVERKSREVISION MISSLYCKADES: {len(external)} extern(a) anslutning(ar). Värdar: {hosts}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, required=True)
    args = ap.parse_args()

    audit_log, _allowed = install_network_audit()
    base = os.environ.get("BRF_LLM_BASE_URL", "").strip()
    if not base:
        raise SystemExit("BRF_LLM_BASE_URL saknas — tokenisering kräver llama.cpp /tokenize")
    runtime = LlamaCppRuntime(base)

    rows = []
    for assoc in association_paths(args.folder):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(data_dir=Path(tmp))
            _ingest_folder(store, assoc)
            rows.append(report_association(assoc.name, store, runtime))
            hits = hits_for_full_corpus(store.chunks, store.documents)
            excerpts, _alias = _render_excerpts(hits)
            system = _system_prompt(store.settings)
            chunk_token_sum, prefix_tokens = measure_tokens(
                runtime, store.chunks, system=system, excerpts=excerpts
            )
            decision = decide_fit(
                chunk_token_sum=chunk_token_sum,
                prefix_tokens=prefix_tokens,
                n_ctx=runtime.n_ctx(),
                threshold=store.settings.fullCorpusTokenThreshold,
                response_budget=store.settings.maxResponseLength + _CITATION_HEADROOM_TOKENS,
            )
            print(
                f"bound={decision.bound} n_ctx={decision.n_ctx} threshold={decision.threshold} "
                f"chunk_token_sum={decision.chunk_token_sum} prefix_tokens={decision.prefix_tokens} "
                f"effective_cap={decision.effective_cap} use={decision.use_full_corpus}",
                file=sys.stderr,
                flush=True,
            )
    print(format_report(rows), flush=True)
    _enforce_loopback(audit_log)


if __name__ == "__main__":
    main()
