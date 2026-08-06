# Development Workflow

## Core Principles

1. **plan.md is the source of truth** for Conductor track task status
2. **Moderate TDD** — tests required for domain and invariant-critical work; not for pure docs/UI polish
3. **Conventional Commits** — atomic, scoped; squash only when a workflow requires it
4. **Evidence over assertion** — critical paths need tests, logs, and acceptance where the repo already defines them
5. **Invariants first** — tenant isolation, refuse-over-fabricate, no content egress to external model APIs, read-only integrations

## TDD Policy

**Level:** Moderate

**Require tests (preferably before or with implementation) for:**

- Domain logic and regressions
- Tenant isolation, authentication
- Refusal / grounding behaviour
- Persistence and mutate/command paths
- Integrations, invoices, watches, tasks
- Other behaviour that could silently violate product invariants

**Do not require test-first for:**

- Pure documentation
- Styling and low-risk UI polish

**Always:** Relevant existing tests and acceptance checks must still pass before merge.

### Task lifecycle (domain / behaviour work)

1. Select next pending task from track `plan.md`; confirm dependencies and acceptance criteria
2. Mark task `[~]` in progress
3. **Red:** write or extend failing tests that define the behaviour
4. **Green:** minimum code to pass
5. **Refactor:** clarify without behaviour change; follow style guides and existing lint configs
6. Run targeted then broader suites as needed
7. Document deviations from the track spec when permanent
8. Commit with Conventional Commits (atomic; no unrelated mix-ins)
9. Mark task `[x]`; commit plan update when the track process calls for it

### Docs / low-risk UI polish

- Implement carefully against product guidelines
- Run relevant lint and any smoke tests that already cover the surface
- Self-review allowed (see Code review)

## Commit Strategy

- **Conventional Commits:** `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:` (and scopes as used historically, e.g. `feat(website):`)
- Clear, scoped subjects
- Atomic commits; avoid mixing unrelated changes
- Squash only when a task or review workflow explicitly requires it

Examples from this repo’s history shape:

```text
feat(ui): finish Träff workspace design pass
fix(desktop): reinstall same-version RPM updates
docs(readme): put the branch topology where a fresh clone can see it
test(website): complete Tauri boundary acceptance
```

## Code Review Policy

**Required for non-trivial changes**, especially:

- Domain logic, security, authentication, tenant isolation
- Integrations, invoices, persistence
- Grounding / refusal behaviour
- Desktop packaging / delivery-sensitive paths

**Self-review OK for:**

- Documentation
- Very small low-risk UI polish

**Critical changes:** Independent review against the **actual diff**, tests, and acceptance evidence — not a summary alone.

## Verification Checkpoints

**Manual verification after each phase completion.**

**Also verify immediately after high-risk changes** affecting:

- Security, tenant isolation, authentication
- Persistence
- Integrations, invoices
- Grounding / refusal
- Desktop packaging

Each checkpoint should review:

1. Actual diff
2. Relevant tests (and failures if any)
3. Logs / evidence artifacts when acceptance applies
4. User-visible behaviour where UI is involved

Do not proceed to the next phase until the checkpoint is satisfied.

### Suggested commands (repo root)

```bash
make setup              # one-time / clean machine
make test               # backend offline suite
make test-isolation     # isolation + lifecycle + auth
# Frontend unit (per app):
cd brfv2-mockup && npm test
cd xs_mobilapp && npm test
# E2E / acceptance as relevant:
cd brfv2-mockup && npm run test:e2e
make desktop-acceptance
make invoice-acceptance
make intake-acceptance
```

Use the smallest suite that still covers the risk; escalate to full acceptance when the change sits on a journey already covered by those targets.

## Quality Gates (before merge)

| Gate | Requirement |
| --- | --- |
| Tests | Relevant suites green |
| Invariants | No regression on isolation, grounding, auth, read-only egress |
| Lint | Existing configs clean on touched areas (`ruff`, oxlint, ESLint as applicable) |
| Review | Per code review policy |
| Evidence | Acceptance evidence recorded when the change claims a journey-level fix |
| Types | Typecheck where the client has it (e.g. mobile PWA) |

## Phase Completion Protocol

At the end of each Conductor phase:

1. All phase tasks marked complete in `plan.md`
2. Relevant automated tests run
3. Manual verification checkpoint completed (diff + tests + behaviour)
4. Checkpoint commit if the track uses them (e.g. `test:` / `chore:` documenting phase complete — follow Conventional Commits)

## Branch awareness

This monorepo has product lines that were not always merged together. See root `README.md` (Grenar) and `docs/POST-BP6-PRODUKTBAS.md`. If something seems missing (`src-tauri/`, integrations, invoices), check branch topology before “adding” it.

## Workflow Diagram

```
Select task → Mark [~]
     → (domain) Red tests → Green → Refactor
     → (docs/polish) implement carefully
     → Run relevant tests / lint
     → Commit (Conventional, atomic)
     → Mark [x]
     → Phase done? → Manual verification checkpoint → next phase
```
