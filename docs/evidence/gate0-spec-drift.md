# Gate 0a — SPEC.md drift check (2026-07-16)

**Method.** SPEC.md (reconstructed 2026-07-16, provenance note at top) was re-read against every
recoverable source: the build prompt's "Raise the ceiling" section (recovered verbatim from the
prior session transcript), `deep-research-report.md` (full read), and the original mock UI's
settings contract (`src/components/SettingsView.jsx`). The build prompt's **floor section was
never on this machine** — the ceiling text opens with "The definition of done *above* is the
floor", and no transcript in either project directory contains the text above it. The floor was
reconstructed from the ceiling's references and the original instruction ("upload → ask →
grounded answer → correct highlight"); Simon holds the only authoritative copy.

## Findings — where SPEC matches the sources

| SPEC section | Source | Status |
|---|---|---|
| §2 failure modes 2.1–2.7, 2.9 | Ceiling item 2 lists exactly these modes | ✅ faithful |
| §5 OCR rig (overlays, drift, quote-match, no go/no-go) | Ceiling item 6, near-verbatim | ✅ faithful |
| §6 eval metric *set* (recall@k, verification, highlight, false-answer) | Ceiling item 1, verbatim | ✅ faithful |
| §4 settings contract | SettingsView.jsx + ceiling item 3 | ✅ faithful |
| §7 corpus & demo | Ceiling items 5 + report §Teknisk spik | ✅ faithful |
| §8 non-goals (multi-tenant, auth, GraphRAG, agentic later) | Ceiling gate paragraph, verbatim | ✅ faithful |
| §8 future EU stack "(Qdrant, BGE-M3, Mistral)" | Report's recommendations | ✅ faithful to the report |

## Drift — reconstruction choices not present in any source (need Simon's nod)

1. **Gate numbers** (§6): recall ≥ 0.85, verification ≥ 0.90, highlight ≥ 0.90, false-answer = 0.
   The ceiling text names the metrics but no thresholds. The report's spike criteria say
   recall@5 ≥ 0.80 and highlight ≥ 0.90; the pilot effect goal says correct-source ≥ 0.80.
   SPEC's numbers are equal or stricter than every sourced number. *Risk: low (stricter).*
2. **Highlight-match rule** (§6): "IoU ≥ 0.30 **or** ≥ 60 % of the citation rect inside the
   golden rect". The containment alternative was added mid-build when a shorter-but-correct
   quote (g14) failed pure IoU. It is a *loosening* relative to pure IoU and is not in any
   source. All 46 golden answers pass with it; 45/46 pass under pure IoU ≥ 0.30.
3. **§2.4 span-crosses-pages policy**: resolved by *construction* (chunks never cross pages;
   quotes must match within one page) rather than by cross-page matching. Consequence: a word
   hyphenated across a *page* break is unfindable as a merged word (review finding #38,
   accepted limitation). The ceiling only says "spans crossing … pages" must be handled.
4. **§2.8 Unicode drift** is a SPEC addition beyond the ceiling's list (motivated by the
   report's Swedish-document emphasis). Strictly extra coverage.
5. **Numeric defaults** (chunk 220/40, minRelevance 0.18, topK 6 …) are implementation-derived,
   not sourced.

## Divergences from the research report — intentional, documented in SPEC §0/§8

The report recommends an OCR-first pipeline (Mistral OCR/Surya), Qdrant, BGE-M3 + reranker, and
Mistral/Silo LLMs on EU hosting. The vertical slice deliberately used PyMuPDF text-layer
extraction (OCR deferred to the §5 spike), a custom in-process hybrid index, model2vec
embeddings, no reranker, and Anthropic/CLI generation — all behind provider seams, as SPEC §8
records. Two report items never made it into SPEC at all and are now tracked:

- **Answer-faithfulness control step** (report "kvalitetskontroll"; verify the *prose*, not just
  the quotes). Matches confirmed review finding #28 — mitigated this phase (prompt hardening),
  full check ticketed for a later phase.
- **Cross-encoder reranking** ("nödvändig för källnoggrannhet" per the report). The slice's
  measured verification rate of 1.000 on the seed corpus did not need it; revisit at real-corpus
  scale.

**Pilot-phase note.** The report's own tenant model is "namespace-separation via metadata
filtering in the vector DB" (§Tenant- och säkerhetsmodell). The pilot brief explicitly requires
stronger-than-that ("enforced at the data layer, not just filtered in a query"), and the pilot
brief names **Gemma 4** as the generation model where the report recommended Mistral Large 2 /
Silo Viking. The brief is newer and explicit; it wins. Both departures are recorded in
`SPEC-PILOT.md`.

## Verdict

No contradiction found between SPEC.md and any recoverable source. Items 1–3 above are the only
substantive reconstruction choices; **Simon should confirm the gate numbers, the highlight-match
rule, and the §2.4 page-break policy**, and can diff the floor section against his original
build prompt whenever convenient.
