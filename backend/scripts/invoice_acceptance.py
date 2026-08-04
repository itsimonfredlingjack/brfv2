"""One invoice, driven through the real installed application, end to end.

Run from the repository root after ``make desktop-build`` (or ``make
invoice-acceptance``, which does both)::

    backend/.venv/bin/python backend/scripts/invoice_acceptance.py [--run-label ...]

Why this exists separately from :mod:`scripts.desktop_acceptance`: that one is
the delivery's full journey and requires a reachable self-hosted model, because
the answer it checks is generated. **This one needs no model at all**, and that
is a property of the feature rather than of the script — the invoice review is
deterministic end to end, so an installation with no model configured can still
read an invoice, compare it against the association's own documents and its own
invoice history, and be worked by a board. A journey that needed a GPU to prove
that would be proving something else.

It reuses the same WebDriver harness, the same binary and the same isolated
``XDG_DATA_HOME``, so the operator's real installation is never touched and
every run starts from a genuinely unprovisioned machine.

What it asserts, in order:

1. **Fakturor is a top-level area**, beside Inkommande rather than inside it.
2. Reading one invoice in produces **one case**, analysed, with every
   non-matching finding stating its uncertainty.
3. **No control on the screen reads as approving an invoice** — no "godkänn
   faktura", no "attestera", no "betala".
4. A finding's citation **opens the cited document at the cited page with the
   passage painted**, through the application's own citation navigation.
5. A person comments, sets a local review status that requires a reason, names
   themselves responsible and takes work on — and the timeline tells the four
   human entries apart from the machine ones.
6. **Refresh is idempotent**: pressing it twice adds no timeline entry, no
   finding and no second case, and overwrites nothing a human wrote.
7. The next invoice from the same supplier reports the change **decomposed into
   the part the invoice explains itself and the part it does not**.
8. **A replaced analysis leaves a record.** Confirming that two spellings of a
   supplier name are one company re-runs the review, and the case says so: a
   second version naming the one it superseded, the reading it was built on,
   the rules that produced it, what differed in plain language — and the
   superseded findings themselves, readable, marked as no longer applying and
   carrying no control that would let anyone act on them.
9. **A credit invoice reads as a credit invoice.** A negative amount is shown
   as one, the case names the invoice it exactly cancels, says out loud that
   nothing in the material decides *which* invoice a credit note belongs to,
   and offers no control that would settle anything.
10. **Inkommande no longer reviews invoices**, so the product cannot grow two
    invoice screens that disagree.

**Where the evidence goes.** ``docs/evidence`` by default, under the run's own
label — ``<label>-invoice-<view>.png`` beside a machine-readable
``<label>-invoice-acceptance.json`` — so an accepted run is a committable
record rather than something in ``/tmp`` that the next reboot decides the fate
of. Evidence git already tracks is never overwritten without
``--overwrite-evidence``: that record is what an earlier acceptance was
approved on. The isolated ``XDG_DATA_HOME`` is a throwaway temporary directory
and is deliberately *not* in the evidence tree.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

# The integrations package first: it and app.invoices reference each other's
# models, and the cycle only resolves when this side is entered first. Every
# in-process caller does that implicitly; a script that starts at the invoice
# end has to say it. Same reason as in app/invoices/rules.py.
from app.integrations import models as _integration_models  # noqa: E402, F401
from app.invoices.models import ANALYSIS_ENGINE_VERSION  # noqa: E402
from scripts.desktop_acceptance import (  # noqa: E402
    DRIVER_ORIGIN,
    AcceptanceError,
    Evidence,
    WebDriver,
    application_identity,
    isolated_environment,
    set_select,
    wait_until,
)

# The views this journey records, in the order it walks them. The list is also
# what the overwrite guard checks, so it must name every screenshot the run can
# write — including the failure one, which is exactly the case where a partial
# run must not be allowed to quietly replace a complete one.
INVOICE_SCREENSHOTS: tuple[str, ...] = (
    "queue-empty",
    "case",
    "citation",
    "case-worked",
    "change",
    "analysis-history",
    "replaced-version",
    "credit",
    "queue",
)
FAILURE_SCREENSHOT = "failure"

APPLICATION = REPO / "src-tauri" / "target" / "release" / "brfv2-desktop"

# "Gjutformen 12" slugifies to gjutformen-12, which is the AssociationRef the
# shipped accounting fixture is scoped by — so the read-in list is not empty.
BRF_NAME = "Gjutformen 12"
OWNER = ("Journeytestaren", "styrelsen@journey.example", "journey-losenord-2026")

CONTRACT_NAME = "Snöröjningsavtal 2026.pdf"
CONTRACT_LINES = [
    "SNÖRÖJNINGSAVTAL 2026",
    "",
    "Mellan Brf Gjutformen 12, org.nr 769600-1234, och Snösvängen Entreprenad AB,",
    "org.nr 556812-3344, har följande avtal träffats.",
    "",
    "Avtalet gäller från den 1 november 2026 och tills vidare.",
    "",
    "Ersättning för maskinell snöröjning med traktor utgår med 1 250 kronor per timme,",
    "exklusive mervärdesskatt.",
    "",
    "Uppsägningstiden är tre månader.",
]

results: dict = {}


def note(step: str, payload) -> None:
    results[step] = payload
    print(f"  · {step}: {json.dumps(payload, ensure_ascii=False)[:300]}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--application",
        type=Path,
        default=APPLICATION,
        help="Shell binary to exercise (defaults to the release build in this checkout)",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=REPO / "docs/evidence",
        help="Where this run's screenshots and receipt are written.",
    )
    parser.add_argument(
        "--run-label",
        default="pilot",
        help="Names this run's evidence: <label>-invoice-<view>.png and "
        "<label>-invoice-acceptance.json. Give each run that is to be kept its own "
        "label; evidence already committed is never overwritten without --overwrite-evidence.",
    )
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="Permit this run to overwrite committed evidence files. Destroys the record "
        "an earlier acceptance was approved on, so it has to be asked for.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Receipt path override.")
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep the throwaway XDG home this run provisioned into.",
    )
    return parser.parse_args(argv)


def write_receipt(
    evidence: Evidence,
    application: Path,
    started: float,
    ok: bool,
    transport_retries: int = 0,
) -> Path:
    """The machine-readable half of the record, written whether or not it passed.

    A failing run's receipt is the more useful of the two, so it is not
    conditional: what was reached, what was read, and which screenshot shows
    the state it stopped in.
    """
    receipt = {
        "schema": "brfv2-invoice-acceptance/v1",
        "ok": ok,
        "runLabel": evidence.label,
        "application": str(application),
        "applicationIdentity": application_identity(application, None),
        "durationSeconds": round(time.time() - started, 1),
        # Said in the record rather than only in a docstring: this journey is
        # green on a machine with no GPU, no tunnel and no model configured,
        # because the invoice review is deterministic end to end.
        "modelRequired": False,
        "engineVersion": ANALYSIS_ENGINE_VERSION,
        # Requests the transport lost and the harness re-established without
        # repeating any work. Recorded so a driver that has started dropping
        # every other request shows up as a number rather than as nothing.
        "transportRetries": transport_retries,
        "screenshots": [
            evidence.reference(name)
            for name in INVOICE_SCREENSHOTS
            if evidence.path(name).is_file()
        ],
        "failureScreenshot": (
            evidence.reference(FAILURE_SCREENSHOT)
            if evidence.path(FAILURE_SCREENSHOT).is_file()
            else None
        ),
        "steps": results,
    }
    evidence.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence.receipt


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    evidence = Evidence(
        args.evidence_dir,
        args.run_label,
        receipt=args.output,
        kind="invoice",
        views=(*INVOICE_SCREENSHOTS, FAILURE_SCREENSHOT),
    )
    # Checked before anything is built or started, so an operator who picked a
    # colliding label learns it in the first second rather than after a journey.
    committed = evidence.tracked()
    if committed and not args.overwrite_evidence:
        listing = "\n  ".join(committed)
        raise AcceptanceError(
            f"Run label {args.run_label!r} writes over evidence that is committed:\n  {listing}\n"
            "That record is what an earlier acceptance was approved on. Give this run its own "
            "--run-label, or pass --overwrite-evidence if replacing it is the intent."
        )
    evidence.dir.mkdir(parents=True, exist_ok=True)
    if not args.application.is_file():
        raise AcceptanceError(
            f"Application missing: {args.application}; run make desktop-build"
        )

    # The provisioned home is a throwaway and is deliberately not in the
    # evidence tree: evidence is committed, and a tenant's store is not.
    home = Path(tempfile.mkdtemp(prefix="brfv2-invoice-acceptance-"))
    started = time.time()
    environment = isolated_environment(home)
    # The embedder weights are already in the operator's HF cache. Without
    # this, model2vec re-resolves them over the network on every run, which
    # is both slow and — on this tqdm/huggingface_hub pair — flaky. The
    # packaged application never does either: its weights are bundled.
    environment["HF_HUB_OFFLINE"] = "1"
    driver_logs: list[str] = []
    process = subprocess.Popen(
        ["tauri-driver"],
        cwd=REPO,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    def drain() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            driver_logs.append(line.rstrip())

    threading.Thread(target=drain, daemon=True).start()
    driver = WebDriver(DRIVER_ORIGIN)

    try:
        wait_until("tauri-driver", lambda: driver.request("GET", "/status"), timeout=20)
        driver.create_session(args.application)
        driver.resize(1720, 1080)

        # -- provision ----------------------------------------------------
        wait_until(
            "first-run setup",
            lambda: driver.execute(
                "return document.body.innerText.includes('Välkommen');"
            ),
            timeout=300,
        )
        driver.type_labelled("Föreningens namn", BRF_NAME)
        driver.type_labelled("Ditt namn", OWNER[0])
        driver.type_labelled("E-postadress", OWNER[1])
        driver.type_labelled("Lösenord", OWNER[2])
        driver.type_labelled("Upprepa lösenord", OWNER[2])
        driver.click("button[type=submit]")
        wait_until(
            "association created",
            lambda: driver.execute(
                "return document.body.innerText.includes('Föreningen är skapad');"
            ),
            timeout=300,
        )
        # No model is needed for the invoice review — it is deterministic.
        driver.click_text("Hoppa över")
        wait_until(
            "workspace",
            lambda: driver.execute(
                "return Boolean(document.querySelector('.user-profile'));"
            ),
            timeout=180,
        )

        # -- the contract the review anchors on ---------------------------
        from scripts.seed import render_pdf

        pdf = render_pdf({"name": CONTRACT_NAME, "pages": [CONTRACT_LINES]})
        driver.click_text("Dokument")
        wait_until(
            "documents view",
            lambda: driver.execute("return Boolean(document.querySelector('input[type=file]'));"),
        )
        accepted = driver.execute(
            """
            const bytes = Uint8Array.from(atob(arguments[0]), (c) => c.charCodeAt(0));
            const file = new File([bytes], arguments[1], { type: 'application/pdf' });
            const input = document.querySelector('input[type=file]');
            if (!input) return false;
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
            """,
            [base64.b64encode(pdf).decode(), CONTRACT_NAME],
        )
        if not accepted:
            raise AcceptanceError("The documents view refused the contract upload")
        wait_until(
            "contract ingested",
            lambda: driver.execute(
                "return document.body.innerText.includes(arguments[0]) "
                "&& !document.body.innerText.includes('Laddar upp…');",
                [CONTRACT_NAME],
            ),
            timeout=300,
        )

        # -- Fakturor is a top-level area ---------------------------------
        nav = driver.execute(
            "return [...document.querySelectorAll('.sidebar-menu .nav-item')]"
            ".map(b => b.textContent.trim());"
        )
        note("navigation", nav)
        if "Fakturor" not in nav:
            raise AcceptanceError(f"Fakturor is not a top-level area: {nav!r}")

        driver.click_text("Fakturor")
        wait_until(
            "the invoice workspace",
            lambda: driver.execute("return Boolean(document.querySelector('.invoices'));"),
            timeout=60,
        )
        empty = driver.execute("return document.querySelector('.empty')?.textContent.trim();")
        note("emptyQueue", empty)
        driver.screenshot(evidence.path("queue-empty"))

        # -- read one invoice in ------------------------------------------
        driver.click("details.invoices-read-in > summary")
        available = wait_until(
            "the read-in list",
            lambda: driver.execute(
                """
                const rows = [...document.querySelectorAll('.invoices-available tbody tr')];
                if (!rows.length) return false;
                return rows.map((r) => r.querySelector('code')?.textContent.trim());
                """
            ),
            timeout=60,
        )
        note("availableFromFixture", available)

        clicked = driver.execute(
            """
            const rows = [...document.querySelectorAll('.invoices-available tbody tr')];
            const row = rows.find((r) => r.querySelector('code')?.textContent.trim() === arguments[0]);
            if (!row) return false;
            row.querySelector('button').click();
            return true;
            """,
            ["SI-2026-114"],
        )
        if not clicked:
            raise AcceptanceError("SI-2026-114 was not offered by the fixture source")

        wait_until(
            "the case view",
            lambda: driver.execute("return Boolean(document.querySelector('.invoice-case'));"),
            timeout=180,
        )
        case = wait_until(
            "the case, analysed",
            lambda: driver.execute(
                """
                const root = document.querySelector('.invoice-case');
                if (!root) return false;
                const findings = [...root.querySelectorAll('.finding')];
                if (!findings.length) return false;
                return {
                  supplier: root.querySelector('.case-header h2')?.textContent.trim(),
                  identity: root.querySelector('.case-identity')?.textContent.trim(),
                  basis: root.querySelector('.case-identity-basis')?.textContent.trim(),
                  amount: root.querySelector('.case-amount')?.textContent.trim(),
                  sourceStatus: root.querySelector('.case-status-card.source strong')?.textContent.trim(),
                  localStatus: root.querySelector('.case-status-card.local strong')?.textContent.trim(),
                  caveat: root.querySelector('.case-status-card.local p')?.textContent.trim(),
                  observations: [...root.querySelectorAll('.observation-kind')].map(o => o.textContent.trim()),
                  findings: findings.map((f) => ({
                    verdict: f.querySelector('.verdict')?.textContent.trim(),
                    citations: f.querySelectorAll('.finding-citation').length,
                    uncertainty: Boolean(f.querySelector('.finding-uncertainty')),
                  })),
                  timeline: [...root.querySelectorAll('.case-timeline li')].length,
                };
                """
            ),
            timeout=240,
        )
        note("caseAfterImport", case)
        driver.screenshot(evidence.path("case"))

        # Every finding that is not a match has to state its uncertainty, and
        # no control on the screen may read as an approval of the invoice.
        for finding in case["findings"]:
            if finding["verdict"] != "överensstämmer" and not finding["uncertainty"]:
                raise AcceptanceError(f"A non-matching finding stated no uncertainty: {finding!r}")
        controls = driver.execute(
            "return [...document.querySelectorAll('button')].map(b => b.textContent.trim().toLowerCase());"
        )
        forbidden = [c for c in controls if "godkänn faktura" in c or "attestera" in c or "betala" in c]
        note("forbiddenControls", forbidden)
        if forbidden:
            raise AcceptanceError(f"Found a control that reads as approval: {forbidden!r}")

        # -- the evidence opens where it says ------------------------------
        citation = driver.execute(
            """
            const button = document.querySelector('.finding-citation');
            if (!button) return false;
            const label = button.getAttribute('title');
            button.click();
            return label;
            """
        )
        if citation:
            opened = wait_until(
                "the cited document, at the cited page",
                lambda: driver.execute(
                    """
                    const title = document.querySelector('.workspace-doc-title')?.textContent.trim();
                    if (!title) return false;
                    // The highlight is painted once pdf.js has laid the page
                    // out; probing before that measures the spinner.
                    if (!document.querySelector('.pdf-page-canvas-wrap canvas')) return false;
                    if (!document.querySelectorAll('.pdf-highlight').length) return false;
                    return {
                      document: title,
                      page: document.querySelector('[data-testid=pdf-page-indicator]')?.textContent.trim(),
                      highlight: document.querySelectorAll('.pdf-highlight').length,
                    };
                    """
                ),
                timeout=120,
            )
            note("citationNavigation", {"clicked": citation, **opened})
            driver.screenshot(evidence.path("citation"))
            driver.click_text("Tillbaka")
            driver.click_text("Fakturor")
            wait_until(
                "back on the queue",
                lambda: driver.execute("return Boolean(document.querySelector('.invoices-queue'));"),
                timeout=60,
            )
            driver.execute(
                "document.querySelector('.invoices-queue .case-link').click(); return true;"
            )
            wait_until(
                "the case again",
                lambda: driver.execute("return Boolean(document.querySelector('.invoice-case'));"),
                timeout=60,
            )
        else:
            note("citationNavigation", "no citation on this case")

        # -- a person works the case ---------------------------------------
        driver.execute(
            """
            const box = document.querySelector('.case-comment-form textarea');
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
              .set.call(box, arguments[0]);
            box.dispatchEvent(new InputEvent('input', { bubbles: true }));
            return true;
            """,
            ["Ringde Snösvängen om timtaxan, återkommer på fredag."],
        )
        driver.click_text("Kommentera")
        wait_until(
            "the comment saved",
            lambda: driver.execute(
                "return document.body.innerText.includes('Ringde Snösvängen om timtaxan');"
            ),
            timeout=60,
        )

        set_select(driver, ".case-review-status select", "needs_investigation")
        driver.execute(
            """
            const field = document.querySelector('.case-review-status input');
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
              .set.call(field, arguments[0]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            return true;
            """,
            ["Timtaxan ska stämmas av mot avtalet."],
        )
        driver.click_text("Spara granskningsläget")
        wait_until(
            "the local status saved",
            lambda: driver.execute(
                "return document.querySelector('.case-status-card.local strong')"
                "?.textContent.trim() === 'Behöver utredas';"
            ),
            timeout=60,
        )

        driver.execute(
            """
            const field = document.querySelector('.case-responsible-form input');
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
              .set.call(field, arguments[0]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            return true;
            """,
            ["Ordförande Ek"],
        )
        driver.execute(
            "document.querySelector('.case-responsible-form button').click(); return true;"
        )
        wait_until(
            "responsible saved",
            lambda: driver.execute(
                "return document.querySelector('.case-responsible-current')"
                "?.textContent.trim() === 'Ordförande Ek';"
            ),
            timeout=60,
        )

        driver.click_text("Skapa uppgift ur fakturan")
        wait_until(
            "the create panel",
            lambda: driver.execute("return Boolean(document.querySelector('.task-create.open'));"),
            timeout=60,
        )
        driver.type_labelled("Ansvarig", "Ordförande Ek")
        driver.execute(
            """
            const panel = document.querySelector('.task-create.open');
            const button = [...panel.querySelectorAll('button')]
              .find(b => b.textContent.trim().startsWith('Skapa uppgift'));
            button.click();
            return true;
            """
        )
        wait_until(
            "the task on the case",
            lambda: driver.execute(
                "return document.querySelectorAll('.case-tasks li').length >= 1;"
            ),
            timeout=120,
        )

        worked = driver.execute(
            """
            const root = document.querySelector('.invoice-case');
            return {
              localStatus: root.querySelector('.case-status-card.local strong')?.textContent.trim(),
              caveat: root.querySelector('.case-status-card.local p')?.textContent.trim(),
              responsible: root.querySelector('.case-responsible-current')?.textContent.trim(),
              comments: [...root.querySelectorAll('.case-comments li p')].map(p => p.textContent.trim()),
              tasks: [...root.querySelectorAll('.case-tasks li strong')].map(s => s.textContent.trim()),
              timeline: [...root.querySelectorAll('.case-timeline li')].map(li => ({
                human: li.className.includes('human'),
                text: li.querySelector('.event-summary')?.textContent.trim(),
              })),
            };
            """
        )
        note("afterHumanWork", worked)
        driver.screenshot(evidence.path("case-worked"))

        # -- refresh is idempotent ----------------------------------------
        before = len(worked["timeline"])
        for attempt in (1, 2):
            driver.click_text("Läs om och granska")
            wait_until(
                f"refresh {attempt} finished",
                lambda: driver.execute(
                    "return document.body.innerText.includes('Ingenting ändrades i ekonomisystemet');"
                ),
                timeout=180,
            )
            time.sleep(1.0)
        after = driver.execute(
            """
            const root = document.querySelector('.invoice-case');
            return {
              timeline: root.querySelectorAll('.case-timeline li').length,
              findings: root.querySelectorAll('.finding').length,
              localStatus: root.querySelector('.case-status-card.local strong')?.textContent.trim(),
              comments: root.querySelectorAll('.case-comments li').length,
              responsible: root.querySelector('.case-responsible-current')?.textContent.trim(),
            };
            """
        )
        note("afterTwoRefreshes", {"timelineBefore": before, **after})
        if after["timeline"] != before:
            raise AcceptanceError(
                f"Refresh grew the timeline: {before} → {after['timeline']}"
            )
        if after["localStatus"] != "Behöver utredas" or after["responsible"] != "Ordförande Ek":
            raise AcceptanceError(f"A re-analysis overwrote a human record: {after!r}")

        # -- the next invoice from the same supplier ------------------------
        driver.click_text("Till fakturakön")
        wait_until(
            "the queue",
            lambda: driver.execute("return Boolean(document.querySelector('.invoices-queue'));"),
            timeout=60,
        )
        driver.click("details.invoices-read-in > summary")
        wait_until(
            "the read-in list again",
            lambda: driver.execute(
                "return document.querySelectorAll('.invoices-available tbody tr').length > 0;"
            ),
            timeout=60,
        )
        driver.execute(
            """
            const rows = [...document.querySelectorAll('.invoices-available tbody tr')];
            const row = rows.find((r) => r.querySelector('code')?.textContent.trim() === arguments[0]);
            row.querySelector('button').click();
            return true;
            """,
            ["SI-2026-131"],
        )
        change = wait_until(
            "the change against the previous invoice",
            lambda: driver.execute(
                """
                const panels = [...document.querySelectorAll('.case-panel')];
                const panel = panels.find(p => p.textContent.includes('Jämfört med föreningens tidigare fakturor'));
                if (!panel) return false;
                const finding = panel.querySelector('.finding');
                if (!finding) return false;
                return {
                  verdict: finding.querySelector('.verdict')?.textContent.trim(),
                  suggestion: finding.querySelector('.finding-suggestion p')?.textContent.trim(),
                  citations: finding.querySelectorAll('.finding-citation').length,
                  facts: [...finding.querySelectorAll('.finding-facts dt')].map(d => d.textContent.trim()),
                };
                """
            ),
            timeout=240,
        )
        note("previousInvoiceComparison", change)
        driver.screenshot(evidence.path("change"))
        for needle in ("4 625,00 SEK", "+74,0 %", "förklarar", "förklarar den inte"):
            if needle not in change["suggestion"]:
                raise AcceptanceError(f"The change breakdown never said {needle!r}: {change!r}")

        # -- a replaced analysis leaves a record ---------------------------
        #
        # The third invoice is from "Snösvängen AB" while the contract says
        # "Snösvängen Entreprenad AB", so the review anchors weakly and asks
        # whether they are the same company. Confirming it and re-running is
        # the one way an operator can change the analysis without anything
        # moving in the accounting system — and it is exactly the case the
        # audit trail exists for: the previous findings were open, nobody had
        # formally decided on them, and they still must not vanish silently.
        driver.click_text("Till fakturakön")
        wait_until(
            "the queue",
            lambda: driver.execute("return Boolean(document.querySelector('.invoices-queue'));"),
            timeout=60,
        )
        driver.click("details.invoices-read-in > summary")
        wait_until(
            "the read-in list a third time",
            lambda: driver.execute(
                "return document.querySelectorAll('.invoices-available tbody tr').length > 0;"
            ),
            timeout=60,
        )
        driver.execute(
            """
            const rows = [...document.querySelectorAll('.invoices-available tbody tr')];
            const row = rows.find((r) => r.querySelector('code')?.textContent.trim() === arguments[0]);
            row.querySelector('button').click();
            return true;
            """,
            ["SI-2027-018"],
        )
        first_run = wait_until(
            "the first recorded analysis",
            lambda: driver.execute(
                """
                const runs = [...document.querySelectorAll('.case-analyses .analysis-run')];
                if (runs.length !== 1) return false;
                const run = runs[0];
                return {
                  head: run.querySelector('.run-head')?.textContent.trim(),
                  summary: run.querySelector('.run-summary')?.textContent.trim(),
                  meta: [...run.querySelectorAll('.run-meta dd')].map(d => d.textContent.trim()),
                  replacedControls: run.querySelectorAll('.run-open').length,
                };
                """
            ),
            timeout=240,
        )
        note("analysisVersionOne", first_run)
        if "Version 1" not in first_run["head"]:
            raise AcceptanceError(f"The first analysis was not recorded as one: {first_run!r}")

        confirmed = driver.execute(
            """
            const button = document.querySelector('.alias-confirm');
            if (!button) return false;
            button.click();
            return true;
            """
        )
        if not confirmed:
            raise AcceptanceError(
                "The weak supplier link offered no confirmation — expected "
                "'Snösvängen AB' against the contract's 'Snösvängen Entreprenad AB'"
            )
        wait_until(
            "the confirmation saved",
            lambda: driver.execute(
                "return Boolean(document.querySelector('.alias-proposal.confirmed'));"
            ),
            timeout=120,
        )
        driver.click_text("Kör om granskningen")
        replaced = wait_until(
            "the second recorded analysis",
            lambda: driver.execute(
                """
                const runs = [...document.querySelectorAll('.case-analyses .analysis-run')];
                if (runs.length !== 2) return false;
                const run = runs[0];
                return {
                  head: run.querySelector('.run-head')?.textContent.trim(),
                  summary: run.querySelector('.run-summary')?.textContent.trim(),
                  meta: [...run.querySelectorAll('.run-meta dd')].map(d => d.textContent.trim()),
                  changes: [...run.querySelectorAll('.run-changes .change')].map((c) => ({
                    kind: c.querySelector('.change-kind')?.textContent.trim(),
                    summary: c.querySelector('.change-summary')?.textContent.trim(),
                    facts: [...c.querySelectorAll('.change-facts > div')].map(d => d.textContent.trim()),
                  })),
                  opens: run.querySelector('.run-open')?.textContent.trim(),
                };
                """
            ),
            timeout=240,
        )
        note("analysisVersionTwo", replaced)
        # Bring the panel into view before the shot: evidence of a claim about
        # what a screen shows should show it. The audit trail is a disclosure —
        # it is what the engine *used* to say, so the case does not open with it
        # — and a screenshot of a collapsed panel would evidence nothing.
        driver.execute(
            """
            const panel = document.querySelector('.case-analyses');
            const disclosure = panel?.querySelector('details');
            if (disclosure) disclosure.open = true;
            panel?.scrollIntoView({block: 'start'});
            return true;
            """
        )
        time.sleep(0.4)
        driver.screenshot(evidence.path("analysis-history"))

        if "Version 2" not in replaced["head"] or "gäller nu" not in replaced["head"]:
            raise AcceptanceError(f"The replacement did not read as one: {replaced!r}")
        if "Ersatte den föregående granskningen" not in replaced["summary"]:
            raise AcceptanceError(f"The run never said it replaced anything: {replaced!r}")
        spoken = json.dumps(replaced, ensure_ascii=False)
        for needle in ("regelmotor", "innehållshash", "delvis namnlikhet", "bekräftat"):
            if needle not in spoken:
                raise AcceptanceError(f"The recorded run never said {needle!r}: {replaced!r}")

        # And the version it replaced is still readable — behind a control,
        # because it no longer applies.
        driver.click(".case-analyses .analysis-run .run-open")
        old = wait_until(
            "the superseded findings",
            lambda: driver.execute(
                """
                const cards = [...document.querySelectorAll('.run-replaced .finding.replaced')];
                if (!cards.length) return false;
                return cards.map((c) => ({
                  verdict: c.querySelector('.verdict')?.textContent.trim(),
                  status: c.querySelector('.finding-status')?.textContent.trim(),
                  buttons: c.querySelectorAll('button').length,
                }));
                """
            ),
            timeout=120,
        )
        note("replacedVersion", old)
        driver.execute(
            "document.querySelector('.run-replaced').scrollIntoView({block: 'center'}); return true;"
        )
        time.sleep(0.4)
        driver.screenshot(evidence.path("replaced-version"))
        if any(card["status"] != "ersatt" for card in old):
            raise AcceptanceError(f"A superseded finding did not say so: {old!r}")
        if any(card["buttons"] for card in old):
            raise AcceptanceError(
                f"A superseded finding offered a control — it is a record, not a card in play: {old!r}"
            )

        # -- a credit invoice reads as a credit invoice ---------------------
        #
        # The fourth read-in is the credit note for the third. It is the one
        # case in this workspace where the arithmetic is unambiguous and the
        # *meaning* is not: two amounts that cancel exactly are a fact, and
        # which invoice a credit note belongs to is not written anywhere in
        # the material. The screen has to carry both of those at once — and it
        # must not grow a control that looks like settling the pair, because
        # settling them is something that happens in the accounting system.
        driver.click_text("Till fakturakön")
        wait_until(
            "the queue",
            lambda: driver.execute("return Boolean(document.querySelector('.invoices-queue'));"),
            timeout=60,
        )
        driver.click("details.invoices-read-in > summary")
        wait_until(
            "the read-in list a fourth time",
            lambda: driver.execute(
                "return document.querySelectorAll('.invoices-available tbody tr').length > 0;"
            ),
            timeout=60,
        )
        offered = driver.execute(
            """
            const rows = [...document.querySelectorAll('.invoices-available tbody tr')];
            const row = rows.find((r) => r.querySelector('code')?.textContent.trim() === arguments[0]);
            if (!row) return false;
            const cells = [...row.querySelectorAll('td')].map((c) => c.textContent.trim());
            row.querySelector('button').click();
            return cells;
            """,
            ["SI-2027-024"],
        )
        if not offered:
            raise AcceptanceError("The credit invoice SI-2027-024 was not offered by the source")
        note("creditOffered", offered)

        credit = wait_until(
            "the credit invoice as a case",
            lambda: driver.execute(
                """
                const root = document.querySelector('.invoice-case');
                if (!root) return false;
                const findings = [...root.querySelectorAll('.finding')];
                if (!findings.length) return false;
                const credits = findings.filter((f) =>
                  (f.querySelector('.finding-suggestion p')?.textContent || '').includes('krediteringen'));
                if (!credits.length) return false;
                return {
                  amount: root.querySelector('.case-amount')?.textContent.trim(),
                  signals: [...root.querySelectorAll('.case-signals li.signal')].map((s) => ({
                    label: s.querySelector('strong')?.textContent.trim(),
                    severity: s.className.replace('signal', '').trim(),
                    detail: s.querySelector('span')?.textContent.trim(),
                  })),
                  credits: credits.map((f) => ({
                    verdict: f.querySelector('.verdict')?.textContent.trim(),
                    says: f.querySelector('.finding-suggestion p')?.textContent.trim(),
                    uncertainty: f.querySelector('.finding-uncertainty')?.textContent.trim(),
                    citations: f.querySelectorAll('.finding-citation').length,
                  })),
                };
                """
            ),
            timeout=240,
        )
        note("creditCase", credit)
        driver.screenshot(evidence.path("credit"))

        # The amount is shown as the negative it is, rather than as a number
        # whose sign a reader has to infer from the word "kredit" somewhere.
        if "-" not in credit["amount"] and "−" not in credit["amount"]:
            raise AcceptanceError(f"A credit invoice was not shown as negative: {credit!r}")
        labels = [s["label"] for s in credit["signals"]]
        if "Möjlig kreditfaktura" not in labels:
            raise AcceptanceError(f"The queue signal for a credit was not raised: {labels!r}")
        # A credit relation is a reading, not a warning: an exactly cancelling
        # pair is a normal, correct thing to find.
        credit_signal = next(s for s in credit["signals"] if s["label"] == "Möjlig kreditfaktura")
        if credit_signal["severity"] != "info":
            raise AcceptanceError(f"A credit was raised as an alarm: {credit_signal!r}")
        # It names the invoice it cancels, the right way round, and says what
        # it cannot know.
        if not any("2027-018" in c["says"] for c in credit["credits"]):
            raise AcceptanceError(
                f"The credit never named the invoice it cancels: {credit['credits']!r}"
            )
        for card in credit["credits"]:
            if "Den här posten är negativ" not in card["says"]:
                raise AcceptanceError(f"The credit was stated backwards: {card!r}")
            if not card["uncertainty"] or "hör till" not in card["uncertainty"]:
                raise AcceptanceError(
                    f"The credit did not say which invoice it cannot decide about: {card!r}"
                )
            if card["citations"]:
                raise AcceptanceError(
                    "A history comparison carried a citation — citations mean a verified "
                    f"passage in a document, and there is none behind this: {card!r}"
                )
        controls = driver.execute(
            "return [...document.querySelectorAll('button')].map(b => b.textContent.trim().toLowerCase());"
        )
        settling = [
            c
            for c in controls
            if any(word in c for word in ("kvitta", "matcha mot", "godkänn faktura", "attestera", "betala"))
        ]
        note("creditControls", {"forbidden": settling, "count": len(controls)})
        if settling:
            raise AcceptanceError(f"The credit view offered a control that settles: {settling!r}")

        driver.click_text("Till fakturakön")
        queue = wait_until(
            "the worked cases in the queue",
            lambda: driver.execute(
                """
                const rows = [...document.querySelectorAll('.invoices-queue tbody tr')];
                if (rows.length < 3) return false;
                return rows.map((r) => {
                  const cells = [...r.querySelectorAll('td')].map(c => c.textContent.trim());
                  // Where a case has been seen is part of its identity and is
                  // read in the first cell beside the invoice number, rather
                  // than in a column of its own.
                  return {
                    invoice: cells[0],
                    amount: cells[1],
                    due: cells[2],
                    accounting: cells[3],
                    review: cells[4],
                    signal: cells[5],
                    responsible: cells[6],
                    lastActivity: cells[7],
                  };
                });
                """
            ),
            timeout=60,
        )
        note("queue", queue)
        counts = driver.execute(
            "return [...document.querySelectorAll('.invoices-counts > div')]"
            ".map(d => d.textContent.trim());"
        )
        note("counts", counts)
        driver.screenshot(evidence.path("queue"))

        # Inkommande must no longer carry an invoice pane.
        driver.click_text("Inkommande")
        tabs = wait_until(
            "the incoming shell",
            lambda: driver.execute(
                "const t = [...document.querySelectorAll('.integrations-tabs button')]"
                ".map(b => b.textContent.trim()); return t.length ? t : false;"
            ),
            timeout=60,
        )
        note("incomingTabs", tabs)
        if any("Faktura" in t for t in tabs):
            raise AcceptanceError(f"Inkommande still reviews invoices: {tabs!r}")

        receipt = write_receipt(
            evidence, args.application, started, ok=True,
            transport_retries=driver.transport_retries,
        )
        print(f"\nJOURNEY OK\nEvidence: {evidence.dir}\nReceipt:  {receipt}")
        return 0
    except Exception as exc:  # noqa: BLE001 - this is a driver script
        print(f"\nJOURNEY FAILED: {exc}")
        try:
            driver.screenshot(evidence.path(FAILURE_SCREENSHOT))
            print(driver.execute("return document.body.innerText.slice(0, 3000);"))
        except Exception:  # noqa: BLE001
            pass
        print("\nDriver tail:\n" + "\n".join(driver_logs[-25:]))
        failed = write_receipt(
            evidence, args.application, started, ok=False,
            transport_retries=driver.transport_retries,
        )
        print(f"\nReceipt: {failed}")
        return 1
    finally:
        try:
            driver.close()
        except Exception:  # noqa: BLE001
            pass
        process.terminate()
        if args.keep_data:
            print(f"Isolated XDG home kept at {home}")
        else:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
