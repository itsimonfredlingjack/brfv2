# Product Guidelines

## Voice & Tone

### Brand Voice

Clear, calm, and trustworthy Swedish. Use plain language for volunteer boards, with short and direct UI text, no marketing fluff or unnecessary technical jargon. Be precise about sources, uncertainty, responsibility, and what the system can or cannot do. Technical documentation may be more formal and detailed, but should remain readable and unambiguous.

### Voice Attributes

- **Clear:** Say what happened, what the source is, and what the human can do next
- **Calm:** No urgency theatre; board work is serious enough without alarmist copy
- **Trustworthy:** Prefer “we could not find support in your documents” over soft inventing
- **Precise:** Name sources, status, and limits; avoid vague “AI-powered” claims

### Tone by Context

| Context | Tone | Example direction |
| --- | --- | --- |
| Success / grounded answer | Steady, source-forward | Lead with the answer, then openable citations |
| Refusal | Direct, non-apologetic | State that documents do not support an answer |
| Error / system failure | Helpful, specific | What failed + what to try; no stack traces in UI |
| Empty states | Inviting, practical | What is missing and the next useful action |
| Onboarding / setup | Patient, stepwise | Short steps; no feature dump |

### Words We Prefer

- Källa, citat, dokument, granskning, beslut, behålls i Träffs miljö
- “Stöds inte av föreningens dokument” / “kunde inte verifieras”
- Status labels that match the domain (e.g. review status ≠ accounting approval)

### Words We Avoid

- Marketing fluff (“magisk AI”, “revolutionerar”)
- False certainty (“garanterat korrekt”)
- Implying write-back or approval in external systems
- Blaming the user for system or grounding limits

## Messaging Guidelines

### Primary Message

> Träff gör fragmenterat BRF-arbete till spårbara, källstödda åtgärder — människan beslutar, systemet förbereder, innehållet stannar i Träffs kontrollerade infrastruktur.

### Supporting Messages

1. Every approved answer opens the cited source at the right place — or is refused.
2. Mail, invoices, tasks, and watches connect into one traceable product surface.
3. No association content is sent to external model APIs for processing.

### Message Hierarchy

1. **Must communicate:** Human control, source grounding, data residency / no external model APIs for content
2. **Should communicate:** How work areas connect (post, fakturor, bevakningar, uppgifter)
3. **Could communicate:** Multi-client packaging (web, desktop RPM, mobile) when relevant to the audience

## Design Principles

### 1. Refuse over fabricate

An answer without a verifiable citation in the tenant’s own documents is refused, never invented.

**Do:** Surface refusals clearly; keep citation paths openable.  
**Don’t:** Soften into plausible-sounding text when support is missing.

### 2. Human decides, system prepares

The product prepares findings, drafts, queues, and structured work. Approvals and outcomes are human.

**Do:** Present evidence and options.  
**Don’t:** Auto-approve invoices or send mail as if the board had acted.

### 3. Every action must remain traceable to its source

Decisions, findings, and answers should point back to documents, messages, or observations that justify them.

**Do:** Preserve provenance; prefer derived stable ids over random re-creates.  
**Don’t:** Orphan state that cannot be re-opened to its origin.

### 4. Tenant isolation is structural

Each association has its own store and index. Cross-tenant access must be impossible by construction, not merely filtered.

**Do:** 404 for another tenant’s resources (not 403).  
**Don’t:** Shared queries that “just” forget a `brf_id` filter.

### 5. No association content leaves Träff-controlled infrastructure

Documents, questions, mail, invoices, prompts, embeddings, and model results stay in Träff’s operating environment (Sweden first, else EU/EES).

**Do:** Self-hosted / controlled inference paths; egress audits where required.  
**Don’t:** Send association content to external commercial model APIs.

### 6. Simplicity for volunteer boards

UI and copy must work for non-technical styrelse members under time pressure.

**Do:** Short UI text; progressive disclosure for advanced tools.  
**Don’t:** Require operator knowledge to complete ordinary loops.

### 7. Read-only integrations by default

Fortnox, Graph/Outlook, and similar adapters ingest and normalise; they do not write back.

**Do:** Intelligence layer + human decision in Träff.  
**Don’t:** Treat missing write verbs as temporary; absence is structural.

### 8. Reliability and reversibility over convenience

Prefer locked command/mutate paths, append-only history where designed, and reversible human outcomes over clever one-shot automation.

**Do:** One validator path for people and models where that pattern exists (e.g. website commands).  
**Don’t:** Replace objects wholesale in ways that erase auditability.

## Accessibility Standards

### Compliance Target

WCAG 2.2 AA as the working target for product UI (web and mobile). Exact certification is not claimed until verified.

### Core Requirements

- Meaningful text alternatives; colour not sole signal
- Keyboard operable primary flows; visible focus
- Clear language; consistent navigation
- Automated a11y checks where the suite already has them (e.g. mobile PWA)

### Testing

- Use existing project acceptance and a11y specs where present
- Manual keyboard and screen-reader checks for high-traffic loops after UI changes

## Error Handling Philosophy

### Prevention

- Validate early; fail closed on tenant and grounding boundaries
- Confirm destructive actions
- Prefer domain-specific status over raw HTTP codes in UI

### Communication

Structure: **what happened** + **why (if useful)** + **what to do next**.

| Bad | Better |
| --- | --- |
| “Något gick fel” | “Kunde inte spara granskningen. Försök igen.” |
| “Error 500” | “Tjänsten svarade inte. Kontrollera anslutningen och försök igen.” |
| Invented answer | “Föreningens dokument stöder inte ett svar på den frågan.” |

### Recovery

- Preserve user input on soft failures
- Offer reopen / retry paths for review work
- Never recover by fabricating content
