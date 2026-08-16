from app.needle_haystack import (
    CANARIES,
    HAYSTACK_SIZES,
    build_haystack,
    occupancy_explains_old_miss,
    occupancy_holds_for_archive,
    recommend_nctx,
)
from scripts.measure_nctx_cost import canary_hit, override_compose_cmd, restore_compose_cmd


def _count(text: str) -> int:
    return len(text.split())


def test_haystack_uses_structured_filler_not_lorem():
    hay, _ = build_haystack(target_tokens=1000, count=_count)
    words = hay.split()
    assert "lorem" not in hay.casefold()
    assert "Avsnitt" in words
    assert words.count("Avsnitt") >= 8
    assert len(set(words)) >= 12


def test_haystack_sizes_are_occupancy_sweep():
    assert HAYSTACK_SIZES == (8000, 16000, 32000, 48000, 62000)


def test_occupancy_holds_when_48k_hits_one_depth():
    rows = [
        {"hay_tokens": 8000, "hit_10": True, "hit_50": True, "hit_90": True},
        {"hay_tokens": 48000, "hit_10": True, "hit_50": False, "hit_90": False},
        {"n_ctx": 65536, "started": True, "stable": True, "vram_full_mib": 8300, "gpu_total_mib": 12282},
    ]
    rec = occupancy_holds_for_archive(rows)
    assert rec["holds"] is True
    assert rec["reason"] == "48k_hit"


def test_occupancy_does_not_hold_when_48k_misses_all():
    rows = [
        {"hay_tokens": 16000, "hit_10": True, "hit_50": True, "hit_90": True},
        {"hay_tokens": 48000, "hit_10": False, "hit_50": False, "hit_90": False},
        {"n_ctx": 65536, "started": True, "stable": True, "vram_full_mib": 8300, "gpu_total_mib": 12282},
    ]
    rec = occupancy_holds_for_archive(rows)
    assert rec["holds"] is False
    assert rec["reason"] == "48k_miss"


def test_occupancy_explains_old_miss_when_16k_in_64k_hits_deeper():
    filled = {"hit_10": True, "hit_50": False, "hit_90": False}
    unfilled = {"hit_10": True, "hit_50": True, "hit_90": False}
    assert occupancy_explains_old_miss(filled_16k=filled, unfilled_16k_in_64k=unfilled) is True
    assert occupancy_explains_old_miss(filled_16k=filled, unfilled_16k_in_64k=filled) is False


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


def test_canary_hit_is_exact_substring():
    assert canary_hit("foo NEEDLE10-A7K3M2 bar", "NEEDLE10-A7K3M2") is True
    assert canary_hit("NEEDLE10-A7K3M2XXXX", "NEEDLE10-A7K3M2") is True
    assert canary_hit("NEEDLE50-P9Q4W1", "NEEDLE10-A7K3M2") is False


def test_restore_compose_cmd_has_no_override_file():
    cmd = restore_compose_cmd("/home/simon/llama-cpp")
    assert cmd == ["docker", "compose", "-f", "/home/simon/llama-cpp/docker-compose.yml", "up", "-d"]


def test_override_cmd_includes_tmp_file_and_nctx():
    cmd = override_compose_cmd("/home/simon/llama-cpp", "/tmp/llama-nctx.yml")
    assert cmd[:4] == ["docker", "compose", "-f", "/home/simon/llama-cpp/docker-compose.yml"]
    assert "/tmp/llama-nctx.yml" in cmd


def test_lorem_filled_16k_matches_first_evidence():
    from scripts.measure_nctx_cost import LOREM_FILLED_16K

    assert LOREM_FILLED_16K == {"hit_10": True, "hit_50": False, "hit_90": False}


def test_document_kind_from_filename():
    from scripts.live_document_ask import document_kind

    assert document_kind("Stadgar Brf.pdf") == "stadgar"
    assert document_kind("Årsredovisning 2024.pdf") == "annual_report"
    assert document_kind("arsredovisning.pdf") == "annual_report"
    assert document_kind("Avtal ekonomisk forvaltning.pdf") == "other"

