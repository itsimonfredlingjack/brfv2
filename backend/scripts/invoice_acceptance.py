"""One invoice, driven through the real installed application, end to end.

Run from the repository root after ``make desktop-build`` (or ``make
invoice-acceptance``, which does both)::

    backend/.venv/bin/python backend/scripts/invoice_acceptance.py [evidence-dir]

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
8. **Inkommande no longer reviews invoices**, so the product cannot grow two
   invoice screens that disagree.

Evidence lands in the directory given as the single positional argument
(screenshots plus ``journey.json``), defaulting to
``/tmp/brfv2-invoice-acceptance``.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from scripts.desktop_acceptance import (  # noqa: E402
    DRIVER_ORIGIN,
    AcceptanceError,
    WebDriver,
    isolated_environment,
    set_select,
    wait_until,
)

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/brfv2-invoice-acceptance")
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = OUT / "shots"
SHOTS.mkdir(exist_ok=True)

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


def main() -> int:
    environment = isolated_environment(OUT / "home")
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
        driver.create_session(APPLICATION)
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
        driver.screenshot(SHOTS / "01-queue-empty.png")

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
        driver.screenshot(SHOTS / "02-case.png")

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
            driver.screenshot(SHOTS / "03-citation.png")
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
        driver.screenshot(SHOTS / "04-case-worked.png")

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
        driver.screenshot(SHOTS / "05-change.png")
        for needle in ("4 625,00 SEK", "+74,0 %", "förklarar", "förklarar den inte"):
            if needle not in change["suggestion"]:
                raise AcceptanceError(f"The change breakdown never said {needle!r}: {change!r}")

        driver.click_text("Till fakturakön")
        queue = wait_until(
            "two cases in the queue",
            lambda: driver.execute(
                """
                const rows = [...document.querySelectorAll('.invoices-queue tbody tr')];
                if (rows.length < 2) return false;
                return rows.map((r) => {
                  const cells = [...r.querySelectorAll('td')].map(c => c.textContent.trim());
                  return {
                    invoice: cells[0],
                    amount: cells[1],
                    due: cells[2],
                    source: cells[3],
                    accounting: cells[4],
                    review: cells[5],
                    signal: cells[6],
                    responsible: cells[7],
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
        driver.screenshot(SHOTS / "06-queue.png")

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

        (OUT / "journey.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\nJOURNEY OK")
        return 0
    except Exception as exc:  # noqa: BLE001 - this is a driver script
        print(f"\nJOURNEY FAILED: {exc}")
        try:
            driver.screenshot(SHOTS / "99-failure.png")
            print(driver.execute("return document.body.innerText.slice(0, 3000);"))
        except Exception:  # noqa: BLE001
            pass
        print("\nDriver tail:\n" + "\n".join(driver_logs[-25:]))
        (OUT / "journey.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 1
    finally:
        try:
            driver.close()
        except Exception:  # noqa: BLE001
            pass
        process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
