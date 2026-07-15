# SPEC §2 failure-mode → test traceability

Every failure mode has a test that proves *detection*, not just absence of crashes.
Run: `cd backend && uv run pytest -q`

| § | Failure mode | Detection tests |
|---|---|---|
| 2.1 | Quote not found (fabricated/altered) | `test_citations.py::Test21QuoteNotFound` (fabricated + subtly altered); end-to-end refusal: `test_answer.py::TestGrounding::test_fabricated_quote_rejected_and_refused_when_all_fail` |
| 2.2 | Span crosses lines | `test_citations.py::Test22SpanCrossesLines` (2 rects, y-bands asserted) |
| 2.3 | Span crosses blocks | `test_citations.py::Test23SpanCrossesBlocks` (fixture asserts ≥2 real blocks) |
| 2.4 | Span crosses pages | Structural: `test_chunker.py::TestInvariants::test_chunks_never_cross_pages`; resolution is constrained to the cited chunk's page (`citations.py::resolve_quote`) |
| 2.5 | Hyphenation drift | `test_normalize.py::TestFindSpans::test_hyphenated_source_dehyphenated_quote` (+3 hyphen variants); `test_citations.py::Test25HyphenationDrift` (boxes include both fragments); corpus plants a real split (`test_seed.py::test_hyphenation_split_present_in_corpus`); golden g24 exercises it through the full pipeline |
| 2.6 | Duplicated boilerplate | `test_citations.py::Test26DuplicatedBoilerplate` — right-page resolution AND `provenance_mismatch` rejection; seeded corpus has an identical footer on all 13 pages |
| 2.7 | Out-of-bounds boxes | `test_citations.py::Test27OutOfBounds` (hand-built off-page word → `bbox_out_of_bounds`) |
| 2.8 | Unicode drift | `test_normalize.py::TestNormalizeText` (NFKC/ligature/NBSP/soft-hyphen/quote-dash folds); `test_citations.py::Test28UnicodeDrift` |
| 2.9 | Unanswerable question | Gate a (pre-LLM): `test_answer.py::TestGates::test_low_relevance_refuses_before_llm` (asserts LLM not called); gate b: `::test_llm_insufficient_data_refuses`; warn mode: `::test_warn_mode_answers_with_warning_instead_of_refusing`; systemic: eval `false_answer_rate = 0.000` on 10 unanswerable |
| — | Unknown/truncated chunk id | `test_answer.py::TestChunkAliases::test_truncated_unknown_id_still_rejected` |
| — | Uncited answer w/ requireSources | `test_answer.py::TestGrounding::test_answer_without_citations_refused_when_sources_required` |

End-to-end refusal reasons exercised in the UI (screenshots in this directory):
`low_relevance` (kvantdatorer), `insufficient_data` (garageplats — explanatory refusal),
`grounding_failed` covered by orchestration tests.
