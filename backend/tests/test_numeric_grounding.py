"""Unit tests for app/numeric_grounding.py: does a number asserted in the
answer text reappear, after normalization, among the numbers in the
verified citation quotes it's shown alongside?

See tests/test_answer.py::TestNumericGroundingGate for the full ask()
pipeline integration (repair attempt, refusal wiring, prompt content)."""

from decimal import Decimal

from app.numeric_grounding import check_numeric_grounding, describe_mismatch, extract_numbers

NBSP = " "  # no-break space
NNBSP = " "  # narrow no-break space


class TestExtractNumbers:
    def test_bare_integer(self):
        [n] = extract_numbers("56 lägenheter")
        assert n.value == Decimal("56") and not n.is_percent

    def test_space_grouped_thousands(self):
        [n] = extract_numbers("Total utgift 15 659 566 kr")
        assert n.value == Decimal("15659566")

    def test_nbsp_grouped_thousands_equals_regular_space(self):
        # U+00A0 no-break space — Swedish financial PDF exports often embed
        # this INSIDE a number so it never wraps across a line.
        [n] = extract_numbers(f"Total utgift 15{NBSP}659{NBSP}566 kr")
        assert n.value == Decimal("15659566")

    def test_narrow_nbsp_grouped_thousands_equals_regular_space(self):
        [n] = extract_numbers(f"Total utgift 15{NNBSP}659{NNBSP}566 kr")
        assert n.value == Decimal("15659566")

    def test_decimal_comma(self):
        [n] = extract_numbers("151,5 kr per m²")
        assert n.value == Decimal("151.5")

    def test_decimal_point(self):
        [n] = extract_numbers("151.5 kr per m²")
        assert n.value == Decimal("151.5")

    def test_percent_sign_is_a_distinct_claim(self):
        [n] = extract_numbers("8,5 %")
        assert n.value == Decimal("8.5") and n.is_percent

    def test_percent_and_bare_number_do_not_share_identity(self):
        pct = extract_numbers("8 %")[0]
        bare = extract_numbers("8 lägenheter")[0]
        assert pct.value == bare.value
        assert pct.is_percent != bare.is_percent

    def test_year(self):
        [n] = extract_numbers("Underhållsplan år 2032")
        assert n.value == Decimal("2032")

    def test_range_splits_into_two_endpoints(self):
        ns = extract_numbers("Planen gäller 2024-2053")
        assert [str(n.value) for n in ns] == ["2024", "2053"]

    def test_hyphenated_id_splits_symmetrically(self):
        # Same rule applied to both sides of a comparison is what matters —
        # not that this matches any particular real-world id semantics.
        ns = extract_numbers("Organisationsnummer 769621-4455")
        assert [str(n.value) for n in ns] == ["769621", "4455"]

    def test_multiple_numbers_in_order(self):
        ns = extract_numbers("Investering 6 281 649 kr, underhåll 9 377 917 kr")
        assert [str(n.value) for n in ns] == ["6281649", "9377917"]

    def test_no_numbers_returns_empty(self):
        assert extract_numbers("Styrelsen sammanträder varje kvartal.") == []

    def test_empty_string_returns_empty(self):
        assert extract_numbers("") == []


class TestCheckNumericGrounding:
    def test_exact_match_passes(self):
        result = check_numeric_grounding("Total utgift 15 659 566 kr.", ["Total utgift 15 659 566 kr"])
        assert result.ok and result.unsupported == []

    def test_transposed_digits_fails(self):
        # The exact reported production defect.
        result = check_numeric_grounding("Summan är 1 565 956 kr.", ["Total utgift 15 659 566 kr"])
        assert not result.ok
        assert result.unsupported[0].value == Decimal("1565956")

    def test_nbsp_in_quote_still_supports_regular_space_answer(self):
        result = check_numeric_grounding(
            "Total utgift 15 659 566 kr.", [f"Total utgift 15{NBSP}659{NBSP}566 kr"]
        )
        assert result.ok

    def test_narrow_nbsp_in_answer_still_matches_regular_space_quote(self):
        result = check_numeric_grounding(
            f"Total utgift 15{NNBSP}659{NNBSP}566 kr.", ["Total utgift 15 659 566 kr"]
        )
        assert result.ok

    def test_all_three_whitespace_variants_are_mutually_equivalent(self):
        # The task's own three "identical-looking" examples: regular space,
        # NBSP, narrow NBSP — every pairing must cross-validate.
        variants = [
            "15 659 566",
            f"15{NBSP}659{NBSP}566",
            f"15{NNBSP}659{NNBSP}566",
        ]
        for answer_variant in variants:
            for quote_variant in variants:
                result = check_numeric_grounding(f"Summan är {answer_variant} kr.", [f"{quote_variant} kr"])
                assert result.ok, f"{answer_variant!r} vs {quote_variant!r}"

    def test_percentage_mismatch_fails_even_if_bare_value_appears_elsewhere(self):
        result = check_numeric_grounding("Andelen är 8 %.", ["Antalet ärenden var 8 st"])
        assert not result.ok

    def test_number_only_in_unrelated_support_text_does_not_count(self):
        result = check_numeric_grounding("Kostnaden är 42 kr.", ["Ersättningen är oförändrad"])
        assert not result.ok

    def test_no_numbers_in_answer_passes_trivially_even_with_no_support(self):
        result = check_numeric_grounding("Inga tal nämns här alls.", [])
        assert result.ok

    def test_multiple_claims_each_supported_by_a_different_quote(self):
        result = check_numeric_grounding(
            "56 lägenheter till en kostnad av 151 kr per m² och år.",
            ["Föreningen har 56 lägenheter", "Avgiften är 151 kr per m² och år"],
        )
        assert result.ok

    def test_one_of_several_claims_unsupported_fails_the_whole_answer(self):
        result = check_numeric_grounding(
            "56 lägenheter till en kostnad av 999 kr per m² och år.",
            ["Föreningen har 56 lägenheter", "Avgiften är 151 kr per m² och år"],
        )
        assert not result.ok
        assert result.unsupported[0].value == Decimal("999")


class TestDescribeMismatch:
    def test_lists_raw_unsupported_numbers_deduplicated(self):
        result = check_numeric_grounding(
            "Priset var 999 kr, sedan 999 kr igen och 42 kr.", ["Priset var 151 kr"]
        )
        msg = describe_mismatch(result)
        assert "999" in msg and "42" in msg
        assert msg.count("999") == 1
