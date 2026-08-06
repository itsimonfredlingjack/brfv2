# Track Registry

This file maintains the registry of all development tracks for the project. Each track represents a distinct body of work with its own spec and implementation plan.

## Status Legend

| Symbol | Status      | Description               |
| ------ | ----------- | ------------------------- |
| `[ ]`  | Pending     | Not yet started           |
| `[~]`  | In Progress | Currently being worked on |
| `[x]`  | Completed   | Finished and verified     |

## Active Tracks

| Status | Track ID | Title | Created | Updated |
| ------ | -------- | ----- | ------- | ------- |
| `[~]` | [sovereign-inference-boundary](./tracks/sovereign-inference-boundary/) | Enforce sovereign inference boundary | 2026-08-05 | 2026-08-06 |

### [~] sovereign-inference-boundary: Enforce sovereign inference boundary

**Description:** Repository-wide architecture consolidation: same sovereign-inference invariant in source, policy, docs, and artefacts. Fedora/pilot already structurally self-hosted; remove hosted Claude/Anthropic from source/dev/eval.  
**Priority:** critical  
**Type:** feature  
**Status:** Phase 0 (agent guidance) complete; Decisions 1–7 locked; implementation not started  
**Folder:** [./tracks/sovereign-inference-boundary/](./tracks/sovereign-inference-boundary/)  
**Spec:** [spec.md](./tracks/sovereign-inference-boundary/spec.md) · **Plan:** [plan.md](./tracks/sovereign-inference-boundary/plan.md)

---

## Completed Tracks

<!-- Move completed tracks here -->

## Archived Tracks

| Track ID | Type | Reason | Archived | Folder |
| -------- | ---- | ------ | -------- | ------ |

## Track Creation Checklist

When creating a new track:

1. [ ] Add entry to this registry
2. [ ] Create track folder: `./tracks/<track-id>/`
3. [ ] Create `spec.md` from template
4. [ ] Create `plan.md` from template
5. [ ] Create `metadata.json` as required by the track workflow
6. [ ] Update `index.md` active tracks if useful

## Notes

- Track IDs should be lowercase with hyphens (e.g. `invoice-rules-lock`)
- Keep descriptions concise (one line)
- Prioritize tracks as: critical, high, medium, low
- Align track goals with [product.md](./product.md) and invariants in [product-guidelines.md](./product-guidelines.md)
