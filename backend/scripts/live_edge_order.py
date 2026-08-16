"""Compare full-corpus excerpt order: page vs probe-edge vs query-edge.

Usage (from backend/):
    uv run python -m scripts.live_edge_order --folder ../DONT_PUSH_brf_stuff --out out/edge-order
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import ask, evaluate_full_corpus  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.prefix_warmup import warm_prefix  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.live_full_corpus import QUESTIONS, _TimingHandler, _ingest  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

logger = logging.getLogger("brf.live_edge_order")

MODES = ("page", "probe", "query")
ARCHIVE_N_CTX = 65536


def _parse_timings(line: str) -> dict:
    out: dict[str, float | int | None] = {"prompt_n": None, "prompt_ms": None, "cache_n": None}
    for key in out:
        marker = f"{key}="
        if marker not in line:
            continue
        raw = line.split(marker, 1)[1].split()[0]
        try:
            out[key] = float(raw) if "." in raw else int(raw)
        except ValueError:
            out[key] = None
    return out


def run_modes(folder: Path, data_dir: Path) -> list[dict]:
    store = Store(data_dir=data_dir)
    _ingest(store, folder)
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("live_corpus_runtime saknas — sätt BRF_LLM och BRF_LLM_BASE_URL")
    provider = pick_provider()
    handler = _TimingHandler()
    logging.getLogger("brf.llm").addHandler(handler)
    payload = []
    for mode in MODES:
        store._full_corpus_order = mode
        store._full_corpus_tokens = None
        if mode in ("page", "probe"):
            warm = warm_prefix(store, runtime, provider)
            print(f"mode={mode} warmup={warm}", flush=True)
        rows = []
        for qid, question in QUESTIONS:
            n_before = len(handler.lines)
            _index, chunks, _pages, documents = store.snapshot()
            evaluated = evaluate_full_corpus(
                store, chunks, documents, runtime, question=question
            )
            decision = evaluated[0] if evaluated is not None else None
            t0 = time.perf_counter()
            resp = ask(store, question, corpus_runtime=runtime)
            elapsed = round(time.perf_counter() - t0, 3)
            logs = handler.lines[n_before:]
            parsed = _parse_timings(logs[-1]) if logs else {}
            row = {
                "qid": qid,
                "mode": mode,
                "refused": resp.refusal,
                "refusal_reason": resp.refusal_reason,
                "n_citations": len(resp.citations),
                "elapsed_s": elapsed,
                "ask_path": "full_corpus" if decision is not None and decision.use_full_corpus else "other",
                "bound": decision.bound if decision is not None else None,
                "prefix_tokens": decision.prefix_tokens if decision is not None else None,
                "prompt_n": parsed.get("prompt_n"),
                "prompt_ms": parsed.get("prompt_ms"),
                "cache_n": parsed.get("cache_n"),
                "timings_log": logs,
            }
            rows.append(row)
            print(
                f"mode={mode} {qid} refused={row['refused']} prompt_n={row['prompt_n']} "
                f"prompt_ms={row['prompt_ms']} cache_n={row['cache_n']} elapsed_s={elapsed}",
                flush=True,
            )
        payload.append({"mode": mode, "questions": rows})
    logging.getLogger("brf.llm").removeHandler(handler)
    return payload


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
    ap.add_argument("--out", type=Path, default=Path("out/edge-order"))
    args = ap.parse_args()

    os.environ.setdefault("BRF_EMBEDDER", "model2vec")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("BRF_LLM", "selfhosted")
    os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    os.environ["BRF_PREFIX_WARMUP"] = "0"

    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    audit_log, _allowed = install_network_audit()
    if not wait_n_ctx(origin, ARCHIVE_N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx är inte {ARCHIVE_N_CTX}")
    args.out.mkdir(parents=True, exist_ok=True)

    payload = {"modes": []}
    with tempfile.TemporaryDirectory() as tmp:
        payload["modes"] = run_modes(args.folder, Path(tmp) / "assoc")
    (args.out / "edge_order.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    _enforce_loopback(audit_log)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    main()
