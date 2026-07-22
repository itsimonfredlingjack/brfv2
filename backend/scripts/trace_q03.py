"""Privacy-bounded, opt-in q03 pipeline trace for the live pilot runtime.

The script runs exactly one production ``ask()`` call for the committed q03
question. It records two gitignored artifacts under ``backend/out``:

* ``private-trace.json`` contains the exact prompt, raw model output and local
  document details. It must never be committed or pasted into tickets.
* ``summary.json`` contains only hashes, counts, stage decisions, ranks and
  runtime identity. It is safe to use when writing a redacted evidence note.

The diagnostic rank census does not change Store settings or the production
``ask()`` call. It only locates the task row and its legend in the complete
index after the real response has been produced.

Usage (from backend/):

    BRF_MODE=pilot \
    BRF_LLM=selfhosted \
    BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
    BRF_LLM_MODEL=gemma4:e12b \
    BRF_LLM_RUNTIME_LABEL=agenntserver \
    BRF_EMBEDDER=model2vec \
    uv run python -m scripts.trace_q03 --network-audit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.reality import common  # noqa: E402


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_safe(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported trace value: {type(value)!r}")


class CaptureProvider:
    """Capture exact provider inputs/output without changing provider behavior."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = getattr(inner, "model", "")
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        call = {
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "model_argument": model,
        }
        self.calls.append(call)
        raw = self.inner.complete(system, user, max_tokens=max_tokens, model=model)
        call["raw"] = raw
        return raw


def _production_hits(store, question: str):
    s = store.settings
    index, _chunks, _pages, _documents = store.snapshot()
    return index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=s.candidateCount,
        top_k=s.topK,
        min_confidence=0.0,
    )


def _rank_census(store, question: str):
    """Diagnostic only: rank every indexed chunk without mutating settings."""
    s = store.settings
    index, _chunks, _pages, _documents = store.snapshot()
    width = max(1, len(index))
    return index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=width,
        top_k=width,
        min_confidence=0.0,
    )


def _legend_chunk_ids(chunks: dict) -> set[str]:
    """Find generic A/B responsibility legends without naming either party."""
    ids: set[str] = set()
    for chunk in chunks.values():
        folded = chunk.text.casefold()
        if (
            "kolumnen" in folded
            and "marker" in folded
            and re.search(r'["]a["]', folded)
            and re.search(r'["]b["]', folded)
        ):
            ids.add(chunk.id)
    return ids


def _runtime_metadata(base_url: str) -> tuple[dict, dict]:
    import httpx

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        models = client.get("/models")
        models.raise_for_status()
        props = client.get(base_url.removesuffix("/v1") + "/props")
        props.raise_for_status()

    model_ids = [str(item.get("id", "")) for item in models.json().get("data", [])]
    props_body = props.json()
    template = str(props_body.get("chat_template", ""))
    params = props_body.get("default_generation_settings", {}).get("params", {})
    private = {
        "advertised_model_ids": model_ids,
        "chat_template": template,
        "chat_template_caps": props_body.get("chat_template_caps", {}),
        "default_generation_settings": props_body.get("default_generation_settings", {}),
    }
    summary = {
        "advertised_model_count": len(model_ids),
        "advertised_model_matches_gemma_4_12b": any(
            any(marker in model_id.casefold() for marker in ("gemma-4-12b", "gemma4-12b", "gemma_4_12b"))
            for model_id in model_ids
        ),
        "chat_template_bytes": len(template.encode("utf-8")),
        "chat_template_sha256": _sha256(template),
        "chat_template_caps": props_body.get("chat_template_caps", {}),
        "chat_template_flags": {
            name: name in template
            for name in (
                "enable_thinking",
                "reasoning",
                "system",
                "developer",
                "add_generation_prompt",
            )
        },
        "default_generation": {
            key: params.get(key)
            for key in (
                "chat_format",
                "reasoning_format",
                "reasoning_in_content",
                "temperature",
                "top_k",
                "top_p",
                "min_p",
                "n_predict",
            )
        },
        "n_ctx": props_body.get("default_generation_settings", {}).get("n_ctx"),
    }
    return private, summary


def main() -> None:
    from app.answer import ask
    from app.llm import OpenAICompatProvider, parse_llm_json
    from scripts.model_readiness import _LOCATORS, _Q, _ingest_digital

    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=common.DEFAULT_FOLDER)
    parser.add_argument("--out", type=Path, default=common.BACKEND / "out" / "xs32" / "q03")
    parser.add_argument("--network-audit", action="store_true")
    args = parser.parse_args()

    expected = {
        "BRF_MODE": "pilot",
        "BRF_LLM": "selfhosted",
        "BRF_LLM_MODEL": "gemma4:e12b",
        "BRF_EMBEDDER": "model2vec",
    }
    mismatches = {key: os.environ.get(key) for key, value in expected.items() if os.environ.get(key) != value}
    if mismatches:
        raise SystemExit(f"Trace requires exact pilot environment; mismatches: {sorted(mismatches)}")
    base_url = os.environ.get("BRF_LLM_BASE_URL", "").rstrip("/")
    if base_url != "http://127.0.0.1:8000/v1":
        raise SystemExit("Trace requires the audited loopback SSH forward at http://127.0.0.1:8000/v1")

    audit_log = None
    if args.network_audit:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        audit_log, _allowed = common.install_network_audit()

    runtime_private, runtime_summary = _runtime_metadata(base_url)
    provider = CaptureProvider(OpenAICompatProvider())
    question = _Q["q03"]

    with common.temp_store() as store:
        digital_ids = _ingest_digital(store, args.folder)
        index, chunks, _pages, documents = store.snapshot()
        production_hits = _production_hits(store, question)
        census = _rank_census(store, question)
        census_rank = {hit.chunk_id: rank for rank, hit in enumerate(census, 1)}

        doc_chunks = []
        for doc_id in digital_ids:
            doc_chunks.extend(common.sorted_doc_chunks(store, doc_id))
        target_candidates = [
            (chunk, label, value)
            for chunk, label, value in _LOCATORS["cell_value"](doc_chunks)
            if "årsredovis" in label.casefold()
        ]
        target_ids = {chunk.id for chunk, _label, _value in target_candidates}
        legend_ids = _legend_chunk_ids(chunks)

        response = ask(store, question, provider=provider)
        parsed_calls = []
        for call in provider.calls:
            raw = call.get("raw", "")
            try:
                parsed = parse_llm_json(raw)
                parse_error = None
            except Exception as exc:  # diagnostic records the failure type only in summary
                parsed = None
                parse_error = repr(exc)
            parsed_calls.append({"parsed": parsed, "parse_error": parse_error})

        private = {
            "runtime": runtime_private,
            "question": question,
            "settings": store.settings.model_dump(mode="json"),
            "documents": [documents[doc_id].model_dump(mode="json") for doc_id in digital_ids],
            "production_hits": [hit.model_dump(mode="json") for hit in production_hits],
            "target_candidates": [
                {
                    "chunk": chunk.model_dump(mode="json"),
                    "label": label,
                    "value": value,
                    "diagnostic_rank": census_rank.get(chunk.id),
                }
                for chunk, label, value in target_candidates
            ],
            "legend_chunks": [
                {
                    "chunk": chunks[chunk_id].model_dump(mode="json"),
                    "diagnostic_rank": census_rank.get(chunk_id),
                }
                for chunk_id in sorted(legend_ids)
            ],
            "provider_calls": provider.calls,
            "parsed_calls": parsed_calls,
            "final_response": response.model_dump(mode="json"),
        }

        prompt = provider.calls[0]["user"] if provider.calls else ""
        raw = provider.calls[-1].get("raw", "") if provider.calls else ""
        final_parsed = parsed_calls[-1]["parsed"] if parsed_calls else None
        production_ids = {hit.chunk_id for hit in production_hits}
        summary = {
            "runtime": {
                "mode": os.environ["BRF_MODE"],
                "provider": provider.name,
                "model": provider.model,
                "runtime_label": os.environ.get("BRF_LLM_RUNTIME_LABEL", ""),
                "base_url_class": "loopback_ssh_tunnel",
                **runtime_summary,
            },
            "corpus": {
                "digital_document_count": len(digital_ids),
                "indexed_chunk_count": len(index),
            },
            "retrieval": {
                "production_top_k": store.settings.topK,
                "production_hit_count": len(production_hits),
                "target_candidate_count": len(target_candidates),
                "target_candidate_production_ranks": sorted(
                    rank
                    for chunk_id in target_ids
                    if (
                        rank := next(
                            (i for i, hit in enumerate(production_hits, 1) if hit.chunk_id == chunk_id),
                            None,
                        )
                    )
                    is not None
                ),
                "target_candidate_diagnostic_ranks": sorted(
                    rank for chunk_id in target_ids if (rank := census_rank.get(chunk_id)) is not None
                ),
                "legend_chunk_count": len(legend_ids),
                "legend_in_production_prompt": bool(legend_ids & production_ids),
                "legend_diagnostic_ranks": sorted(
                    rank for chunk_id in legend_ids if (rank := census_rank.get(chunk_id)) is not None
                ),
            },
            "prompt": {
                "call_count": len(provider.calls),
                "bytes": len(prompt.encode("utf-8")),
                "sha256": _sha256(prompt),
                "contains_target_row": any(chunks[chunk_id].text in prompt for chunk_id in target_ids),
                "contains_responsibility_legend": any(chunks[chunk_id].text in prompt for chunk_id in legend_ids),
                "system_bytes": len(provider.calls[0]["system"].encode("utf-8")) if provider.calls else 0,
                "system_sha256": _sha256(provider.calls[0]["system"]) if provider.calls else None,
                "max_tokens": provider.calls[0]["max_tokens"] if provider.calls else None,
            },
            "model_raw_output": {
                "bytes": len(raw.encode("utf-8")),
                "sha256": _sha256(raw),
                "has_json_object": "{" in raw and "}" in raw,
            },
            "structured_parse": {
                "ok": final_parsed is not None,
                "insufficient_data": final_parsed.get("insufficient_data") if final_parsed else None,
                "answer_bytes": len(final_parsed.get("answer", "").encode("utf-8")) if final_parsed else 0,
                "citation_count": len(final_parsed.get("citations", [])) if final_parsed else 0,
                "citation_span_counts": [len(c["quotes"]) for c in final_parsed.get("citations", [])]
                if final_parsed
                else [],
                "parse_error_types": [
                    item["parse_error"].split("(", 1)[0] for item in parsed_calls if item["parse_error"]
                ],
            },
            "citation_verification": {
                "verified_count": len(response.citations),
                "rejected_count": len(response.rejected_citations),
                "rejected_reasons": [item.reason for item in response.rejected_citations],
                "skipped_because_model_declared_insufficient": bool(
                    final_parsed
                    and final_parsed["insufficient_data"]
                    and store.settings.insufficientDataBehavior == "refuse"
                ),
            },
            "grounding_validation": {
                "numeric_gate_reached": not response.refusal,
                "numeric_grounding_failed": response.refusal_reason == "numeric_grounding_failed",
            },
            "final": {
                "refusal": response.refusal,
                "refusal_reason": response.refusal_reason,
                "provider": response.provider,
                "model": response.model,
            },
        }

    external = []
    if audit_log is not None:
        external = [entry for entry in audit_log if not entry["allowed"]]
        summary["network_audit"] = {
            "total_connections": len(audit_log),
            "external_connection_count": len(external),
            "endpoint_classes": sorted(
                {"loopback" if entry["host"] in ("127.0.0.1", "::1", "localhost") else "external" for entry in audit_log}
            ),
        }

    args.out.mkdir(parents=True, exist_ok=True)
    private_path = args.out / "private-trace.json"
    summary_path = args.out / "summary.json"
    private_path.write_text(json.dumps(private, ensure_ascii=False, indent=2, default=_json_safe), "utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"PRIVATE → {private_path}")
    print(f"SUMMARY → {summary_path}")

    if external:
        raise SystemExit("Network audit found disallowed external connections")


if __name__ == "__main__":
    main()
