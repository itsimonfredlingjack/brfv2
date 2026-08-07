# Inkommande — readable layout (top chrome + detail)

Date: 2026-08-07  
Branch context: `ui/inkommande-iteration-1` (builds on A-only, B1, B2)  
Surface: `brfv2-mockup` Inkommande (`IntakeQueue` + Integrations shell)

## Problem

The Inkommande screen is hard to read. The issue is **formatting and hierarchy**, not “delete a few sentences.”

- Top chrome (tabs, mailbox status, filters) competes with the queue and feels like scribble on a newspaper article.
- Filters do not sit calmly above the mail list.
- The detail pane stacks message / reading / decision at similar visual volume.
- The **thread list is acceptable**; only row meta is a bit text-heavy.

Prior A/B1/B2 work improved declutter and decision reachability; readability of chrome + detail hierarchy remains the gap.

## Goal

A review surface a board member can **read and decide on** without visual overload:

- Clear primary vs secondary surfaces
- Same job: open → read → decide
- Same product rules: review queue (not inbox); human decides; mailbox unchanged by resolve

## Non-goals

- Redesigning the list interaction model (no card grid, no single-item-only queue)
- Changing outcome model, ResolveForm fields, or backend intake contracts
- Redesigning Anslutningar beyond shared shell spacing needed for Inkommande
- New visual identity (keep Träff Identitet v2 tokens)

## Approach (approved)

**C — Rebuild top chrome + detail pane; keep list structure.**

### List (minimal)

- Keep master/detail list behavior and selection.
- Optionally shorten row meta (prefer subject + origin + date; demote counts/tags so they do not dominate).
- Do not invent a new list pattern.

### Top chrome

One concern per row; toolstrip — not article:

1. **Tabs** — Inkommande / Anslutningar as navigation only. Count on Inkommande is quiet (not a loud badge).
2. **Source row** — single thin line: connected or not · last fetch · Import / Fetch actions. Policy and attachment format limits live behind progressive disclosure (“Om hämtning” / details), not a permanent gray manifesto box.
3. **Filters** — own row above the list with room to breathe. Three modes must fit without collision (short labels and/or compact segmented control). Not three long phrases fighting the list.
4. **No permanent manifesto** under the title (“Brevlådan är råmaterial…”). Explanation belongs in empty state or help, not above every queue view.

Visual rule: top is chrome. Serif may remain on tab labels; no newspaper block of body copy under the title.

### Detail pane (right)

Preserve epistemic order **message → reading → decision**, formatted as a reading stream:

1. **Message is primary** — calm header (subject, sender, time); body with air. Do not restate list meta as a second newspaper headline.
2. **Reading is secondary** — keep B1 collapsed-by-default progressive disclosure; provisional tone; smaller visual weight than the message.
3. **Decision is footer** — keep B2: anchored at foot of detail; reachable in the working viewport; expanded task/watch forms grow upward into the evidence scroller (no nested scroll inside the decision form in this pass).
4. **Weight & air** — one primary surface (message). Fewer nested boxes; separate with spacing more than frames.

## Invariants to keep

- DOM/reading order: message → reading → decision
- A-only intent: queue work before policy essay
- B1: reading depth collapsed by default
- B2: bounded detail, anchored decisions, forms grow upward
- Resolve outcomes and validation behavior unchanged
- Selective evidence via visual harness (`visual-inkommande.html`) at 1440×900

## Success criteria

At 1440×900 on the visual harness (and live Inkommande with real threads):

1. Top chrome does not read as body copy under a newspaper title.
2. Filter row fits calmly above the list without collision/wrapping chaos.
3. Message body is the obvious primary read target in the detail pane.
4. Reading stays secondary unless expanded.
5. Decision controls remain reachable (B2 preserved).
6. List still works as today; row text is not the loudest element on screen.

## Out of scope follow-ups

- Aggressive single-item review mode (earlier option 3)
- Redesigning list as choose-only rail with full-bleed detail (earlier option 2 as full product shift)
- Max-height strategy if task/watch forms prove too tall in real use (known B2 follow-up)

## Primary files

- `brfv2-mockup/src/components/IntakeQueue.jsx`
- `brfv2-mockup/src/components/IntakeQueue.css`
- `brfv2-mockup/src/components/Integrations.jsx` / `Integrations.css` (shell tabs / shared chrome)
- `brfv2-mockup/src/IntakeQueue.test.jsx`
- `brfv2-mockup/src/visual-inkommande.jsx` + evidence under `docs/evidence/`
