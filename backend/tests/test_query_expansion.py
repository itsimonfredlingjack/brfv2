"""Locks on the BRF-1 doc2query / query2doc measurement helpers.

The live eleven-case run is scripts/eval_brf1_query_expansion.py. These tests
use synthetic Swedish text only — no archive content.
"""

import json

from app.indexer import tokenize
from scripts.query_expansion import (
    QUERY2DOC_REPEATS,
    concatenate_query2doc,
    doc2query_prompt,
    expand_document_text,
    fit_document_bm25,
    format_four_angle_entry,
    four_angle_prompt,
    four_angle_selection_prompt,
    index_growth,
    isolated_selection_prompt,
    parse_four_angles,
    parse_passage,
    parse_questions,
    parse_selected_document,
    query2doc_prompt,
    rank_letters,
    token_contains,
    gold_in_package,
    hit_spread,
    overlay_descriptions,
    per_set_hit_counts,
    unique_text_counts,
    union_case,
    union_selected_ids,
    union_summary,
    view_fragor_prompt,
    view_reglerar_prompt,
    cumulative_union_counts,
)


def test_parse_questions_reads_json_list():
    raw = '{"questions": ["Vem betalar avgiften?", "När höjs priset?"]}'
    assert parse_questions(raw) == ["Vem betalar avgiften?", "När höjs priset?"]


def test_parse_questions_drops_blank_and_dedupes():
    raw = '{"questions": ["Samma?", "", "Samma?", "Annan?"]}'
    assert parse_questions(raw) == ["Samma?", "Annan?"]


def test_parse_passage_reads_json_or_raw():
    assert parse_passage('{"passage": "Hyresgästen ansvarar inte för skada."}') == (
        "Hyresgästen ansvarar inte för skada."
    )
    assert parse_passage("Ett kort stycke utan JSON.") == "Ett kort stycke utan JSON."


def test_query2doc_concat_repeats_query_five_times():
    out = concatenate_query2doc("vem betalar", "friskrivning vid parkering")
    assert QUERY2DOC_REPEATS == 5
    assert out == (
        "vem betalar vem betalar vem betalar vem betalar vem betalar "
        "friskrivning vid parkering"
    )


def test_query2doc_concat_once_for_description_selection():
    out = concatenate_query2doc("vem betalar", "friskrivning", repeats=1)
    assert out == "vem betalar friskrivning"


def test_doc2query_prompt_asks_for_board_language_not_legal_terms():
    system, user = doc2query_prompt("Avtalet fastställer administrationskostnad.", n=20)
    blob = f"{system}\n{user}"
    assert "styrelseledamot" in blob.lower() or "vardagliga" in blob.lower()
    assert "administrationskostnad" in user
    assert "20" in blob
    assert "questions" in blob


def test_query2doc_prompt_asks_for_a_swedish_passage():
    system, user = query2doc_prompt("Vem betalar om en bil får en skada på gården?")
    blob = f"{system}\n{user}"
    assert "gården" in user
    assert "stycke" in blob.lower() or "passage" in blob.lower()
    assert "svenska" in blob.lower()


def test_isolated_selection_prompt_lists_descriptions_not_titles():
    system, user = isolated_selection_prompt(
        [("A", "Reglerar bokföring."), ("G", "Reglerar parkering och friskrivning.")],
        "Vem betalar om en bil får en skada på gården?",
    )
    assert "Avtal.pdf" not in user
    assert "Reglerar parkering och friskrivning." in user
    assert "Reglerar bokföring." in user
    assert '{"document"' in system
    assert "1–3" not in system
    assert "FRÅGA:" in user


def test_parse_selected_document_reads_single_letter():
    assert parse_selected_document('{"document": "G"}', {"A", "G"}) == "G"
    assert parse_selected_document('{"documents": ["B"]}', {"A", "B"}) == "B"
    assert parse_selected_document("jag väljer C", {"A", "C"}) == "C"
    assert parse_selected_document("ingen", {"A", "G"}) is None


def test_bm25_misses_vocabulary_gap_until_doc2query_appends_questions():
    legal = "På varje faktura tillkommer administrationskostnad."
    distractor = "Extra avgift för jour. Fakturorna skickas varje månad."
    query = "extra avgift som läggs på fakturorna"
    letters = ["E", "B"]
    before = rank_letters(fit_document_bm25([legal, distractor]), query, letters)
    assert before[0] != "E"

    expanded = expand_document_text(
        legal, ["Vilken extra avgift läggs på fakturorna?"]
    )
    after = rank_letters(fit_document_bm25([expanded, distractor]), query, letters)
    assert after[0] == "E"


def test_bm25_query2doc_hits_when_pseudo_passage_uses_document_terms():
    parking = "Friskrivning i hyresavtalet för parkeringsplatser i garaget."
    other = "Sophämtning faktureras månadsvis med administrationskostnad."
    query = "vem står för kostnaden"
    letters = ["G", "E"]
    bm25 = fit_document_bm25([parking, other])
    expanded_query = concatenate_query2doc(
        query,
        "Friskrivning i hyresavtalet för parkeringsplatser i garaget.",
    )
    after = rank_letters(bm25, expanded_query, letters)
    assert after[0] == "G"
    scores = bm25.scores(tokenize(expanded_query))
    assert scores[0] > scores[1]


def test_index_growth_reports_tokens_per_document_and_total():
    before = ["avgift administrationskostnad", "felanmälan jour"]
    after = [
        expand_document_text(before[0], ["Vilken extra avgift läggs på fakturan?"]),
        before[1],
    ]
    growth = index_growth(before, after)
    assert growth["n_documents"] == 2
    assert growth["tokens_before"] == sum(len(tokenize(t)) for t in before)
    assert growth["tokens_after"] == sum(len(tokenize(t)) for t in after)
    assert growth["tokens_after"] > growth["tokens_before"]
    assert growth["per_document"][0]["tokens_added"] > 0
    assert growth["per_document"][1]["tokens_added"] == 0


def test_token_contains_uses_index_tokenizer():
    assert token_contains("Vem betalar om en bil får en skada på gården?", "bil")
    assert not token_contains("Hyresavtal för parkering i lokalen.", "gården")


def test_union_hits_counts_old_new_and_at_least_one():
    rows = [
        union_case("R1", "G", "G", "G"),
        union_case("R5", "E", "E", "C"),
        union_case("R3b", "G", "B", "G"),
        union_case("R6", "E", "C", "D"),
    ]
    summary = union_summary(rows)
    assert summary == {"old": 2, "new": 2, "union": 3, "n": 4}
    assert rows[1]["hit_old"] and not rows[1]["hit_new"]
    assert not rows[2]["hit_old"] and rows[2]["hit_new"]
    assert rows[2]["hit_union"]
    assert not rows[3]["hit_union"]


def test_four_angle_prompt_asks_for_four_distinct_views():
    system, user = four_angle_prompt("Avtalet fastställer administrationskostnad 494 kr.")
    blob = f"{system}\n{user}"
    assert "reglerar" in blob.lower()
    assert "parter" in blob.lower()
    assert "belopp" in blob.lower() or "pengar" in blob.lower()
    assert "frågor" in blob.lower()
    assert "administrationskostnad" in user
    assert "reglerar" in blob and "parter" in blob


def test_parse_four_angles_reads_four_short_fields():
    raw = json.dumps(
        {
            "reglerar": "Sophämtning och gårdsskötsel.",
            "fragor": "Vem betalar driftskostnaderna?",
            "parter": "Stena och föreningen.",
            "belopp": "Administrationskostnad 494 kr.",
        }
    )
    parsed = parse_four_angles(raw)
    assert parsed["reglerar"].startswith("Sophämtning")
    assert "driftskostnaderna" in parsed["fragor"]
    assert "Stena" in parsed["parter"]
    assert "494" in parsed["belopp"]


def test_format_four_angle_entry_lists_all_four_under_the_letter():
    block = format_four_angle_entry(
        "E",
        {
            "reglerar": "Sophämtning.",
            "fragor": "Vem betalar?",
            "parter": "Stena och föreningen.",
            "belopp": "494 kr.",
        },
    )
    assert block.startswith("E.")
    assert "Sophämtning." in block
    assert "Vem betalar?" in block
    assert "Stena och föreningen." in block
    assert "494 kr." in block
    assert "Avtal.pdf" not in block


def test_four_angle_selection_prompt_shows_all_angles_not_titles():
    system, user = four_angle_selection_prompt(
        [
            (
                "G",
                {
                    "reglerar": "Parkering.",
                    "fragor": "Vem ansvarar vid skada?",
                    "parter": "Hyresvärd och hyresgäst.",
                    "belopp": "60 000 kr per kvartal.",
                },
            )
        ],
        "Vem betalar om en bil får en skada på gården?",
    )
    assert "Avtal.pdf" not in user
    assert "Parkering." in user
    assert "60 000 kr per kvartal." in user
    assert '{"document"' in system
    assert "1–3" not in system
    assert "FRÅGA:" in user


class _Meta:
    def __init__(self, description: str) -> None:
        self.description = description

    def model_copy(self, *, update: dict) -> "_Meta":
        return _Meta(update.get("description", self.description))


def test_two_view_prompts_are_standalone_and_not_the_same_text():
    text = "Avtalet fastställer administrationskostnad 494 kr."
    sys_a, user_a = view_reglerar_prompt(text)
    sys_b, user_b = view_fragor_prompt(text)
    blob_a = f"{sys_a}\n{user_a}"
    blob_b = f"{sys_b}\n{user_b}"
    assert sys_a != sys_b
    assert '{"description"' in sys_a
    assert '{"description"' in sys_b
    assert '"reglerar"' not in blob_a and '"parter"' not in blob_a
    assert '"reglerar"' not in blob_b and '"parter"' not in blob_b
    assert "reglerar" in sys_a.lower()
    assert "styrelseledamot" in sys_b.lower() or "vardagliga" in sys_b.lower()
    assert "494" in user_a and "494" in user_b
    assert "Avtal.pdf" not in blob_a and "Avtal.pdf" not in blob_b
    from app.document_describe import description_prompt

    prod, _ = description_prompt("titel", text)
    assert "Du beskriver vad en föreningshandling reglerar" not in sys_a
    assert "Du beskriver vad en föreningshandling reglerar" not in sys_b
    assert sys_a != prod and sys_b != prod


def test_overlay_descriptions_replaces_text_without_mutating_source():
    source = {"e1": _Meta("gammal")}
    overlaid = overlay_descriptions(source, {"e1": "ny vy"})
    assert source["e1"].description == "gammal"
    assert overlaid["e1"].description == "ny vy"
    assert overlaid is not source


def test_union_selected_ids_keeps_first_order_and_appends_new():
    assert union_selected_ids(["C", "D", "E"], ["E", "G"]) == ["C", "D", "E", "G"]
    assert union_selected_ids(["G"], ["G"]) == ["G"]
    assert union_selected_ids(["B"], ["E"]) == ["B", "E"]
    assert union_selected_ids([], ["E"]) == ["E"]


def test_gold_in_package_is_membership_not_first_only():
    assert gold_in_package("E", ["C", "D", "E"]) is True
    assert gold_in_package("E", ["C", "D"]) is False
    assert gold_in_package("G", ["G"]) is True


def test_per_set_hit_counts_are_independent():
    golds = {"R1": "G", "R5": "E", "R7": "E", "R3b": "G"}
    sets = [
        {"R1": "G", "R5": "C", "R7": "B", "R3b": "G"},
        {"R1": "G", "R5": "E", "R7": "B", "R3b": "B"},
        {"R1": "G", "R5": "C", "R7": "B", "R3b": "G"},
    ]
    assert per_set_hit_counts(sets, golds) == [2, 2, 2]


def test_cumulative_union_climbs_then_can_plateau():
    golds = {"R1": "G", "R5": "E", "R6": "E", "R7": "E", "R3b": "G", "R7b": "E"}
    sets = [
        {"R1": "G", "R5": "C", "R6": "C", "R7": "B", "R3b": "B", "R7b": "A"},
        {"R1": "G", "R5": "E", "R6": "C", "R7": "B", "R3b": "G", "R7b": "A"},
        {"R1": "G", "R5": "E", "R6": "E", "R7": "B", "R3b": "G", "R7b": "A"},
        {"R1": "G", "R5": "C", "R6": "C", "R7": "B", "R3b": "G", "R7b": "A"},
        {"R1": "G", "R5": "C", "R6": "C", "R7": "B", "R3b": "G", "R7b": "A"},
    ]
    assert cumulative_union_counts(sets, golds) == [1, 3, 4, 4, 4]


def test_hit_spread_reports_min_max_and_span():
    assert hit_spread([7, 6, 8, 7, 7]) == {"min": 6, "max": 8, "span": 2, "values": [7, 6, 8, 7, 7]}


def test_unique_text_counts_per_letter_without_storing_the_texts():
    sets = [
        {"E": "avgift 494", "G": "parkering"},
        {"E": "avgift 494", "G": "fordon och skada"},
        {"E": "annan text", "G": "parkering"},
    ]
    assert unique_text_counts(sets) == {"E": 2, "G": 2}