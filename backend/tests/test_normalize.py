from app.normalize import canonical_stream, find_spans, norm_token, normalize_text


class TestNormalizeText:
    def test_nfkc_ligature(self):
        assert normalize_text("ﬁnansiering") == "finansiering"

    def test_nbsp_and_thin_space(self):
        assert normalize_text("1 250 kr") == "1 250 kr"

    def test_soft_hyphen_removed(self):
        assert normalize_text("för­valtning") == "förvaltning"

    def test_typographic_quotes_and_dashes(self):
        assert normalize_text("”citat” – tanke") == '"citat" - tanke'

    def test_casefold_swedish(self):
        assert normalize_text("ÅRSAVGIFT Ö") == "årsavgift ö"


class TestNormToken:
    def test_strips_edge_punctuation(self):
        assert norm_token("system.") == "system"
        assert norm_token("(styrelsen),") == "styrelsen"
        assert norm_token("§1.") == "1"

    def test_keeps_trailing_hyphen(self):
        assert norm_token("för-") == "för-"
        assert norm_token("för-,") == "för-"

    def test_keeps_internal_hyphen(self):
        assert norm_token("e-post") == "e-post"

    def test_pure_punctuation_becomes_empty(self):
        assert norm_token("•") == ""
        assert norm_token("–") == "-" or norm_token("–") == ""


class TestCanonicalStream:
    def test_merges_hyphenated_linebreak(self):
        stream = canonical_stream(["för-", "valtning", "av", "huset"])
        tokens = [t for t, _ in stream]
        assert tokens == ["förvaltning", "av", "huset"]
        assert stream[0][1] == [0, 1]  # merged token spans both source words

    def test_plain_words_map_one_to_one(self):
        stream = canonical_stream(["Styrelsen", "beslutade."])
        assert [(t, idx) for t, idx in stream] == [("styrelsen", [0]), ("beslutade", [1])]

    def test_skips_pure_punctuation_words(self):
        tokens = [t for t, _ in canonical_stream(["a", "•", "b"])]
        assert tokens == ["a", "b"]


class TestFindSpans:
    WORDS = "Föreningens firma är Bostadsrättsföreningen Gjutformen 12 . Styrelsen har sitt säte i Göteborg".split()

    def test_exact_match(self):
        assert find_spans(self.WORDS, "Styrelsen har sitt säte") == [(7, 10)]

    def test_case_and_punctuation_insensitive(self):
        assert find_spans(self.WORDS, "styrelsen HAR sitt säte,") == [(7, 10)]

    def test_no_match(self):
        assert find_spans(self.WORDS, "ordföranden har vetorätt") == []

    def test_multiple_occurrences(self):
        words = "hyra betalas i förskott . hyra betalas i förskott".split()
        assert find_spans(words, "hyra betalas") == [(0, 1), (5, 6)]

    def test_hyphenated_source_dehyphenated_quote(self):
        words = ["Ekonomisk", "för-", "valtning", "sköts", "av", "byrån"]
        assert find_spans(words, "Ekonomisk förvaltning sköts") == [(0, 3)]

    def test_dehyphenated_source_hyphenated_quote(self):
        words = ["Ekonomisk", "förvaltning", "sköts"]
        assert find_spans(words, "Ekonomisk för- valtning sköts") == [(0, 2)]

    def test_hyphen_compound_split_vs_joined(self):
        # "e-post" split at linebreak as "e-" + "post" still matches quote "e-post"
        words = ["Kontakta", "oss", "via", "e-", "post", "alltid"]
        assert find_spans(words, "via e-post alltid") == [(2, 5)]

    def test_swedish_suspended_hyphen(self):
        # "vatten- och avloppssystem" — the trailing hyphen on "vatten-" is
        # grammatical, not a linebreak split; identical text must still match.
        words = ["underhåll", "av", "vatten-", "och", "avloppssystem"]
        assert find_spans(words, "vatten- och avloppssystem") == [(2, 4)]

    def test_nbsp_and_typographic_quote_in_quote(self):
        words = ["Avgiften", "är", "1", "250", "kr", "per", "månad"]
        assert find_spans(words, "Avgiften är 1 250 kr") == [(0, 4)]

    def test_quote_with_soft_hyphen(self):
        words = ["årsavgiften", "fastställs", "av", "styrelsen"]
        assert find_spans(words, "års­avgiften fastställs") == [(0, 1)]

    def test_empty_quote_returns_nothing(self):
        assert find_spans(self.WORDS, "") == []
        assert find_spans(self.WORDS, " . , ") == []


class TestChainMergeAndDashSignals:
    def test_chain_merge_three_fragments(self):
        # A word hyphenated over three lines folds into one canonical token.
        assert find_spans(["för-", "valt-", "ning"], "förvaltning") == [(0, 2)]

    def test_chain_merge_provenance_indices(self):
        stream = canonical_stream(["för-", "valt-", "ning", "klar"])
        assert stream[0] == ("förvaltning", [0, 1, 2])
        assert stream[1] == ("klar", [3])

    def test_em_dash_does_not_merge_words(self):
        # "slutet—" + "Nästa": the em dash is punctuation, not hyphenation.
        assert find_spans(["slutet—", "Nästa", "kapitel"], "Nästa kapitel") == [(1, 2)]
        assert find_spans(["slutet—", "Nästa"], "slutet") == [(0, 0)]

    def test_trailing_soft_hyphen_merges(self):
        assert find_spans(["för­", "valtningen", "sköts"], "förvaltningen sköts") == [(0, 2)]


class TestUnmergedFallback:
    def test_quote_starting_inside_a_merge(self):
        words = ["ordinarie", "för-", "valtningen", "har", "skötts"]
        assert find_spans(words, "valtningen har skötts") == [(2, 4)]

    def test_quote_ending_at_a_fragment(self):
        assert find_spans(["ordinarie", "för-", "valtningen"], "ordinarie för-") == [(0, 1)]
