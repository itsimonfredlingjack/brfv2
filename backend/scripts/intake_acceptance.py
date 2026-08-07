"""One piece of incoming post, driven through the real installed application.

Run from the repository root after ``make desktop-build`` (or ``make
intake-acceptance``, which does both)::

    backend/.venv/bin/python backend/scripts/intake_acceptance.py [--run-label ...]

Why this exists beside :mod:`scripts.desktop_acceptance` and
:mod:`scripts.invoice_acceptance`: those two walk the answer loop and the
invoice loop. This one walks the chain the incoming-post feature is *for*, and
that chain is the product's own sentence read left to right —

    källhändelse → proveniens → koppling → förslag → mänskligt beslut → sökbar historik

**No model is required**, and that is a property of the feature rather than of
the script: the queue's floor is deterministic — categories, dates, amounts and
suppliers come from rules over the text, using the product's own readers — so an
installation that has never configured generation can still review its post.

What it asserts, in order:

1. A queue with nothing in it **says so** rather than rendering empty.
2. An ``.eml`` a person picked becomes one card carrying its **provenance**:
   how it arrived, which adapter read it, who imported it, and the content hash
   the duplicate rule is enforced on.
3. The reading is **shown as a reading**: every signal carries the words it was
   read from, and a question is reported as looking like one awaiting a reply.
4. **Nothing is preserved without a stated reason.** The decision cannot be
   saved while the reason is empty, and the control says so rather than failing
   afterwards.
5. One human decision **preserves the message as an ordinary document and makes
   a task out of it** — and the task carries a *verified citation into that
   document*, which is the whole point of preserving first.
6. The preserved message opens in the archive at the cited page, through the
   application's own document navigation. A preserved message that cannot be
   opened is a claim, not a document.
7. **Reopening is not an erasure.** The card returns to the queue, what the
   decision produced stays exactly where it is, and the decision itself is
   filed in the item's own append-only ``decision_history``.
8. **A new decision is a new decision.** Deciding again puts a watch on the
   board with the same citation, without preserving the message a second time —
   and the earlier decision is still readable in the history beside it.

**Where the evidence goes.** ``docs/evidence`` by default, under the run's own
label — ``<label>-intake-<view>.png`` beside a machine-readable
``<label>-intake-acceptance.json``. Evidence git already tracks is never
overwritten without ``--overwrite-evidence``: that record is what an earlier
acceptance was approved on. The isolated ``XDG_DATA_HOME`` is a throwaway
temporary directory and is deliberately *not* in the evidence tree.
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

# The integrations package first, for the same import-cycle reason
# invoice_acceptance states: app.invoices and app.integrations reference each
# other's models, and the cycle only resolves when this side is entered first.
from app.integrations import models as _integration_models  # noqa: E402, F401
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

INTAKE_SCREENSHOTS: tuple[str, ...] = (
    "queue-empty",
    "card",
    "decided",
    "preserved-document",
    "task",
    "reopened",
    "watch",
)
FAILURE_SCREENSHOT = "failure"

APPLICATION = REPO / "src-tauri" / "target" / "release" / "brfv2-desktop"
MESSAGE = REPO / "backend" / "fixtures" / "mail" / "fraga-fran-medlem.eml"

BRF_NAME = "Gjutformen 12"
OWNER = ("Postgranskaren", "styrelsen@post.example", "post-losenord-2026")

# The message: a member asking when the snow-clearing on-call hours apply. It
# has no attachment on purpose — the post worth most to a board frequently has
# none, and a journey that only worked on invoices-with-a-PDF would be proving
# the attachment path rather than the queue.
SUBJECT = "Fråga om jourtid för snöröjning"
SENDER = "medlem@gjutformen12.example"

PRESERVE_REASON = "Medlemsfråga om jourtid — underlag för styrelsens svar."
TASK_TITLE = "Svara medlemmen om jourtid för snöröjning"
TASK_RESPONSIBLE = "Karin Lindqvist"
TASK_DUE = "2026-09-15"

# The second decision, taken after the first is reopened. A different person,
# a different outcome and a different date, so nothing about it could be the
# first decision leaking through.
SECOND_REASON = "Omtag: styrelsen vill ha svaret bevakat, inte bara en uppgift."
WATCH_DUE = "2026-10-01"

results: dict = {}


def note(step: str, payload) -> None:
    results[step] = payload
    print(f"  · {step}: {json.dumps(payload, ensure_ascii=False)[:300]}")


# ---------------------------------------------------------------------------
# Controls this journey needs that the shared harness does not have
# ---------------------------------------------------------------------------
#
# Same discipline as WebDriver._press: an interaction reports what actually
# happened to the control, never merely that something matching was found.


# Getting to one message's own pane, re-established on every single poll.
#
# The queue is master–detail: threads are chosen in the list on the left and
# worked in the pane on the right, where the messages, the reading and the
# decision form all live. Two things still stand between the queue and a settled
# message, and both are correct product behaviour: the default filter shows only
# what still needs a decision, so a thread that was just decided leaves the list;
# and the surrounding Inkommande pane reloads — unmounting the queue and
# resetting its filter and its selection — after every write, because a decision
# changes what the other pane shows too.
#
# So this is not a step the journey performs once. It is the preamble to every
# read and every interaction, and it repairs whatever the last re-render undid
# rather than assuming the screen stayed where it was put.
ENSURE_CARD = """
const subject = arguments[0];
if (!document.querySelector('.intake')) return null;
const row = [...document.querySelectorAll('.intake-list .thread-row')]
  .find((r) => r.innerText.includes(subject));
if (!row) {
  const all = document.querySelector('.intake-counts button[data-filter="all"]');
  if (all && all.getAttribute('aria-pressed') !== 'true') all.click();
  return null;
}
if (row.getAttribute('aria-current') !== 'true') {
  row.click();
  return null;
}
const detail = document.querySelector('.intake-detail .thread-detail');
if (!detail || !detail.innerText.includes(subject)) return null;
return detail;
"""


# What the product itself says happened, read through its own HTTP contract from
# inside the application's own page. The screen is where a journey belongs, but
# the queue deliberately does not render an item's filed decisions — the record
# is on the source event, not in a second archive — so the one assertion the DOM
# cannot make is made here instead of not at all.
READ_STATE = """
const done = arguments[arguments.length - 1];
fetch('/api/auth/me', { credentials: 'include' })
  .then((r) => r.json())
  .then((me) => {
    const id = me.memberships[0].brf_id;
    return Promise.all([
      fetch(`/api/brf/${id}/integrations/intake`, { credentials: 'include' }).then(r => r.json()),
      fetch(`/api/brf/${id}/tasks`, { credentials: 'include' }).then(r => r.json()),
      fetch(`/api/brf/${id}/documents`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([queue, tasks, documents]) => {
      const event = queue.threads[0].events[0];
      done({
        outcomes: (event.resolution?.outcomes || []).map((o) => o.kind),
        resolutionPresent: Boolean(event.resolution),
        decisionHistory: (event.decision_history || []).map((record) => ({
          decidedBy: record.resolution.decided_by,
          note: record.resolution.note,
          outcomes: record.resolution.outcomes.map((o) => o.kind),
          supersededBy: record.superseded_by,
        })),
        preservedDocumentId: event.preserved_document_id,
        activeTasks: tasks.active.length,
        documents: documents.length,
      });
    });
  })
  .catch((error) => done({ error: String(error) }));
"""


def on_card(driver: WebDriver, subject: str, body: str, args: list | None = None):
    """Run *body* against the thread's detail pane, having first opened it.

    One round trip, so the state this establishes cannot be undone between
    establishing it and using it.
    """
    return driver.execute(
        "const article = (function () {\n" + ENSURE_CARD + "\n}).apply(this, arguments);\n"
        "if (!article) return false;\n" + body,
        [subject, *(args or [])],
    )


def tick(driver: WebDriver, subject: str, label: str) -> None:
    """Tick the outcome checkbox whose label reads *label*, and prove it took."""
    wait_until(
        f"the outcome {label!r}",
        lambda: on_card(
            driver,
            subject,
            """
            const wanted = arguments[1];
            const row = [...article.querySelectorAll('.resolve-options label')]
              .find((candidate) => candidate.textContent.trim() === wanted);
            if (!row) return false;
            const box = row.querySelector('input[type=checkbox]');
            if (!box || box.disabled) return false;
            if (!box.checked) box.click();
            return box.checked;
            """,
            [label],
        ),
        timeout=60,
    )


def fill(driver: WebDriver, subject: str, label: str, value: str) -> None:
    """Set the input of a label whose own text reads *label*.

    Not ``type_labelled``: the resolve form writes its label text as a bare text
    node rather than in a ``<span>``, and a helper that matched neither would
    set nothing and say nothing.
    """
    wait_until(
        f"the field labelled {label!r}",
        lambda: on_card(
            driver,
            subject,
            """
            const wanted = arguments[1];
            const field = [...article.querySelectorAll('label')]
              .find((candidate) => {
                const own = [...candidate.childNodes]
                  .filter((n) => n.nodeType === Node.TEXT_NODE)
                  .map((n) => n.textContent.trim())
                  .join(' ')
                  .trim();
                return own === wanted;
              })
              ?.querySelector('input');
            if (!field || field.disabled) return false;
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
              .set.call(field, arguments[2]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            return field.value === arguments[2];
            """,
            [label, value],
        ),
        timeout=60,
    )


def fill_note(driver: WebDriver, subject: str, value: str) -> None:
    """The reason. Its label changes wording with the outcomes, the class does not."""
    wait_until(
        "the decision's reason field",
        lambda: on_card(
            driver,
            subject,
            """
            const field = article.querySelector('.resolve-note input');
            if (!field || field.disabled) return false;
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
              .set.call(field, arguments[1]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            return field.value === arguments[1];
            """,
            [value],
        ),
        timeout=60,
    )


def press_on_card(driver: WebDriver, subject: str, label: str) -> None:
    """Press a control inside the card, proving it dispatched — as _press does."""
    state = wait_until(
        f"the control {label!r} on the card",
        lambda: on_card(
            driver,
            subject,
            """
            const wanted = arguments[1];
            const control = [...article.querySelectorAll('button')]
              .find((b) => b.textContent.trim().includes(wanted));
            if (!control || control.disabled) return false;
            let fired = false;
            const spy = () => { fired = true; };
            control.addEventListener('click', spy, true);
            try { control.click(); } finally {
              control.removeEventListener('click', spy, true);
            }
            return { fired };
            """,
            [label],
        ),
        timeout=60,
    )
    if not state.get("fired"):
        raise AcceptanceError(f"{label!r} on the card dispatched no click: {state!r}")


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
        help="Names this run's evidence: <label>-intake-<view>.png and "
        "<label>-intake-acceptance.json. Give each run that is to be kept its own "
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
    """The machine-readable half of the record, written pass or fail."""
    receipt = {
        "schema": "brfv2-intake-acceptance/v1",
        "ok": ok,
        "runLabel": evidence.label,
        "application": str(application),
        "applicationIdentity": application_identity(application, None),
        "durationSeconds": round(time.time() - started, 1),
        # Said in the record rather than only in a docstring: the review queue
        # is green on a machine with no GPU, no tunnel and no model configured.
        "modelRequired": False,
        "message": {"file": MESSAGE.name, "subject": SUBJECT, "sender": SENDER},
        "transportRetries": transport_retries,
        "screenshots": [
            evidence.reference(name)
            for name in INTAKE_SCREENSHOTS
            if evidence.path(name).is_file()
        ],
        "failureScreenshot": (
            evidence.reference(FAILURE_SCREENSHOT)
            if evidence.path(FAILURE_SCREENSHOT).is_file()
            else None
        ),
        "steps": results,
    }
    evidence.receipt.parent.mkdir(parents=True, exist_ok=True)
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
        kind="intake",
        views=(*INTAKE_SCREENSHOTS, FAILURE_SCREENSHOT),
    )
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
        raise AcceptanceError(f"Application missing: {args.application}; run make desktop-build")
    if not MESSAGE.is_file():
        raise AcceptanceError(f"Fixture message missing: {MESSAGE}")

    home = Path(tempfile.mkdtemp(prefix="brfv2-intake-acceptance-"))
    started = time.time()
    environment = isolated_environment(home)
    # As in the invoice journey: the operator's HF cache already holds the
    # embedder, and the packaged application never resolves it over the network.
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

        # -- provision -----------------------------------------------------
        wait_until(
            "first-run setup",
            lambda: driver.execute("return document.body.innerText.includes('Välkommen');"),
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
        # Skipped deliberately, and it is an assertion rather than a shortcut:
        # the queue's reading is deterministic, so this whole journey has to be
        # green on an installation that never configured generation.
        driver.click_text("Hoppa över")
        wait_until(
            "workspace",
            lambda: driver.execute("return Boolean(document.querySelector('.user-profile'));"),
            timeout=180,
        )
        model_state = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch('/api/health', { credentials: 'include' })
              .then(r => r.json())
              .then(health => done({ mode: health.mode, llm: health.llm }))
              .catch(error => done({ error: String(error) }));
            """
        )
        if model_state.get("llm", {}).get("ready"):
            raise AcceptanceError(
                f"This journey must prove itself without generation configured: {model_state!r}"
            )
        note("withoutModel", model_state)

        # -- an empty queue says it is empty --------------------------------
        driver.click_text("Inkommande")
        empty = wait_until(
            "the empty review queue",
            lambda: driver.execute(
                """
                if (!document.querySelector('.intake')) return false;
                const empty = document.querySelector('.intake .empty');
                if (!empty) return false;
                return {
                  says: empty.textContent.trim(),
                  cards: document.querySelectorAll('.intake-list .thread-row').length,
                  importControl: Boolean(document.querySelector('#intake-eml-import')),
                };
                """
            ),
            timeout=120,
        )
        if empty["cards"] != 0 or not empty["says"]:
            raise AcceptanceError(f"An empty queue must say so: {empty!r}")
        if not empty["importControl"]:
            raise AcceptanceError("The queue offers no way to import a message by hand")
        note("emptyQueue", empty)
        driver.screenshot(evidence.path("queue-empty"))

        # -- a person picks one .eml ----------------------------------------
        raw = MESSAGE.read_bytes()
        accepted = driver.execute(
            """
            const bytes = Uint8Array.from(atob(arguments[0]), (c) => c.charCodeAt(0));
            const file = new File([bytes], arguments[1], { type: 'message/rfc822' });
            const input = document.querySelector('#intake-eml-import');
            if (!input) return false;
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
            // Read before dispatching: the view's own change handler clears the
            // input so the same file can be picked twice, and it runs
            // synchronously inside dispatchEvent. Asking afterwards measures
            // that reset, not whether the file was staged.
            const staged = input.files.length === 1;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return staged;
            """,
            [base64.b64encode(raw).decode(), MESSAGE.name],
        )
        if not accepted:
            raise AcceptanceError("The queue refused the .eml import control")

        card = wait_until(
            "the imported message as a card",
            lambda: driver.execute(
                """
                const subject = arguments[0];
                const row = [...document.querySelectorAll('.intake-list .thread-row')]
                  .find((r) => r.innerText.includes(subject));
                if (!row) return false;
                if (row.getAttribute('aria-current') !== 'true') { row.click(); return false; }
                const detail = document.querySelector('.intake-detail .thread-detail');
                if (!detail || !detail.innerText.includes(subject)) return false;
                // Every reading, not only the first few the panel shows before it
                // is asked: the promise being checked is about all of them.
                const more = detail.querySelector('.signals-more');
                if (more && more.textContent.includes('Visa alla')) { more.click(); return false; }
                return {
                  subject: row.querySelector('.thread-subject')?.textContent.trim(),
                  meta: row.querySelector('.thread-meta')?.textContent.trim(),
                  badges: [...row.querySelectorAll('.thread-row-tags .tag')]
                    .map((b) => b.textContent.trim()),
                  suggestedBy: detail.querySelector('.reading-by')?.textContent.trim(),
                  signals: [...detail.querySelectorAll('.reading-signals li')].map((li) => ({
                    kind: li.querySelector('.signal-kind')?.textContent.trim(),
                    value: li.querySelector('.signal-value')?.textContent.trim(),
                    quote: li.querySelector('.signal-quote')?.textContent.trim(),
                  })),
                };
                """,
                [SUBJECT],
            ),
            timeout=180,
        )
        if not card["signals"]:
            raise AcceptanceError(f"The reading produced no signals to show: {card!r}")
        # Rule three of the screen: a reading is never shown as a fact. Every
        # signal must carry the words it was read out of.
        quoteless = [s for s in card["signals"] if not s.get("quote")]
        if quoteless:
            raise AcceptanceError(f"A signal was shown without its words: {quoteless!r}")
        if not any("vänta svar" in badge for badge in card["badges"]):
            raise AcceptanceError(f"A question did not read as awaiting a reply: {card!r}")
        note("card", card)

        provenance = wait_until(
            "the message's provenance",
            lambda: on_card(
                driver,
                SUBJECT,
                """
                const rows = [...article.querySelectorAll('.message-provenance div')];
                if (rows.length === 0) return false;
                const out = {};
                for (const row of rows) {
                  out[row.querySelector('dt')?.textContent.trim()] =
                    row.querySelector('dd')?.textContent.trim();
                }
                return out;
                """
            ),
            timeout=60,
        )
        how = provenance.get("Hur det kom hit", "")
        if "manual-file-import" not in how:
            raise AcceptanceError(f"A hand-picked file did not say so in its provenance: {how!r}")
        if not provenance.get("Innehållshash"):
            raise AcceptanceError(f"The card shows no content hash: {provenance!r}")
        note("provenance", provenance)
        driver.screenshot(evidence.path("card"))

        # -- nothing is preserved without a stated reason --------------------
        tick(driver, SUBJECT, "Ta in")
        tick(driver, SUBJECT, "Skapa uppgift")
        guard = on_card(
            driver,
            SUBJECT,
            """
            const submit = article.querySelector('.resolve-submit');
            return {
              disabled: submit?.disabled === true,
              title: submit?.getAttribute('title') || '',
              asks: article.querySelector('.resolve-note')?.textContent.trim() || '',
            };
            """,
        )
        if not guard["disabled"]:
            raise AcceptanceError(
                f"The decision could be saved with no reason for preserving: {guard!r}"
            )
        if "krävs" not in guard["asks"]:
            raise AcceptanceError(f"The form does not say the reason is required: {guard!r}")
        note("reasonRequired", guard)

        # -- one human decision: preserve, and make it somebody's job --------
        fill(driver, SUBJECT, "Rubrik", TASK_TITLE)
        fill(driver, SUBJECT, "Ansvarig", TASK_RESPONSIBLE)
        fill(driver, SUBJECT, "Klart senast", TASK_DUE)
        fill_note(driver, SUBJECT, PRESERVE_REASON)
        press_on_card(driver, SUBJECT, "Spara beslutet")

        decided = wait_until(
            "the decision, and what it produced",
            lambda: on_card(
                driver,
                SUBJECT,
                """
                const box = article.querySelector('.resolution');
                if (!box) return false;
                return {
                  head: box.querySelector('h5')?.textContent.trim(),
                  outcomes: [...box.querySelectorAll('li')].map((li) => li.textContent.trim()),
                  note: box.querySelector('.resolution-note')?.textContent.trim() || '',
                  opensDocument: Boolean([...box.querySelectorAll('button')]
                    .find((b) => b.textContent.includes('Öppna dokumentet'))),
                  reopen: Boolean(box.querySelector('.reopen')),
                };
                """
            ),
            timeout=180,
        )
        if not decided["opensDocument"]:
            raise AcceptanceError(f"The preserved message offers no way in: {decided!r}")
        joined = " ".join(decided["outcomes"])
        for expected in ("bevarad som dokument", "Skapa uppgift"):
            if expected not in joined:
                raise AcceptanceError(f"The decision lost {expected!r}: {decided!r}")
        if PRESERVE_REASON not in decided["note"]:
            raise AcceptanceError(f"The stated reason was not kept: {decided!r}")
        note("firstDecision", decided)
        driver.screenshot(evidence.path("decided"))

        # -- the preserved message is an ordinary, openable document ---------
        #
        # The archive is checked first, and deliberately: a message that was
        # preserved while the workspace was open must be in the association's
        # document list without a reload, or the control beside it that offers
        # to open it is offering something that is not there yet.
        driver.click_text("Dokument")
        archived_first = wait_until(
            "the preserved message in the document archive",
            lambda: driver.execute(
                "return document.body.innerText.includes(arguments[0]) "
                "&& !document.body.innerText.includes('Laddar upp…');",
                [SUBJECT],
            ),
            timeout=120,
        )
        note("inArchiveWithoutReload", bool(archived_first))
        driver.click_text("Inkommande")
        wait_until(
            "the card again",
            lambda: on_card(driver, SUBJECT, "return Boolean(article.querySelector('.resolution'));"),
            timeout=120,
        )
        press_on_card(driver, SUBJECT, "Öppna dokumentet")
        preserved = wait_until(
            "the preserved message open in the archive",
            lambda: driver.execute(
                """
                const title = document.querySelector('.workspace-doc-title')?.textContent.trim();
                if (!title) return false;
                const canvas = document.querySelector('.pdf-page-canvas-wrap canvas');
                // The canvas element exists before pdf.js has laid the page out
                // and painted it. Probing only for the element photographs the
                // spinner and calls it a rendered document, so the page has to
                // have real dimensions and the loading state has to be gone.
                if (!canvas || !canvas.width || !canvas.height) return false;
                if (document.querySelector('.pdf-pane-loading')) return false;
                return {
                  document: title,
                  page: document.querySelector('[data-testid=pdf-page-indicator]')
                    ?.textContent.trim(),
                  canvas: { width: canvas.width, height: canvas.height },
                };
                """
            ),
            timeout=180,
        )
        if SUBJECT not in preserved["document"]:
            raise AcceptanceError(f"The opened document is not the message: {preserved!r}")
        note("preservedDocument", preserved)
        driver.screenshot(evidence.path("preserved-document"))

        # -- the task carries a citation into that document ------------------
        # Out of the document viewer first: it takes over the workspace, and
        # the areas in the sidebar are not reachable from inside it.
        driver.click_text("Tillbaka")
        driver.click_text("Uppgifter")
        task = wait_until(
            "the task the post produced",
            lambda: driver.execute(
                """
                const cards = [...document.querySelectorAll('.tasks-active .task')];
                const card = cards.find((c) => c.innerText.includes(arguments[0]));
                if (!card) return false;
                return {
                  active: cards.length,
                  origin: card.querySelector('.task-origin-kind')?.textContent.trim(),
                  text: card.innerText.replace(/\\n/g, ' '),
                  citations: [...card.querySelectorAll('.task-citation')]
                    .map((c) => c.textContent.trim().slice(0, 120)),
                  events: card.querySelectorAll('.task-event').length,
                };
                """,
                [TASK_TITLE],
            ),
            timeout=120,
        )
        if task["origin"] != "Inkommande post":
            raise AcceptanceError(f"The task forgot where it came from: {task!r}")
        if TASK_RESPONSIBLE not in task["text"]:
            raise AcceptanceError(f"The task lost its owner: {task!r}")
        if not task["citations"]:
            raise AcceptanceError(
                f"The task carries no citation into the preserved message: {task!r}"
            )
        if not any(SUBJECT in citation for citation in task["citations"]):
            raise AcceptanceError(f"The task's citation points elsewhere: {task!r}")
        if task["events"] < 1:
            raise AcceptanceError(f"The task has no history: {task!r}")
        note("taskFromPost", task)
        driver.screenshot(evidence.path("task"))

        # -- reopening files the decision; it does not erase it --------------
        driver.click_text("Inkommande")
        wait_until(
            "the queue again",
            lambda: driver.execute("return Boolean(document.querySelector('.intake'));"),
            timeout=120,
        )
        press_on_card(driver, SUBJECT, "Öppna i kön igen")
        reopened = wait_until(
            "the item back in the queue",
            lambda: on_card(
                driver,
                SUBJECT,
                """
                if (article.querySelector('.resolution')) return false;
                if (!article.querySelector('.resolve')) return false;
                return {
                  badges: [...article.querySelectorAll('.detail-head-tags .tag')]
                    .map((b) => b.textContent.trim()),
                  offersOutcomes: article.querySelectorAll('.resolve-options label').length,
                };
                """,
            ),
            timeout=120,
        )
        note("reopened", reopened)

        # What the decision produced is untouched — the task is still work
        # somebody has, and reopening a card is not a decision about it.
        history = driver.execute_async(READ_STATE)
        if history.get("error"):
            raise AcceptanceError(f"Could not read the item's history: {history!r}")
        if history["resolutionPresent"]:
            raise AcceptanceError(f"A reopened item still carries a resolution: {history!r}")
        if len(history["decisionHistory"]) != 1:
            raise AcceptanceError(
                f"Reopening did not file the decision it replaced: {history!r}"
            )
        filed = history["decisionHistory"][0]
        if sorted(filed["outcomes"]) != ["create_task", "take_in"]:
            raise AcceptanceError(f"The filed decision is not the one taken: {filed!r}")
        if filed["note"] != PRESERVE_REASON:
            raise AcceptanceError(f"The filed decision lost its reason: {filed!r}")
        note("afterReopen", history)
        documents_before = history["documents"]
        driver.screenshot(evidence.path("reopened"))

        # -- a new human decision, on the same post --------------------------
        tick(driver, SUBJECT, "Ta in")
        tick(driver, SUBJECT, "Bevaka")
        set_select(driver, ".resolve-section select", "expected_reply")
        fill(driver, SUBJECT, "Datum", WATCH_DUE)
        fill_note(driver, SUBJECT, SECOND_REASON)
        press_on_card(driver, SUBJECT, "Spara beslutet")
        second = wait_until(
            "the second decision",
            lambda: on_card(
                driver,
                SUBJECT,
                """
                const box = article.querySelector('.resolution');
                if (!box) return false;
                const outcomes = [...box.querySelectorAll('li')].map((li) => li.textContent.trim());
                if (!outcomes.some((o) => o.includes('Bevaka'))) return false;
                return {
                  outcomes,
                  note: box.querySelector('.resolution-note')?.textContent.trim() || '',
                };
                """
            ),
            timeout=180,
        )
        if SECOND_REASON not in second["note"]:
            raise AcceptanceError(f"The second decision lost its reason: {second!r}")
        note("secondDecision", second)

        after = driver.execute_async(READ_STATE)
        if after.get("error"):
            raise AcceptanceError(f"Could not read the item after deciding again: {after!r}")
        if sorted(after["outcomes"]) != ["monitor", "take_in"]:
            raise AcceptanceError(f"The new decision is not the one taken: {after!r}")
        if len(after["decisionHistory"]) != 1:
            raise AcceptanceError(
                f"The earlier decision did not survive the new one: {after!r}"
            )
        if after["preservedDocumentId"] != history["preservedDocumentId"]:
            raise AcceptanceError(
                f"Preserving twice produced a second document: {after!r} vs {history!r}"
            )
        if documents_before is not None and after["documents"] != documents_before:
            raise AcceptanceError(
                f"The archive grew a duplicate of the message: {after!r}, was {documents_before}"
            )
        if after["activeTasks"] != history["activeTasks"]:
            raise AcceptanceError(f"The task the first decision made did not survive: {after!r}")
        note("afterSecondDecision", after)

        # -- the date is on the board, with the same citation ----------------
        driver.click_text("Bevakningar")
        wait_until(
            "the watch board loaded",
            lambda: driver.execute("return Boolean(document.querySelector('.watches-board'));"),
            timeout=120,
        )
        watch = wait_until(
            "the watch the post produced",
            lambda: driver.execute(
                """
                const buckets = [...document.querySelectorAll('.watches-board .watch-bucket')];
                const cards = buckets.flatMap((b) =>
                  [...b.querySelectorAll('.watch.board')].map((c) => ({
                    bucket: b.getAttribute('aria-label'),
                    text: c.innerText.replace(/\\n/g, ' '),
                    citations: c.querySelectorAll('.watch-citation').length,
                  })));
                const found = cards.find((c) => c.text.includes(arguments[0]));
                if (!found) return false;
                return { onBoard: cards.length, ...found };
                """,
                [WATCH_DUE],
            ),
            timeout=120,
        )
        if watch["citations"] < 1:
            raise AcceptanceError(f"The watch carries no citation into the message: {watch!r}")
        if SUBJECT not in watch["text"]:
            raise AcceptanceError(f"The watch does not name the post it came from: {watch!r}")
        note("watchFromPost", watch)
        driver.screenshot(evidence.path("watch"))

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
