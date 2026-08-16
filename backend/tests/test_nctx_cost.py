from app.needle_haystack import CANARIES, build_haystack, recommend_nctx


def _count(text: str) -> int:
    return len(text.split())


def test_canaries_overwrite_at_10_50_90_percent():
    hay, placements = build_haystack(target_tokens=1000, count=_count)
    assert _count(hay) == 1000
    by_marker = {p["marker"]: p for p in placements}
    for needle in CANARIES:
        p = by_marker[needle["marker"]]
        assert needle["code"] in hay
        assert abs(p["depth"] - needle["depth"]) <= 0.02
        prefix = hay[: hay.index(needle["code"])]
        assert abs(_count(prefix) / 1000 - needle["depth"]) <= 0.02


def test_recommend_smallest_that_hits_all_three_depths():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 10000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
    assert rec["reason"] == "smallest_all_depths"


def test_recommend_drops_larger_window_that_loses_90_percent():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 11000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
    assert 65536 in rec["discarded"]


def test_recommend_prefers_window_that_hits_all_three_over_smaller_that_misses_90():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 10000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 32768


def test_recommend_disqualifies_65536_with_under_1gib_free():
    rows = [
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 9000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 12000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 32768
    assert 65536 in rec["discarded"]


def test_recommend_ignores_nctx_that_did_not_start():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": False, "stable": False, "hit_10": False, "hit_50": False, "hit_90": False, "vram_full_mib": None, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
