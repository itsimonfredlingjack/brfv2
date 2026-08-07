# Product Vision

## Product Overview

**Name:** Träff

**Tagline:** Structured, source-backed work for Swedish housing associations — human decides, system prepares, content never leaves Träff-controlled infrastructure.

**Description:**

Träff använder inga externa modell-API:er för behandling av föreningens innehåll. Inferens körs på infrastruktur som Träff kontrollerar, i första hand i Sverige och annars inom EU/EES. Dokument, frågor, mejl, fakturor, prompts, embeddings och modellresultat lämnar aldrig Träffs driftmiljö.

Träff is a multi-client product (web, desktop, mobile) shared by one FastAPI backend. Core loops include grounded document Q&A with page-level citations, inkommande post, fakturor, bevakningar, uppgifter, and hemsidan — always refusing claims the association’s own sources do not support.

## Problem Statement

### The Problem

Träff solves the gap between information arriving and responsible action being taken.

BRF boards are often run by volunteers who must manage emails, invoices, contracts, resident questions, meeting notes and deadlines across fragmented, unstructured systems. Important information gets buried, responsibilities become person-dependent, and decisions are difficult to trace back to their source. Existing portals digitise individual tasks, while generic AI tools introduce uncertainty around accuracy, privacy and data location.

Träff turns this fragmented workload into structured, source-backed and traceable work, while keeping every decision under human control and all AI processing within Träff-controlled Swedish or European infrastructure.

### Current Solutions

- Association portals and document archives that store files but do not structure work
- Email and accounting tools (Outlook, Fortnox, etc.) that hold fragments of truth
- Generic cloud AI assistants that answer fluently without binding answers to the association’s own documents or data residency guarantees

### Why They Fall Short

- Tasks are digitised one-by-one; nothing connects mail → invoice → contract → decision
- Responsibility stays person-dependent when knowledge lives in inboxes and heads
- Generic AI invents or hedges; board work needs refuse-over-fabricate and openable sources
- Third-party model APIs raise privacy, accuracy, and data-location risk for association content

## Target Users

### Primary Users

Swedish housing associations (*bostadsrättsföreningar*) as organisations — boards, appointed managers, and anyone authorised to act for the association.

- **Who:** Volunteer styrelse members, property managers, and delegated operators acting for a BRF
- **Goals:** Act on incoming information responsibly; find what the documents say; leave an audit trail others can follow
- **Pain Points:** Fragmented systems, buried deadlines, untraceable decisions, fear of leaking data to external AI
- **Technical Proficiency:** Mixed — product UI must work for non-technical volunteers; operators may be more technical

### Secondary Users

- Integrators and technical operators deploying desktop packages or running self-hosted inference
- Product/engineering teams maintaining the shared backend contract across clients

## Core Value Proposition

### Key Goals

1. Turn fragmented BRF work into structured, source-backed actions while keeping every decision under human control.
2. Make all AI processing private, verifiable, and operated entirely within Träff-controlled Swedish or EU/EES infrastructure.
3. Reduce person-dependence by connecting documents, incoming post, invoices, tasks, watches, and decisions in one traceable product.

### Differentiators

- **Refuse over fabricate** — no answer without a verifiable citation in the tenant’s own corpus
- **Structural tenant isolation** — each `brf_id` has its own object graph; 404 not 403 for foreign resources
- **No association content to external model APIs** — inference on Träff-controlled infrastructure (SE / EU/EES)
- **Read-only integrations** — Fortnox and Microsoft Graph as intelligence layers, not write-back systems
- **Human decides, system prepares** — review queues and findings, not autonomous approvals

### Value Statement

> Träff closes the gap between information arriving and responsible action — source-backed, human-controlled, and private by infrastructure, not by policy alone.

## Success Metrics

Success is evidence-based for this product line (tests, acceptance runs, pilot evidence under `docs/evidence/`), not vanity traffic metrics. Track and update as product metrics are formalised.

### Leading indicators (working set)

- Grounded answers open the cited PDF at the right page with the passage highlighted
- Unsupported questions are refused, not guessed
- Intake → preserve → task/watch/invoice paths remain deterministic where designed to be
- Zero unexpected egress of association content to external model providers in pilot/desktop verification

### Lagging indicators (working set)

- Boards complete real work loops without leaving the product for “where did that decision come from?”
- Person-dependence drops for recurring mail, invoice, and deadline handling

## Out of Scope

### Explicitly Not Included

- Writing back to Fortnox, Outlook, or other external systems of record
- Using external commercial model APIs for association content processing
- Replacing the association’s legal counsel or formal accounting approval workflows
- Treating local review status as an approval in another system’s ledger

### Non-Goals

- Becoming a general-purpose chatbot for the open web
- Multi-tenant document storage in a shared SQL “product database” that mixes corpora
- Shipping feature parity of every web workspace to phone (phone is for the grounded ask loop, not full invoice/post review)

### Future Considerations

Document as tracks when prioritised; do not assume them in the current product base without a track.
