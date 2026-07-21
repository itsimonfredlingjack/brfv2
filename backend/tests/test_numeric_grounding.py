"""Unit tests for app/numeric_grounding.py: does a number asserted in the
answer text reappear, after normalization, among the numbers in the
verified citation quotes it's shown alongside?

See tests/test_answer.py::TestNumericGroundingGate for the full ask()
pipeline integration (repair attempt, refusal wiring, prompt content)."""

from decimal import Decimal

from app.numeric_grounding import (
    check_numeric_grounding,
    describe_mismatch,
    extract_numbers,
    mask_trusted_spans,
)

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


class TestPeriodGroupedThousands:
    """Period-grouped thousands ("15.659.566") vs. a genuine decimal
    ("15.5") — SPEC 2.10 follow-up normalization gap."""

    def test_period_grouped_thousands_parses_as_one_value(self):
        [n] = extract_numbers("Total utgift 15.659.566 kr")
        assert n.value == Decimal("15659566")

    def test_period_grouped_thousands_matches_space_grouped(self):
        result = check_numeric_grounding("Total utgift 15.659.566 kr.", ["Total utgift 15 659 566 kr"])
        assert result.ok

    def test_genuine_decimal_stays_a_decimal(self):
        [n] = extract_numbers("Arean är 15.5 kvadratmeter")
        assert n.value == Decimal("15.5")

    def test_genuine_decimal_does_not_match_a_thousands_value(self):
        result = check_numeric_grounding("Arean är 15.5 kvadratmeter.", ["Arean är 155 kvadratmeter"])
        assert not result.ok


class TestProcentWord:
    """The Swedish word "procent" must be recognized as equivalent to "%",
    while a bare number stays a distinct claim from its percent form."""

    def test_procent_word_is_a_percent_claim(self):
        [n] = extract_numbers("25 procent")
        assert n.value == Decimal("25") and n.is_percent

    def test_procent_word_matches_percent_sign(self):
        result = check_numeric_grounding("Andelen är 25 procent.", ["Andelen uppgår till 25 %"])
        assert result.ok

    def test_percent_sign_matches_procent_word(self):
        result = check_numeric_grounding("Andelen är 25 %.", ["Andelen uppgår till 25 procent"])
        assert result.ok

    def test_bare_number_remains_distinct_from_percent_form(self):
        result = check_numeric_grounding("Andelen är 25 procent.", ["Det finns 25 lägenheter"])
        assert not result.ok

    def test_procent_inside_a_longer_word_is_not_mistaken_for_the_marker(self):
        # "procentuellt" must not be parsed as "25" + a dangling "procent"
        # marker that happens to prefix-match — the number is bare here.
        [n] = extract_numbers("En ökning på 25 procentuellt sett stor.")
        assert n.value == Decimal("25") and not n.is_percent


class TestMaskTrustedSpans:
    """Pure masking behavior — see TestCheckNumericGroundingWithTrustedNames
    for the identity-comparison-level guarantees this feeds into."""

    def test_exact_span_is_masked(self):
        out = mask_trusted_spans("brf gjutformen 12 har manga medlemmar", ["Brf Gjutformen 12"])
        assert "12" not in out
        assert "gjutformen" not in out

    def test_masked_span_replaced_with_spaces_not_deleted(self):
        text = "brf gjutformen 12 har manga medlemmar"
        out = mask_trusted_spans(text, ["brf gjutformen 12"])
        assert len(out) == len(text)

    def test_no_trusted_names_is_a_no_op(self):
        text = "brf gjutformen 12 har manga medlemmar"
        assert mask_trusted_spans(text, []) == text

    def test_wrong_numeric_identifier_is_not_masked(self):
        # "123" is NOT "12" — the trusted span must not partially match.
        out = mask_trusted_spans("brf gjutformen 123 ar okand", ["brf gjutformen 12"])
        assert "123" in out

    def test_partial_name_prefix_is_not_masked(self):
        out = mask_trusted_spans("brf gjutformen 12an ar okand", ["brf gjutformen 12"])
        assert "12an" in out

    def test_repeated_mentions_all_masked(self):
        out = mask_trusted_spans(
            "brf gjutformen 12 traffade brf gjutformen 12 igen", ["brf gjutformen 12"]
        )
        assert "12" not in out

    def test_case_and_normalization_already_applied_by_caller(self):
        # mask_trusted_spans normalizes trusted_names itself, but expects
        # `text` to already be normalized (check_numeric_grounding's job).
        out = mask_trusted_spans("brf gjutformen 12 ligger i orebro", ["BRF GJUTFORMEN 12"])
        assert "12" not in out


class TestCheckNumericGroundingWithTrustedNames:
    """End-to-end (pure function level) proof of the false-refusal fix: a
    verified tenant name containing a digit must not be treated as an
    unsupported numeric claim, while every other invariant (wrong number,
    fabricated name, question text, separate claims) still refuses exactly
    as before."""

    def test_exact_tenant_name_with_identifier_passes(self):
        result = check_numeric_grounding(
            "BRF GJUTFORMEN 12 har sitt säte i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_casefolded_tenant_name_passes(self):
        result = check_numeric_grounding(
            "brf gjutformen 12 har sitt säte i göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_nbsp_variant_in_tenant_name_passes(self):
        result = check_numeric_grounding(
            f"BRF{NBSP}GJUTFORMEN{NBSP}12 har sitt säte i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_narrow_nbsp_variant_in_tenant_name_passes(self):
        result = check_numeric_grounding(
            f"BRF{NNBSP}GJUTFORMEN{NNBSP}12 har sitt säte i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_surrounding_punctuation_passes(self):
        result = check_numeric_grounding(
            "Enligt stadgarna heter föreningen Brf Gjutformen 12, med säte i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_repeated_exact_mentions_pass(self):
        result = check_numeric_grounding(
            "Brf Gjutformen 12 grundades i Göteborg. Brf Gjutformen 12 har sitt säte där.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_partial_tenant_name_match_does_not_exempt_the_number(self):
        # "Gjutformen 12" alone (missing "Brf") is not the trusted span.
        result = check_numeric_grounding(
            "Gjutformen 12 grundades i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert not result.ok

    def test_fabricated_tenant_name_does_not_exempt_the_number(self):
        result = check_numeric_grounding(
            "Falska Föreningen 99 grundades i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert not result.ok
        assert result.unsupported[0].value == Decimal("99")

    def test_wrong_number_in_tenant_name_does_not_pass(self):
        result = check_numeric_grounding(
            "Brf Gjutformen 13 grundades i Göteborg.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert not result.ok
        assert result.unsupported[0].value == Decimal("13")

    def test_same_number_outside_the_exact_span_remains_unsupported(self):
        # "12" appears both inside the trusted span AND as a separate,
        # unrelated claim later in the sentence — the second occurrence must
        # still require citation support.
        result = check_numeric_grounding(
            "Brf Gjutformen 12 har 12 anställda.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert not result.ok
        assert result.unsupported[0].value == Decimal("12")

    def test_tenant_name_plus_separate_unsupported_quantity_fails(self):
        result = check_numeric_grounding(
            "Brf Gjutformen 12 har 56 lägenheter.",
            ["Föreningen grundades i Göteborg"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert not result.ok
        assert result.unsupported[0].value == Decimal("56")

    def test_tenant_name_plus_supported_quantity_passes(self):
        result = check_numeric_grounding(
            "Brf Gjutformen 12 har 56 lägenheter.",
            ["Föreningen har 56 lägenheter"],
            trusted_names=["Brf Gjutformen 12"],
        )
        assert result.ok

    def test_arbitrary_numbers_from_the_question_are_never_trusted(self):
        # Passing the question text itself as a "trusted name" is exactly
        # the misuse this gate must resist — proves trusted_names is not a
        # generic escape hatch, only exact whole-span matches count, and the
        # caller is what decides what's trusted (never done here).
        result = check_numeric_grounding(
            "Kostnaden är 999 kr.",
            ["Priset är oförändrat"],
            trusted_names=["Vad kostar det, 999 kr eller mer?"],
        )
        assert not result.ok
