"""Synthetic needle-in-haystack prompts and n_ctx recommendation rules."""

from __future__ import annotations

CANARIES = (
    {"depth": 0.10, "marker": "ALPHA", "code": "NEEDLE10-A7K3M2"},
    {"depth": 0.50, "marker": "MID", "code": "NEEDLE50-P9Q4W1"},
    {"depth": 0.90, "marker": "OMEGA", "code": "NEEDLE90-Z2R8C5"},
)
FILLER_WORD = "lorem"
GPU_FREE_MIN_MIB = 1024


def build_haystack(*, target_tokens: int, count) -> tuple[str, list[dict]]:
    if target_tokens < 32:
        raise ValueError("target_tokens too small")
    words = [FILLER_WORD] * target_tokens
    placements = []
    for needle in CANARIES:
        payload = f"Markor {needle['marker']} {needle['code']}".split()
        start = int(needle["depth"] * target_tokens)
        if start + len(payload) > target_tokens:
            start = target_tokens - len(payload)
        words[start : start + len(payload)] = payload
        prefix_words = words[:start]
        depth = len(prefix_words) / target_tokens
        placements.append({**needle, "start": start, "depth": depth})
    hay = " ".join(words)
    if count(hay) != target_tokens:
        raise RuntimeError("haystack token count drifted")
    return hay, placements


def recommend_nctx(rows: list[dict]) -> dict:
    discarded: list[int] = []
    alive = []
    for r in rows:
        if not r.get("started") or not r.get("stable"):
            discarded.append(r["n_ctx"])
            continue
        free = (r.get("gpu_total_mib") or 0) - (r.get("vram_full_mib") or 0)
        if r["n_ctx"] == 65536 and free < GPU_FREE_MIN_MIB:
            discarded.append(r["n_ctx"])
            continue
        alive.append(r)
    hit90 = [r for r in alive if r.get("hit_90")]
    if hit90:
        smallest_90 = min(r["n_ctx"] for r in hit90)
        kept = []
        for r in alive:
            if not r.get("hit_90") and r["n_ctx"] > smallest_90:
                discarded.append(r["n_ctx"])
            else:
                kept.append(r)
        alive = kept
    all_three = [r for r in alive if r.get("hit_10") and r.get("hit_50") and r.get("hit_90")]
    if all_three:
        chosen = min(all_three, key=lambda r: r["n_ctx"])
        return {"n_ctx": chosen["n_ctx"], "reason": "smallest_all_depths", "discarded": discarded}
    if not alive:
        return {"n_ctx": None, "reason": "none_started", "discarded": discarded}

    def depth_score(r: dict) -> tuple[int, int]:
        deepest = (1 if r.get("hit_10") else 0) + (2 if r.get("hit_50") else 0) + (4 if r.get("hit_90") else 0)
        return (deepest, -r["n_ctx"])

    chosen = max(alive, key=depth_score)
    return {"n_ctx": chosen["n_ctx"], "reason": "deepest_then_smallest", "discarded": discarded}
