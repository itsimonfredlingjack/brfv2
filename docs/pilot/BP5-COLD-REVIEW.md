# BP5 cold review — controlled Fedora pilot of BRF Dokument-AI (desktop)

**Gate:** Throughförande → BP5.  
**Reviewer role:** independent cold reviewer (no builder history).  
**Review date:** 2026-07-31.  
**Worktree:** `/home/aidev/Projects/brfv2-desktop-bp5-cold-review`  
**Branch:** `grok/bp5-independent-cold-review`

This document is a recommendation, not the human’s formal gate decision.

---

## 1. Claim under review

Exactly this claim, and no broader one:

> One exact unsigned desktop artifact was successfully operated by one
> installationsadministrator on one Fedora 44 KDE/Wayland machine, using a
> synthetic five-document corpus and Gemma 4 12B on `agenntserver` through
> loopback SSH forwarding, across installation, repeated use, fault injection,
> backup, restore, package replacement and recovery from an absent active data
> directory.

A PASS means only that this narrow claim is independently supported and that no
pilot stop criterion (§8) occurred. It does **not** mean distribution readiness,
production readiness, multi-user safety, real-corpus quality, signed packaging,
`dnf upgrade`, other OS/Fedora versions, or accessibility completeness.

---

## 2. Reviewed identities

| Identity | Expected | Independently observed |
| --- | --- | --- |
| Final pilot evidence tip | `a5a112b095d28f2e740b9fe8a095e2c62b9c5803` | `git rev-parse HEAD` = same |
| BP2 source commit | `84b6fc853ec047fe9b438f2e1c0a2aed08cfe754` | ancestor of tip; delivery tree identical |
| `deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | tip, BP2 source, every cumulative pilot commit, installed `BUNDLE.json` |
| RPM | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` | installed; archive under `~/pilot-artefakter/` |
| RPM SHA-256 | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` | archive match |
| Machine | Fedora 44 KDE/Wayland | `Fedora release 44`, `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE` (kernel `7.1.5-201.fc44.x86_64`) |

### Cumulative pilot commits (all ancestors of tip)

| Loop | SHA | Subject |
| --- | --- | --- |
| XS-54 | `7cd1f9211e4c7b670cd8185302fb01a9d3c65057` | recoverable evidence-safe pilot environment |
| XS-55 | `c6db95a55cdfa82898acc3f6dd5b663e90330fe3` | unconfigured machine → working installation |
| XS-56 | `df9f664b738d735d6c7c8a3e9cc91e1d724e41f0` | repeated real sessions |
| BP4-3 | `813f26dbd9d266360bf7ebf6c86e16e3fd3c142f` | BP4-3 gate pack |
| XS-57 D1–D3 | `e96db7d31d175ddcbe4d7b3276986436b54107b3` | backup, restore, package swap |
| XS-57 D4 | `298337a5419c73ccadf544f575b3d089bb5accee` | disaster recovery from missing data dir |
| XS-57 cleanup | `a5a112b095d28f2e740b9fe8a095e2c62b9c5803` | quarantine afterpass |

Machine-readable capture:
[`docs/evidence/pilot/bp5-cold-review/cold-review-results.json`](../evidence/pilot/bp5-cold-review/cold-review-results.json).

---

## 3. Methodology and evidence classes

### What was done

1. Isolated worktree from tip `a5a112b…` only (product code and live pilot state
   not modified by this review).
2. Read primary pilot docs: `PILOTPLAN.md`, `RUNBOOK-PILOT.md`, `JOURNAL.md`,
   BP3/BP4-3/BP4-4 packs, XS-54–XS-57 evidence files and registers, XS-56 JSON.
3. Reproduced integrity commands on the live Fedora install and archive.
4. Independently analysed machine-readable Q&A, reconstructed citation support
   from live extract word lists, and compared live `data/` to the D1 backup.
5. Treated every prior PASS / builder conclusion as untrusted until matched to
   primary evidence or a live check.

### Evidence classes used in this report

| Class | Meaning |
| --- | --- |
| **Direct observation** | Command or file inspection run in this cold-review session |
| **Committed primary evidence** | Narrative or machine-readable files written during the pilot loops |
| **Operator attestation** | Human-attested UI steps (B2/B3 smoke, menu starts); not automation |
| **Agent-assisted observation** | Pilot-time a11y/log tooling; product behaviour still via real window |
| **Inference from code** | Source inspection of frozen `REPRO_DELIVERY_PATHS` (e.g. Shift+Enter) |
| **Not re-run (limitation)** | Would mutate pilot state or redo destructive exercises |

No historical evidence file was rewritten. No product path, installed RPM tree,
backup, or account state was altered for this review.

---

## 4. Reproduced integrity results

| Check | Command / method | Result | Class |
| --- | --- | --- | --- |
| Tip | `git rev-parse HEAD` | `a5a112b095d28f2e740b9fe8a095e2c62b9c5803` | Direct |
| Four loops present | ancestry of seven SHAs | all `ANCESTOR_OK` | Direct |
| `REPRO_DELIVERY_PATHS` unchanged | `git diff 84b6fc85… HEAD -- <paths>` | empty; `ops/lib/repro.sh` bit-identical | Direct |
| Delivery tree (repo) | `git ls-tree -r … \| sha256sum` at tip and all pilot SHAs | `a702a337…` | Direct |
| Delivery tree (install) | `BUNDLE.json.deliveryTree` | `a702a337…` | Direct |
| Archived RPM | `sha256sum ~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` | `6ba028fb…` | Direct |
| Package integrity | `rpm --verify brf-dokument-ai` | exit `0`, no differences | Direct |
| Provider exclusion | `ops/inspect_payload.py --installed --json …` | **45 checks, 0 findings, `ok: true`** | Direct |
| Hosted provider selectable | same inspection (`provider-selection`, registry) | selected `none` for hosted paths; selfhosted still selectable | Direct |
| Signature | `rpm -qi` | `Signature : (none)` — unsigned, as claimed | Direct |

Captures:
- [`integrity-summary.txt`](../evidence/pilot/bp5-cold-review/integrity-summary.txt)
- [`inspect-installed.json`](../evidence/pilot/bp5-cold-review/inspect-installed.json)
- [`inspect-installed.txt`](../evidence/pilot/bp5-cold-review/inspect-installed.txt)

**No hosted provider is present, selectable or reachable in the installed payload.**

---

## 5. Evidence integrity

| Control | Finding |
| --- | --- |
| XS-56 register hashes vs files | pass1/2/3 and g19-restart SHA-256 match register exactly |
| Pass files | three files, each 15 824 bytes, **identical answers**, **different** `elapsed_s` → three recordings, not three copies of one file |
| Committed secrets / PII in pilot evidence | no real emails in `xs56/*.json`; no backup zips, PDFs, or `auth.db` in Git; only intentional dummy `sk-ant-must-never-be-used` in preflight notes |
| Operator identity in docs | name appears in plan/journal as participant label (expected); not in machine-readable Q&A |
| Historical rewrite to improve scores | g24/M5 correction **raises** the bar (10/10 → 9/10) and preserves the original wrong answer with strike-through — not a silent improvement |
| Preflight vs first-start separation | `EVIDENSREGISTER-XS55.md` cleanly separates class P (acceptance under temp `XDG_DATA_HOME`) from class F (genuine first start) |

---

## 6. Independent findings per loop

### 6.1 XS-54 — environment

Committed evidence (`slinga1-startevidens.md`) plus live archive/install checks
support: recoverable RPM archive, SHA identity, setup of corpus and tooling
outside delivery paths. **Direct:** archive hash and install identity hold today.

### 6.2 XS-55 — genuine first start

| Required check | Independent conclusion | Basis |
| --- | --- | --- |
| First start genuine | **Supported.** B0 recorded `~/.local/share/se.brfdokumentai.desktop` absent before start; acceptance preflight used isolated `XDG_DATA_HOME` | Committed F-class evidence; register timing (account created after preflight screenshots) |
| Final corpus 5 docs / 13 chunks | **Supported then and now** | Committed; **direct** live `documents.json` sums to 5 / 13; PDFs match `~/pilot-korpus/` and sling1 SHA table |
| Baseline fragment facts after g24 correction | **9/10, not 10/10** | Journal correction + golden.json: g24 facit is SBC economic manager; Driftia is technical — page text confirms both |
| M10 invalid, not replaced | **Supported** | Journal: measured but invalid (overnight pause); no invented substitute metric |
| Shift+Enter failed | **Supported** | Operator attestation + **inference from code**: chat is `<input type="text">`, Enter handlers lack multi-line / effective Shift+Enter newline behaviour; `user-profile` menu entry has **no `tabIndex`** |
| u05 failed zero-citation rule | **Supported under unchanged rule** | Baseline: qualified non-answer **with** supported citation → 2/3 unanswerable |
| No fabricated citation | **Supported** | Fabrication = unsupported citation; g24 citation resolved, answer wrong — not fabrication (stop criterion 4) |

**Evidence class note:** B2 setup and B3 keyboard smoke are operator attestation
(with tool assist on smoke). B4 corpus counts and B5 citation resolution are
machine-verifiable against extracts. This review did **not** re-run first start.

### 6.3 XS-56 — repeated sessions

| Required check | Independent conclusion | Basis |
| --- | --- | --- |
| Three distinct real sessions | **Supported** | Three JSON files; answers identical sans times; times differ; narrative records four menu starts / three full suites |
| Correctness vs citation separate | **Supported** | BP4-3 / sling3 methodology; g24 answers **SBC** (correct) in all three passes |
| Recorded suite results | **Supported** | 10/10 · 2/2 · 3/3 · 0 fabricated per pass; `field_verified: true` on all 15×3; unanswerables `u02,u05,u08` have **zero** citations |
| Cited pages support answers | **Supported (14/14)** | Reconstructed page text from live extract words (dehyphenating PDF soft breaks); all citation quotes found |
| Tunnel loss safe | **Supported (not re-injected)** | Committed: provider error / refusal, zero citations, no grounded-looking fabrication; logs only `127.0.0.1:8000` |
| Backend termination product-owned | **Supported (not re-injected)** | Committed: error window named **signal 15**; data tree unchanged; log rotation preserved crash log |
| Data survived both injections | **Supported** | Committed hashes; **direct** live data still 5/13, `auth.db` `96636b3e…`, endpoint `http://127.0.0.1:8000/v1` |
| No unexpected egress | **Supported (log-level)** | Committed log URL inventory; payload inspection excludes hosted providers |

Post-restart grounded answer (`pass3-grundat-svar-efter-omstart.json`): g19
“Årets resultat blev -142 000 kronor” → Årsredovisning 2025.pdf s.2 — quote
present on reconstructed page 2.

### 6.4 XS-57 — backup, restore, package swap, absent data/

| Required check | Independent conclusion | Basis |
| --- | --- | --- |
| D1 backup identity + off-machine copy | **Supported** | Live D1 zip SHA `5fe53c7a…` (16 entries, 5 docs); register records matching remote copy |
| D2 against genuine post-backup deviation | **Supported (committed)** | Tree changed `23e27246…` → `aaab8211…` then restored to T0; not an empty restore against unchanged data |
| D3 uninstall/reinstall preserves data | **Supported (committed + install date)** | Data outside package; `rpm -qi` install date 2026-07-30 17:15 consistent with reinstall narrative |
| D4 active `data/` absent | **Supported as quarantine absence** | Documented atomic move to `~/pilot-quarantine-xs57/…`; product saw missing path |
| Restoration recovered exact account/association/endpoint/5/13 | **Supported** | Committed post-restore table; **direct:** live files **15/15 bit-identical** to D1 zip; auth `96636b3e…`; endpoint loopback; 5/13 |
| Grounded post-recovery answer | **Supported (committed)** | g19 citation to correct page after D4 restore |
| Quarantine cleanup authorised and scoped | **Supported** | Afterpass documents BP4-4 authorisation; path strictly under quarantine; active data and backups retained; target **absent now** |

**Explicit non-claim (required):** D4 demonstrated recovery from **absence of the
active path** via a **reversible quarantine move**. It did **not** physically
overwrite or cryptographically erase filesystem blocks. Product-visible
condition (path missing) is the same; block-reuse after true deletion is
unproven.

**Tree-hash note:** pilot narratives key on aggregate `data/` digest
`23e27246…`. This review could not re-derive that exact aggregate string with a
simple `find | sha256sum | sha256sum` pipeline, but **every file** in live
`data/` is bit-identical to the D1 backup that the pilot used as recovery
ground truth, and `auth.db` matches the recorded `96636b3e…`. File-level
identity is treated as the stronger integrity check; the unreproduced aggregate
string is a documentation gap, not evidence of data loss.

---

## 7. Stop-criterion assessment (§8)

Each criterion was evaluated against primary evidence and live checks. **None
occurred.**

| # | Criterion | Assessment |
| --- | --- | --- |
| 1 | Cross-tenant document leakage | No second tenant in pilot; no evidence of leakage |
| 2 | Egress to non-configured host | Logs restricted to configured loopback model URL; tunnel-loss case contacted no alternate host |
| 3 | Hosted provider present/selectable | Live `inspect_payload --installed`: 0 findings; selection tests select none for hosted |
| 4 | Fabricated citation / ungrounded answer presented as grounded | 0 fabrications; g24 baseline error was wrong-but-supported selection, corrected methodologically |
| 5 | Data loss on backup/restore/reinstall | D2/D3/D4 show recovery; live state matches D1 |
| 6 | `rpm --verify` ≠ 0 or `deliveryTree` ≠ `a702a337…` | verify 0; trees match |
| 7 | Three unexplained backend deaths in one pass | One intentional SIGTERM (explained); host power-loss earlier (explained); zero unexplained triples |

---

## 8. Contradictions, corrections, unresolved gaps

### Corrections already in the evidence (not hidden)

1. **g24 / M5:** baseline fragment facts **9/10** after correction (was wrongly
   counted 10/10 when citation resolution was treated as answer correctness).
2. **M4 wording:** “unexpected” vs “unexplained” backend deaths aligned with
   stop criterion 7.
3. **Preflight timestamp:** acceptance wall-clock corrected from agent read time
   to file mtime window.
4. **D4 method:** quarantine, not wipe — stated in BP4-4 and sling4 §9.

### Unresolved / residual gaps (do not block the narrow claim)

| Gap | Handling |
| --- | --- |
| Aggregate tree-hash string `23e27246…` not re-derived | File-level D1 identity used instead; formula should be documented for future pilots |
| Tunnel / backend fault injections not re-run | Would mutate live state; accepted as committed primary evidence only |
| First-start not re-run | Inherently one-shot; B0 absence check is historical |
| Unanswerable-question rule (zero citations) still open policy at BP4-3 | Pilot kept the strict rule; XS-56 meets it; XS-55 u05 recorded as deviation under that rule |
| Live kernel patchlevel `7.1.5-201` vs evidence `7.1.5-200` | Same Fedora 44 line; not a delivery-tree change |

No contradiction was found that reverses a loop PASS or trips a stop criterion.

---

## 9. Proven scope

Independently supported:

- One **unsigned** RPM `6ba028fb…` / delivery tree `a702a337…` on **one** Fedora
  **44** **KDE/Wayland** machine.
- One installationsadministrator operating the real desktop shell.
- Synthetic **five-document** corpus (bit-identical to `~/pilot-korpus/`), index
  **5 documents / 13 chunks**.
- Model path: **Gemma 4 12B** via **loopback** `http://127.0.0.1:8000/v1` (SSH
  forward to `agenntserver` as pilot operational pattern).
- Lifecycle: install identity, genuine first configuration (historical),
  repeated work sessions, tunnel-loss behaviour, backend-kill behaviour, backup,
  restore against deviation, package remove/reinstall with data retained,
  recovery when active `data/` path is absent (quarantine method).
- Provider exclusion boundary holds on the installed tree (45 / 0).

---

## 10. Unsupported scope (must not be inferred from a PASS)

- Distribution or multi-machine / multi-operator use  
- Production or support commitments  
- Real BRF / customer document quality  
- Shared-machine security beyond single OS user trust boundary  
- Accessibility-complete workflows (keyboard path to Appinställningar broken)  
- Signed packages or package-repo update channels  
- `dnf upgrade` between product versions  
- Other OS families or other Fedora major versions  
- Physical secure-delete / block erasure of data  
- A valid M10 friction measurement  

---

## 11. Limitation classification

| Limitation | Classification |
| --- | --- |
| Invalid M10 (overnight-contaminated; not replaced by invented metric) | **Accepted within proven pilot scope** |
| Shift+Enter sends instead of newline | **Accepted within pilot** · **Required before distribution** (usability) |
| Keyboard-inaccessible Appinställningar (no `tabIndex` on profile menu) | **Accepted within pilot** · **Required before broader pilot** if any keyboard-only operator · **Required before distribution** |
| 14-day restored session survives crash/restore/reinstall without re-auth | **Accepted within pilot** (single operator machine) · **Required before broader pilot** on shared or multi-user hosts |
| `restore-staging/pending-restore.zip` mode `0644` (dir `0700`) | **Accepted within pilot** · **Required before distribution** (defence in depth / PII in zip) |
| D4 quarantine rather than physical byte deletion | **Accepted within proven pilot scope** (path absence proven; block wipe not claimed) |
| Unsigned RPM | **Accepted within pilot** · **Required before distribution** |
| Large RPM (~575 MiB compressed) | **Accepted within pilot** · follow-up for broader deploy targets |
| Synthetic-only corpus | **Accepted within pilot** · **Required before** any real-corpus claim |
| One operator and one machine | **Accepted within pilot** · **Required before broader pilot** |
| No `dnf upgrade` proof | **Accepted within pilot** · **Required before distribution** of a second version |
| No other OS / Fedora-version proof | **Accepted within pilot** · **Required before** those claims |
| No shared-machine security proof | **Accepted within pilot** · **Required before broader pilot** with real data or other users |
| No accessibility-complete workflow | **Accepted within pilot** · **Required before distribution** |
| No real BRF-document quality proof | **Accepted within pilot** · **Required before** production quality claims |

**None of the above is classified as an evidence gap blocking BP5** for the
narrow controlled single-operator Fedora pilot claim.

---

## 12. Formal BP5 recommendation

**PASS BP5 — CONTROLLED SINGLE-OPERATOR FEDORA PILOT VERIFIED**

### Why PASS

- Artifact identity, delivery tree, RPM hash, `rpm --verify`, and provider
  exclusion were independently reproduced on this workstation.
- All four pilot loops are present in coherent ancestry with unchanged
  `REPRO_DELIVERY_PATHS`.
- XS-55/56/57 primary evidence is internally consistent; the g24 correction
  improves honesty rather than erasing failure; stop criteria were assessed
  individually and none fired.
- Live pilot data still matches the D1 recovery point (15/15 files), 5/13 index,
  recorded `auth.db` digest, and loopback endpoint.
- Scope and non-implications are explicit; known limitations are classified
  without absorbing them into a silent success.

### What this PASS is not

Not distribution approval. Not production approval. Not a claim about other
users, machines, OS versions, signed updates, real corpora, accessibility
completeness, or physical media sanitisation.

---

## 13. Review constraints observed

- Product code: not modified  
- Installed artifact: not modified  
- Pilot data / backups / accounts: not modified  
- Destructive exercises: not repeated  
- First-start: not re-run  
- Historical evidence: not rewritten  
- Linear statuses: not updated  
- Human formal BP5 decision: not made on the human’s behalf  

---

*End of independent BP5 cold review.*
