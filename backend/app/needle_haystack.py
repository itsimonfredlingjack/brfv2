"""Synthetic needle-in-haystack prompts and n_ctx recommendation rules."""

from __future__ import annotations

CANARIES = (
    {"depth": 0.10, "marker": "ALPHA", "code": "NEEDLE10-A7K3M2"},
    {"depth": 0.50, "marker": "MID", "code": "NEEDLE50-P9Q4W1"},
    {"depth": 0.90, "marker": "OMEGA", "code": "NEEDLE90-Z2R8C5"},
)
HAYSTACK_SIZES = (8000, 16000, 32000, 48000, 62000)
GPU_FREE_MIN_MIB = 1024
STRUCTURE_VOCAB = (
    "styrelsen",
    "rakenskap",
    "avgift",
    "underhall",
    "fonden",
    "lanet",
    "amortering",
    "byggnaden",
    "marken",
    "kassan",
    "skulden",
    "rantan",
    "motet",
    "stamma",
    "ledamot",
    "revisor",
    "budget",
    "kostnad",
    "intakt",
    "kapital",
    "anlaggning",
    "omsattning",
    "avskrivning",
    "lagenhet",
    "garage",
    "vatten",
    "fiber",
    "sophantering",
)
HEADER_EVERY = 48


def structured_filler_words(n: int) -> list[str]:
    if n < 1:
        return []
    headers = (
        ("Avsnitt", "Forvaltning"),
        ("Avsnitt", "Resultat"),
        ("Avsnitt", "Balans"),
        ("Avsnitt", "Noter"),
    )
    out: list[str] = []
    vocab_i = 0
    header_i = 0
    while len(out) < n:
        if len(out) % HEADER_EVERY == 0:
            pair = headers[header_i % len(headers)]
            header_i += 1
            for token in pair:
                if len(out) >= n:
                    break
                out.append(token)
            continue
        out.append(STRUCTURE_VOCAB[vocab_i % len(STRUCTURE_VOCAB)])
        vocab_i += 1
    return out[:n]


def build_haystack(*, target_tokens: int, count) -> tuple[str, list[dict]]:
    if target_tokens < 32:
        raise ValueError("target_tokens too small")
    words = structured_filler_words(target_tokens)
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


def haystack_row(rows: list[dict], size: int) -> dict | None:
    exact = [r for r in rows if r.get("target_tokens") == size]
    if exact:
        return exact[0]
    slop = max(512, int(size * 0.05))
    near = [r for r in rows if abs((r.get("hay_tokens") or 0) - size) <= slop]
    return near[0] if near else None


def occupancy_holds_for_archive(rows: list[dict]) -> dict:
    server = next((r for r in rows if r.get("n_ctx") == 65536), None)
    if server is None:
        server = next((r for r in rows if "started" in r), {}) or {}
    if not server.get("started", True):
        return {"holds": False, "reason": "not_started"}
    if server.get("stable") is False:
        return {"holds": False, "reason": "unstable"}
    total = server.get("gpu_total_mib")
    used = server.get("vram_full_mib")
    if total and used is not None and (total - used) < GPU_FREE_MIN_MIB:
        return {"holds": False, "reason": "gpu_low"}
    hay = haystack_row(rows, 48000)
    if hay is None:
        return {"holds": False, "reason": "48k_missing"}
    if hay.get("hit_10") or hay.get("hit_50") or hay.get("hit_90"):
        return {"holds": True, "reason": "48k_hit"}
    return {"holds": False, "reason": "48k_miss"}


def occupancy_explains_old_miss(*, filled_16k: dict, unfilled_16k_in_64k: dict) -> bool:
    for key in ("hit_50", "hit_90"):
        if unfilled_16k_in_64k.get(key) and not filled_16k.get(key):
            return True
    return False
