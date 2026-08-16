"""Measure n_ctx cost and three-depth needle quality on loopback llama.cpp.

Temporarily overrides `-c` via a gitignored compose file, then always restores
the operational n_ctx (65536). Stdout is numbers only — never haystack text.

Usage (from backend/):
    uv run python -m scripts.measure_nctx_cost --out out/nctx-cost
    uv run python -m scripts.measure_nctx_cost --mode occupancy --out out/nctx-cost
    uv run python -m scripts.measure_nctx_cost --mode filled-window --out out/nctx-cost
    uv run python -m scripts.measure_nctx_cost --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.full_corpus import LlamaCppRuntime, server_origin  # noqa: E402
from app.needle_haystack import (  # noqa: E402
    CANARIES,
    HAYSTACK_SIZES,
    build_haystack,
    haystack_row,
    occupancy_explains_old_miss,
    occupancy_holds_for_archive,
    recommend_nctx,
)
from scripts.eval import install_network_audit  # noqa: E402

N_CTXS = (16384, 32768, 65536)
OPERATIONAL_N_CTX = 65536
LOREM_FILLED_16K = {"hit_10": True, "hit_50": False, "hit_90": False}
COMPOSE_DIR_DEFAULT = "/home/simon/llama-cpp"
OVERRIDE_PATH = Path("/tmp/llama-nctx-override.yml")
GGUF_IN_CONTAINER = (
    "/root/.cache/huggingface/hub/models--unsloth--gemma-4-12b-it-GGUF/"
    "snapshots/d997c805aafe035a8024f961c6e1afd6b30d79a5/gemma-4-12b-it-UD-Q4_K_XL.gguf"
)
STABLE_WAIT_S = 120
WAIT_NCTX_S = 180
CHAT_TIMEOUT_S = 600


def canary_hit(completion: str, code: str) -> bool:
    return code in completion


def restore_compose_cmd(compose_dir: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(Path(compose_dir) / "docker-compose.yml"),
        "up",
        "-d",
    ]


def override_compose_cmd(compose_dir: str, override_file: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(Path(compose_dir) / "docker-compose.yml"),
        "-f",
        str(override_file),
        "up",
        "-d",
    ]


def write_override_yaml(path: Path, n_ctx: int) -> None:
    path.write_text(
        f"""services:
  llama-server:
    command: >
      -m {GGUF_IN_CONTAINER}
      --host 0.0.0.0
      --port 8000
      -c {n_ctx}
      --n-gpu-layers 99
      --jinja
      --reasoning off
      --cache-type-k q8_0
      --cache-type-v q8_0
      --no-mmap
      --parallel 1
      --temp 1.0
      --top-p 0.95
      --top-k 64
""",
        encoding="utf-8",
    )


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-2000:]
        print(err, file=sys.stderr, flush=True)
    return proc.returncode


def nvidia_memory() -> tuple[int | None, int | None]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None
    line = out.strip().splitlines()[0]
    used_s, total_s = [p.strip() for p in line.split(",")]
    return int(used_s), int(total_s)


def parse_docker_mem(text: str) -> float | None:
    m = re.match(r"([\d.]+)\s*([KMGT]i?B)", text.strip(), re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)[0].upper()
    mul = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024.0}
    return val * mul[unit]


def docker_mem_mib() -> float | None:
    try:
        out = subprocess.check_output(
            [
                "docker",
                "stats",
                "llama-server",
                "--no-stream",
                "--format",
                "{{.MemUsage}}",
            ],
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    used = out.strip().split("/")[0].strip()
    return parse_docker_mem(used)


def wait_n_ctx(origin: str, expected: int, timeout_s: float = WAIT_NCTX_S) -> bool:
    import httpx

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{origin}/props", timeout=5.0)
            resp.raise_for_status()
            n = resp.json().get("default_generation_settings", {}).get("n_ctx")
            if n == expected:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def fit_haystack(target_tokens: int, count) -> tuple[str, list[dict]]:
    word_count = lambda t: len(t.split())  # noqa: E731
    sample, _ = build_haystack(target_tokens=256, count=word_count)
    sample_n = count(sample)
    ratio = sample_n / 256.0
    guess = max(32, int(target_tokens / max(ratio, 0.05)))
    hay, places = build_haystack(target_tokens=guess, count=word_count)
    n = count(hay)
    for _ in range(6):
        if abs(n - target_tokens) <= max(32, int(target_tokens * 0.02)):
            break
        guess = max(32, int(guess * target_tokens / max(n, 1)))
        hay, places = build_haystack(target_tokens=guess, count=word_count)
        n = count(hay)
    measured = []
    for p in places:
        code = p["code"]
        prefix = hay[: hay.index(code)]
        measured.append({**p, "token_depth": count(prefix) / max(n, 1), "hay_tokens": n})
    return hay, measured


def chat_completion(origin: str, system: str, user: str, *, max_tokens: int) -> dict:
    import httpx

    payload = {
        "model": os.environ.get("BRF_LLM_MODEL", "gemma4:e12b"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
        "cache_prompt": True,
    }
    resp = httpx.post(
        f"{origin}/v1/chat/completions",
        json=payload,
        timeout=CHAT_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    text = ""
    choices = data.get("choices") or []
    if choices:
        text = ((choices[0].get("message") or {}).get("content")) or ""
    timings = data.get("timings") if isinstance(data.get("timings"), dict) else {}
    return {
        "text": text,
        "prompt_n": timings.get("prompt_n"),
        "prompt_ms": timings.get("prompt_ms"),
        "cache_n": timings.get("cache_n"),
    }


def slots_snapshot(origin: str) -> dict | None:
    import httpx

    try:
        resp = httpx.get(f"{origin}/slots", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    slot = data[0]
    return {
        "n_ctx": slot.get("n_ctx"),
        "n_prompt_tokens": slot.get("n_prompt_tokens"),
        "n_prompt_tokens_cache": slot.get("n_prompt_tokens_cache"),
    }


def _enforce_loopback(audit_log: list[dict]) -> None:
    external = [e for e in audit_log if not e.get("allowed", False)]
    if external:
        hosts = sorted({f"{e['host']}:{e['port']}" for e in external})
        raise SystemExit(
            f"NÄTVERKSREVISION MISSLYCKADES: {len(external)} extern(a) anslutning(ar). Värdar: {hosts}"
        )


def ask_needles(origin: str, runtime: LlamaCppRuntime, target_tokens: int) -> dict:
    hay, placements = fit_haystack(target_tokens, runtime.count)
    row: dict = {
        "target_tokens": target_tokens,
        "hay_tokens": placements[0]["hay_tokens"] if placements else None,
        "hit_10": False,
        "hit_50": False,
        "hit_90": False,
        "needles": [],
    }
    system = "Svara med enbart koden. Inget annat."
    for needle, key in zip(CANARIES, ("hit_10", "hit_50", "hit_90"), strict=True):
        user = hay + f"\n\nFRÅGA: Vilken kod står vid markören {needle['marker']}?"
        result = chat_completion(origin, system, user, max_tokens=64)
        hit = canary_hit(result["text"], needle["code"])
        row[key] = hit
        row["needles"].append(
            {
                "marker": needle["marker"],
                "depth": needle["depth"],
                "token_depth": next(
                    (p["token_depth"] for p in placements if p["marker"] == needle["marker"]),
                    None,
                ),
                "hit": hit,
                "prompt_n": result["prompt_n"],
                "prompt_ms": result["prompt_ms"],
                "cache_n": result["cache_n"],
            }
        )
    return row


def measure_one(origin: str, n_ctx: int, runtime: LlamaCppRuntime) -> dict:
    row: dict = {
        "n_ctx": n_ctx,
        "started": True,
        "stable": False,
        "hit_10": False,
        "hit_50": False,
        "hit_90": False,
        "vram_loaded_mib": None,
        "vram_full_mib": None,
        "gpu_total_mib": None,
        "ram_loaded_mib": None,
        "ram_full_mib": None,
        "kv_full": None,
        "kv_source": "vram_delta",
        "needles": [],
    }
    used, total = nvidia_memory()
    row["vram_loaded_mib"] = used
    row["gpu_total_mib"] = total
    row["ram_loaded_mib"] = docker_mem_mib()
    needles = ask_needles(origin, runtime, max(32, n_ctx - 256))
    row.update({k: needles[k] for k in ("target_tokens", "hay_tokens", "hit_10", "hit_50", "hit_90", "needles")})
    used_full, _ = nvidia_memory()
    row["vram_full_mib"] = used_full
    row["ram_full_mib"] = docker_mem_mib()
    row["slots_after"] = slots_snapshot(origin)
    time.sleep(STABLE_WAIT_S)
    try:
        tiny = chat_completion(origin, "Svara med ett ord.", "Hej?", max_tokens=16)
        row["stable"] = bool(tiny.get("text") is not None)
    except Exception:
        row["stable"] = False
    return row


def _restore_ops(compose_dir: str, origin: str) -> None:
    print(f"restoring n_ctx={OPERATIONAL_N_CTX}", file=sys.stderr, flush=True)
    _run(restore_compose_cmd(compose_dir))
    if not wait_n_ctx(origin, OPERATIONAL_N_CTX, timeout_s=WAIT_NCTX_S):
        print(f"RESTORE FAILED — /props n_ctx is not {OPERATIONAL_N_CTX}", file=sys.stderr, flush=True)
        sys.exit(2)


def run_filled_window(origin: str, base: str, compose_dir: str, out: Path) -> None:
    rows: list[dict] = []
    try:
        for n_ctx in N_CTXS:
            print(f"n_ctx={n_ctx} starting override", file=sys.stderr, flush=True)
            write_override_yaml(OVERRIDE_PATH, n_ctx)
            rc = _run(override_compose_cmd(compose_dir, str(OVERRIDE_PATH)))
            if rc != 0 or not wait_n_ctx(origin, n_ctx):
                rows.append(
                    {
                        "n_ctx": n_ctx,
                        "started": False,
                        "stable": False,
                        "hit_10": False,
                        "hit_50": False,
                        "hit_90": False,
                        "vram_full_mib": None,
                        "gpu_total_mib": nvidia_memory()[1],
                    }
                )
                print(f"n_ctx={n_ctx} started=false", file=sys.stderr, flush=True)
                continue
            runtime = LlamaCppRuntime(base)
            try:
                row = measure_one(origin, n_ctx, runtime)
            except Exception as exc:
                print(f"n_ctx={n_ctx} measure failed: {exc}", file=sys.stderr, flush=True)
                used, total = nvidia_memory()
                rows.append(
                    {
                        "n_ctx": n_ctx,
                        "started": True,
                        "stable": False,
                        "hit_10": False,
                        "hit_50": False,
                        "hit_90": False,
                        "vram_full_mib": used,
                        "gpu_total_mib": total,
                        "error": type(exc).__name__,
                    }
                )
                continue
            rows.append(row)
            print(
                f"n_ctx={n_ctx} started=true 10={row['hit_10']} 50={row['hit_50']} 90={row['hit_90']}",
                file=sys.stderr,
                flush=True,
            )
    finally:
        _restore_ops(compose_dir, origin)

    rec = recommend_nctx(rows)
    payload = {"mode": "filled-window", "rows": rows, "recommended": rec}
    (out / "run.json").write_text(json.dumps(payload), encoding="utf-8")
    rec_n = rec.get("n_ctx")
    (out / "recommended.txt").write_text("" if rec_n is None else str(rec_n), encoding="utf-8")
    print(json.dumps({"recommended_n_ctx": rec_n, "reason": rec.get("reason"), "discarded": rec.get("discarded")}), flush=True)


def run_occupancy(origin: str, base: str, compose_dir: str, out: Path) -> None:
    hay_rows: list[dict] = []
    used, total = nvidia_memory()
    server: dict = {
        "n_ctx": 65536,
        "started": False,
        "stable": False,
        "vram_loaded_mib": used,
        "vram_full_mib": None,
        "gpu_total_mib": total,
        "ram_loaded_mib": docker_mem_mib(),
        "ram_full_mib": None,
    }
    try:
        print("n_ctx=65536 occupancy override", file=sys.stderr, flush=True)
        write_override_yaml(OVERRIDE_PATH, 65536)
        rc = _run(override_compose_cmd(compose_dir, str(OVERRIDE_PATH)))
        if rc != 0 or not wait_n_ctx(origin, 65536):
            print("n_ctx=65536 started=false", file=sys.stderr, flush=True)
        else:
            server["started"] = True
            used, total = nvidia_memory()
            server["vram_loaded_mib"] = used
            server["gpu_total_mib"] = total
            server["ram_loaded_mib"] = docker_mem_mib()
            runtime = LlamaCppRuntime(base)
            for size in HAYSTACK_SIZES:
                print(f"haystack={size} starting", file=sys.stderr, flush=True)
                try:
                    row = ask_needles(origin, runtime, size)
                except Exception as exc:
                    print(f"haystack={size} failed: {exc}", file=sys.stderr, flush=True)
                    row = {
                        "target_tokens": size,
                        "hay_tokens": None,
                        "hit_10": False,
                        "hit_50": False,
                        "hit_90": False,
                        "needles": [],
                        "error": type(exc).__name__,
                    }
                hay_rows.append(row)
                print(
                    f"haystack={size} hay_tokens={row['hay_tokens']} "
                    f"10={row['hit_10']} 50={row['hit_50']} 90={row['hit_90']}",
                    file=sys.stderr,
                    flush=True,
                )
            used_full, _ = nvidia_memory()
            server["vram_full_mib"] = used_full
            server["ram_full_mib"] = docker_mem_mib()
            time.sleep(STABLE_WAIT_S)
            try:
                tiny = chat_completion(origin, "Svara med ett ord.", "Hej?", max_tokens=16)
                server["stable"] = bool(tiny.get("text") is not None)
            except Exception:
                server["stable"] = False
    finally:
        _restore_ops(compose_dir, origin)

    print("control haystack=16000 at n_ctx=16384", file=sys.stderr, flush=True)
    try:
        write_override_yaml(OVERRIDE_PATH, 16384)
        rc = _run(override_compose_cmd(compose_dir, str(OVERRIDE_PATH)))
        if rc != 0 or not wait_n_ctx(origin, 16384):
            raise RuntimeError("kunde inte starta n_ctx=16384 för 16k-kontroll")
        control = ask_needles(origin, LlamaCppRuntime(base), 16000)
    except Exception as exc:
        print(f"control 16k@16384 failed: {exc}", file=sys.stderr, flush=True)
        control = {
            "target_tokens": 16000,
            "hay_tokens": None,
            "hit_10": False,
            "hit_50": False,
            "hit_90": False,
            "needles": [],
            "error": type(exc).__name__,
        }
    finally:
        _restore_ops(compose_dir, origin)
    print(
        f"control 16k@16384 hay_tokens={control['hay_tokens']} "
        f"10={control['hit_10']} 50={control['hit_50']} 90={control['hit_90']}",
        file=sys.stderr,
        flush=True,
    )

    holds = occupancy_holds_for_archive([*hay_rows, server])
    unfilled = haystack_row(hay_rows, 16000) or {}
    payload = {
        "mode": "occupancy",
        "server": server,
        "haystacks": hay_rows,
        "control_16k_at_16384": control,
        "holds_for_archive": holds,
        "explains_vs_lorem": occupancy_explains_old_miss(
            filled_16k=LOREM_FILLED_16K, unfilled_16k_in_64k=unfilled
        ),
        "explains_vs_structured_control": occupancy_explains_old_miss(
            filled_16k=control, unfilled_16k_in_64k=unfilled
        ),
    }
    (out / "occupancy.json").write_text(json.dumps(payload), encoding="utf-8")
    print(json.dumps({"holds_for_archive": holds, "explains_vs_lorem": payload["explains_vs_lorem"]}), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("out/nctx-cost"))
    ap.add_argument("--compose-dir", default=COMPOSE_DIR_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mode", choices=("occupancy", "filled-window"), default="occupancy")
    args = ap.parse_args()

    if args.dry_run:
        hay, places = build_haystack(target_tokens=1000, count=lambda t: len(t.split()))
        report = {
            "dry_run": True,
            "mode": args.mode,
            "hay_words": 1000,
            "depths": [{"marker": p["marker"], "depth": p["depth"]} for p in places],
            "codes": [c["code"] for c in CANARIES],
            "lorem": "lorem" in hay.casefold(),
        }
        print(json.dumps(report), flush=True)
        return

    base = os.environ.get("BRF_LLM_BASE_URL", "").strip()
    if not base:
        raise SystemExit("BRF_LLM_BASE_URL saknas")
    origin = server_origin(base)
    audit_log, _allowed = install_network_audit()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mode == "filled-window":
        run_filled_window(origin, base, args.compose_dir, args.out)
    else:
        run_occupancy(origin, base, args.compose_dir, args.out)
    _enforce_loopback(audit_log)


if __name__ == "__main__":
    main()
