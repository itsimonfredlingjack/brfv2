"""Pin the deterministic span-derivation heuristics in
scripts/reality/fragment_facts.py: org-number (entity-name + number token),
party (role-label + party-block name), and cell-value (appendix row label +
value token). Synthetic fixtures only — no real corpus, matching the
reality-script convention (see test_reality_common.py) of never touching
real documents from the offline test suite.
"""

from __future__ import annotations

from app.schemas import Chunk
from scripts.reality.fragment_facts import (
    locate_cell_value,
    locate_org_number,
    locate_party,
)


def _chunk(text: str, *, page: int = 1, chunk_id: str = "doc:p1:0-0") -> Chunk:
    words = text.split()
    return Chunk(id=chunk_id, document_id="doc", page=page, word_start=0, word_end=len(words) - 1, text=text)


class TestLocateOrgNumber:
    def test_finds_entity_name_and_number_across_an_org_label(self):
        chunk = _chunk("Etikett: Test Företaget AB Org.nr 123456-7890 Övrig text")
        out = locate_org_number([chunk])
        assert len(out) == 1
        found_chunk, name, number = out[0]
        assert found_chunk is chunk
        assert name == "Test Företaget AB"
        assert number == "123456-7890"

    def test_finds_entity_name_immediately_before_the_number_no_label(self):
        # No "Org.nr"-shaped token between name and number at all (signature-
        # block style: name, then bare number) — the backward scan still
        # stops cleanly at the preceding colon-terminated boundary.
        chunk = _chunk("Rubrik: BRF TESTFORENINGEN 123456-7890 Sverige")
        out = locate_org_number([chunk])
        assert len(out) == 1
        _, name, number = out[0]
        assert name == "BRF TESTFORENINGEN"
        assert number == "123456-7890"

    def test_personnummer_shaped_token_does_not_match(self):
        # 8 digits before the hyphen (personnummer), not 6 — must not be
        # mistaken for an org number even though it looks similar.
        chunk = _chunk("Namn Person 19901231-1234 Sverige")
        assert locate_org_number([chunk]) == []

    def test_number_with_no_preceding_name_yields_no_candidate(self):
        chunk = _chunk("123456-7890 står ensamt i början")
        assert locate_org_number([chunk]) == []

    def test_name_fragment_is_capped_at_max_name_words(self):
        # Many capitalized words in a row before the number — the fragment
        # must not swallow an unrelated preceding caption.
        chunk = _chunk("Rubrik Foretaget Ett Tva Tre Org.nr 123456-7890")
        out = locate_org_number([chunk])
        assert len(out) == 1
        _, name, _ = out[0]
        assert name.split() == ["Foretaget", "Ett", "Tva", "Tre"]  # caps at 4, drops "Rubrik"

    def test_candidates_returned_in_document_order_across_chunks(self):
        chunk_a = _chunk("Part: Alfa AB Org.nr 111111-1111", page=1, chunk_id="doc:p1:0-0")
        chunk_b = _chunk("Part: Beta AB Org.nr 222222-2222", page=2, chunk_id="doc:p2:0-0")
        out = locate_org_number([chunk_a, chunk_b])
        assert [c.id for c, _, _ in out] == ["doc:p1:0-0", "doc:p2:0-0"]

    def test_no_match_in_chunk_without_org_number_shaped_token(self):
        chunk = _chunk("Det finns inget organisationsnummer här alls.")
        assert locate_org_number([chunk]) == []


class TestLocateParty:
    def test_finds_label_and_name_stopping_at_next_label(self):
        chunk = _chunk("Företag: Mitt Bolag AB Företag: Annat Bolag AB")
        out = locate_party([chunk])
        assert len(out) == 2
        _, name0, label0 = out[0]
        assert label0 == "Företag:"
        assert name0 == "Mitt Bolag AB"
        _, name1, _ = out[1]
        assert name1 == "Annat Bolag AB"

    def test_unrecognized_label_is_ignored(self):
        chunk = _chunk("Adress: Kungsgatan 1 Telefon: 08-1234567")
        assert locate_party([chunk]) == []

    def test_name_stops_before_an_org_label(self):
        chunk = _chunk("Uppdragsgivare: Bolag AB Org.nr 000000-0000")
        out = locate_party([chunk])
        assert len(out) == 1
        _, name, label = out[0]
        assert label == "Uppdragsgivare:"
        assert name == "Bolag AB"

    def test_label_with_no_following_words_yields_no_candidate(self):
        chunk = _chunk("Företag: Part: Nästa")
        out = locate_party([chunk])
        # "Företag:" is immediately followed by another label token, so its
        # name-run is empty and it is not a candidate.
        assert all(label != "Företag:" for _, _, label in out)

    def test_name_capped_at_max_name_words(self):
        chunk = _chunk("Kund: Ett Tva Tre Fyra Fem Sex Telefon: 08-000")
        out = locate_party([chunk])
        assert len(out) == 1
        _, name, _ = out[0]
        assert len(name.split()) == 4


class TestLocateCellValue:
    def test_finds_row_label_and_value(self):
        chunk = _chunk("X9.99.99 Skötsel av gemensamma utrymmen och ytor B X9.9 NASTA")
        out = locate_cell_value([chunk])
        assert len(out) == 1
        _, label, value = out[0]
        assert label == "Skötsel av gemensamma utrymmen och ytor"
        assert value == "B"

    def test_section_header_codes_are_not_leaf_rows(self):
        # "X9" and "X9.9" have 0/1 dotted segments — not leaf-level.
        chunk = _chunk("X9 RUBRIK X9.9 UNDERRUBRIK Text utan kod eller värde alls")
        assert locate_cell_value([chunk]) == []

    def test_single_word_description_is_rejected(self):
        chunk = _chunk("X9.99.99 Ensamt B")
        assert locate_cell_value([chunk]) == []

    def test_no_value_token_within_budget_skips_the_row(self):
        filler = " ".join(f"ord{i}" for i in range(20))  # exceeds MAX_DESC_WORDS
        chunk = _chunk(f"X9.99.99 {filler} B")
        assert locate_cell_value([chunk]) == []

    def test_multiple_leaf_rows_all_returned_in_order(self):
        chunk = _chunk(
            "X9.99.99 Forsta raden med text B X9.98.01 Andra raden med text JA"
        )
        out = locate_cell_value([chunk])
        assert len(out) == 2
        assert out[0][1] == "Forsta raden med text"
        assert out[0][2] == "B"
        assert out[1][1] == "Andra raden med text"
        assert out[1][2] == "JA"
