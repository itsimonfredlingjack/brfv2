"""The association's website, built and published through the real application.

Run from the repository root after ``make desktop-build`` (or ``make
website-acceptance``, which does both)::

    backend/.venv/bin/python backend/scripts/website_acceptance.py [--run-label ...]

Why this exists beside the other three journeys: they walk the answer loop, the
invoice loop and the incoming-post chain. This one walks the sentence the
website feature is *for* —

    utkast → block → redigering → publicering → utkastet ändras igen → återställning

**No model is required**, and as with the intake journey that is a property of
the feature rather than a convenience of the script: building and publishing a
page is deterministic end to end. The AI partner is asked for exactly one thing
here — to prove it refuses when there is no model to ask — because "refuse
rather than guess" is the behaviour that must survive an installation that never
configured generation.

What it asserts, in order:

1. A website that does not exist yet **says so** rather than rendering an empty
   editor, and creating it is a deliberate act.
2. The canvas is a **real same-origin viewport**: the site renders inside an
   iframe, with the site's own light document rather than the application's
   dark one — the CSS isolation the whole editing model rests on.
3. A block added from the library **lands as a command**, and appears in the
   canvas the operator is looking at.
4. Editing a field in the floating panel changes the page, and the change is in
   the association's own history with a name on it.
5. The mobile control is a **real width**, not a class name: 390 px, laid out by
   the same stylesheet the published page uses.
6. Publishing puts the page in front of the public.
7. **The draft cannot reach the public.** Editing after publication — including
   moving the page's address — changes nothing a visitor sees until somebody
   publishes again. This is the boundary the feature is built around, and it is
   asserted from the outside, through the product's own published view.
8. Rollback republishes an earlier version without rewriting anything, and the
   draft is left alone.
9. The AI partner, on an installation with no model, **writes nothing and says
   so**.
10. The history is append-only in fact: undoing a change appends, and never
    edits what is already recorded.

**Where the evidence goes.** ``docs/evidence`` by default, under the run's own
label — ``<label>-website-<view>.png`` beside a machine-readable
``<label>-website-acceptance.json``. Evidence git already tracks is never
overwritten without ``--overwrite-evidence``.
"""

from __future__ import annotations

import argparse
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

from app.integrations import models as _integration_models  # noqa: E402, F401
from scripts.desktop_acceptance import (  # noqa: E402
    DRIVER_ORIGIN,
    AcceptanceError,
    Evidence,
    WebDriver,
    application_identity,
    isolated_environment,
    wait_until,
)

WEBSITE_SCREENSHOTS: tuple[str, ...] = (
    "empty",
    "canvas",
    "selected",
    "mobile",
    "published",
    "versions",
)
FAILURE_SCREENSHOT = "failure"

APPLICATION = REPO / "src-tauri" / "target" / "release" / "brfv2-desktop"

BRF_NAME = "Gjutformen 12"
OWNER = ("Webbansvarig", "webb@gjutformen12.example", "webb-losenord-2026")

FIRST_HEADING = "Brf Gjutformen 12"
EDITED_HEADING = "Välkommen till Brf Gjutformen 12"
DRAFT_ONLY_HEADING = "Den här texten är bara ett utkast"
MOVED_SLUG = "hem"

results: dict = {}


def note(step: str, payload) -> None:
    results[step] = payload
    print(f"  · {step}: {json.dumps(payload, ensure_ascii=False)[:300]}")


def api(driver: WebDriver, path: str) -> dict:
    """Read one of the product's own endpoints from inside the application.

    The published view is asserted through the API the public renderer uses,
    not by re-deriving it here — the point is that *the product* says the draft
    has not reached the public, not that this script can compute the same thing.
    """
    return driver.execute_async(
        """
        const done = arguments[arguments.length - 1];
        fetch(arguments[0], { credentials: 'include' })
          .then((r) => r.json().then((body) => done({ status: r.status, body })))
          .catch((error) => done({ error: String(error) }));
        """,
        [path],
    )


def brf_id(driver: WebDriver) -> str:
    memberships = driver.execute_async(
        """
        const done = arguments[arguments.length - 1];
        fetch('/api/auth/me', { credentials: 'include' })
          .then((r) => r.json())
          .then((me) => done(me.memberships || []))
          .catch(() => done([]));
        """
    )
    if not memberships:
        raise AcceptanceError("No membership resolved for the provisioned owner")
    return memberships[0]["brf_id"]


def set_inspector_field(driver: WebDriver, label: str, value: str) -> None:
    """Type into the floating panel's field with the given Swedish label."""
    ok = wait_until(
        f"the inspector field {label!r}",
        lambda: driver.execute(
            """
            const wanted = arguments[0];
            const root = document.querySelector('.site-inspector');
            if (!root) return false;
            const field = [...root.querySelectorAll('label')]
              .find((l) => l.textContent.trim().startsWith(wanted))
              ?.querySelector('input, textarea');
            if (!field || field.disabled) return false;
            const proto = field.tagName === 'TEXTAREA'
              ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(field, arguments[1]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            return field.value === arguments[1];
            """,
            [label, value],
        ),
        timeout=30,
    )
    if not ok:
        raise AcceptanceError(f"Could not set the inspector field {label!r}")


def canvas_text(driver: WebDriver) -> str:
    return driver.execute(
        """
        const frame = document.querySelector('.site-canvas iframe');
        const doc = frame && frame.contentDocument;
        return doc ? doc.body.innerText : '';
        """
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", type=Path, default=APPLICATION)
    parser.add_argument("--artifact", type=Path, default=None)
    parser.add_argument("--evidence-dir", type=Path, default=REPO / "docs/evidence")
    parser.add_argument("--run-label", default="local")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="Permit this run to overwrite committed evidence files.",
    )
    parser.add_argument("--keep-data", action="store_true")
    return parser.parse_args(argv)


def write_receipt(evidence: Evidence, application: Path, artifact: Path | None,
                  started: float, *, ok: bool, transport_retries: int) -> Path:
    payload = {
        "schema": "brfv2-website-acceptance/v1",
        "runLabel": evidence.label,
        "ok": ok,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "durationSeconds": round(time.time() - started, 1),
        "application": application_identity(application, artifact),
        "transportRetries": transport_retries,
        "steps": results,
        "screenshots": [
            evidence.reference(name)
            for name in WEBSITE_SCREENSHOTS
            if evidence.path(name).is_file()
        ] + (
            [evidence.reference(FAILURE_SCREENSHOT)]
            if evidence.path(FAILURE_SCREENSHOT).is_file()
            else []
        ),
    }
    evidence.receipt.parent.mkdir(parents=True, exist_ok=True)
    evidence.receipt.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence.receipt


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    evidence = Evidence(
        args.evidence_dir,
        args.run_label,
        receipt=args.output,
        kind="website",
        views=(*WEBSITE_SCREENSHOTS, FAILURE_SCREENSHOT),
    )
    committed = evidence.tracked()
    if committed and not args.overwrite_evidence:
        listing = "\n  ".join(committed)
        raise AcceptanceError(
            f"Run label {args.run_label!r} writes over evidence that is committed:\n  {listing}\n"
            "Give this run its own --run-label, or pass --overwrite-evidence."
        )
    evidence.dir.mkdir(parents=True, exist_ok=True)
    if not args.application.is_file():
        raise AcceptanceError(f"Application missing: {args.application}; run make desktop-build")

    home = Path(tempfile.mkdtemp(prefix="brfv2-website-acceptance-"))
    started = time.time()
    environment = isolated_environment(home)
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

        # -- provision, without a model -------------------------------------
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
        driver.click_text("Hoppa över")
        wait_until(
            "workspace",
            lambda: driver.execute("return Boolean(document.querySelector('.user-profile'));"),
            timeout=180,
        )
        health = api(driver, "/api/health")["body"]
        if health.get("llm", {}).get("ready"):
            raise AcceptanceError(f"This journey must run without generation: {health!r}")
        note("withoutModel", {"mode": health.get("mode"), "llm": health.get("llm")})
        tenant = brf_id(driver)

        # -- 1. a website that does not exist says so ------------------------
        driver.click_text("Hemsidan")
        empty = wait_until(
            "the empty website workspace",
            lambda: driver.execute(
                """
                const card = document.querySelector('.site-start__card');
                if (!card) return false;
                return {
                  says: card.querySelector('p')?.textContent.trim() || '',
                  create: Boolean([...card.querySelectorAll('button')]
                    .find((b) => b.textContent.includes('Skapa startsidan'))),
                  canvas: Boolean(document.querySelector('.site-canvas')),
                };
                """
            ),
            timeout=120,
        )
        if empty["canvas"] or not empty["create"] or not empty["says"]:
            raise AcceptanceError(f"An unstarted website must say so, not render an editor: {empty!r}")
        before = api(driver, f"/api/brf/{tenant}/website")["body"]
        if before["pages"]:
            raise AcceptanceError("Reading the workspace created a site — a read must not write")
        note("emptyWorkspace", {**empty, "pagesAfterRead": len(before["pages"])})
        driver.screenshot(evidence.path("empty"))

        # -- 2. the canvas is a real same-origin viewport --------------------
        driver.click_text("Skapa startsidan")
        canvas = wait_until(
            "the editable canvas",
            lambda: driver.execute(
                """
                const frame = document.querySelector('.site-canvas iframe');
                const doc = frame && frame.contentDocument;   // same-origin or this is null
                const site = doc && doc.querySelector('.brf-site');
                if (!site) return false;
                return {
                  sameOrigin: true,
                  siteBackground: getComputedStyle(site).backgroundColor,
                  appBackground: getComputedStyle(document.body).backgroundColor,
                  width: Math.round(frame.getBoundingClientRect().width),
                };
                """
            ),
            timeout=180,
        )
        if canvas["siteBackground"] == canvas["appBackground"]:
            raise AcceptanceError(
                f"The site inside the canvas wears the application's own document: {canvas!r}"
            )
        note("canvas", canvas)

        # -- 3. a block from the library lands as a command ------------------
        driver.click_text("Lägg till block")
        driver.click('button[aria-label="Lägg till Toppsektion"]')
        wait_until(
            "the block in the canvas",
            lambda: FIRST_HEADING in canvas_text(driver) or "Välkommen" in canvas_text(driver),
            timeout=60,
        )
        page = api(driver, f"/api/brf/{tenant}/website")["body"]["pages"][0]
        history = api(driver, f"/api/brf/{tenant}/website")["body"]["history"]
        if not any("Toppsektion" in t["summary"] for t in history):
            raise AcceptanceError(f"Adding a block left no record of itself: {history!r}")
        note("blockAdded", {"blocks": page["block_count"], "summary": history[0]["summary"]})
        driver.screenshot(evidence.path("canvas"))

        # -- 4. editing a field, through the floating panel ------------------
        driver.execute(
            """
            const frame = document.querySelector('.site-canvas iframe');
            const heading = frame.contentDocument.querySelector('.blk-hero');
            heading.scrollIntoView({ block: 'center' });
            heading.click();
            """
        )
        wait_until(
            "the floating panel",
            lambda: driver.execute("return Boolean(document.querySelector('.site-inspector'));"),
            timeout=60,
        )
        driver.screenshot(evidence.path("selected"))
        set_inspector_field(driver, "Rubrik", EDITED_HEADING)
        wait_until(
            "the edit in the canvas",
            lambda: EDITED_HEADING in canvas_text(driver),
            timeout=60,
        )
        wait_until(
            "the edit in the association's history",
            lambda: any(
                "Ändrade" in t["summary"]
                for t in api(driver, f"/api/brf/{tenant}/website")["body"]["history"]
            ),
            timeout=60,
        )
        note("edited", {"heading": EDITED_HEADING})

        # -- 5. mobile is a real width ---------------------------------------
        driver.click_text("Mobil")
        mobile = wait_until(
            "the mobile viewport",
            lambda: driver.execute(
                """
                const canvas = document.querySelector('.site-canvas');
                const frame = canvas && canvas.querySelector('iframe');
                if (!frame) return false;
                const width = Math.round(canvas.getBoundingClientRect().width);
                if (width > 420) return false;
                const doc = frame.contentDocument;
                const hero = doc.querySelector('.blk-hero__inner');
                return {
                  canvasWidth: width,
                  frameWidth: Math.round(frame.getBoundingClientRect().width),
                  heroColumns: hero ? getComputedStyle(hero).gridTemplateColumns : '',
                };
                """
            ),
            timeout=60,
        )
        note("mobileViewport", mobile)
        driver.screenshot(evidence.path("mobile"))
        driver.click_text("Dator")

        # -- 6. publishing puts it in front of the public --------------------
        driver.click_text("Publicera")
        published = wait_until(
            "the published page",
            lambda: (
                api(driver, f"/api/brf/{tenant}/website/published")["body"]["pages"] or False
            ),
            timeout=120,
        )
        if EDITED_HEADING not in json.dumps(published, ensure_ascii=False):
            raise AcceptanceError(f"The published page does not carry the edit: {published!r}")
        first_slug = published[0]["slug"]
        note("published", {"seq": published[0]["seq"], "slug": first_slug})
        driver.screenshot(evidence.path("published"))

        # -- 7. the draft cannot reach the public ----------------------------
        # The invariant the whole feature is built around, asserted from
        # outside: change the draft — including the page's address — and read
        # the product's own published view back.
        set_inspector_field(driver, "Ingress", DRAFT_ONLY_HEADING)
        driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch(`/api/brf/${arguments[0]}/website/commands`, {
              method: 'POST', credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ operations: [{
                command: 'rename_page', page_id: arguments[1],
                title: 'Startsidan', slug: arguments[2],
              }], summary: 'Bytte adress i utkastet' }),
            }).then((r) => done(r.status)).catch((e) => done(String(e)));
            """,
            [tenant, page["id"], MOVED_SLUG],
        )
        still = wait_until(
            "the public view after a draft change",
            lambda: api(driver, f"/api/brf/{tenant}/website/published")["body"],
            timeout=60,
        )
        leaked = json.dumps(still, ensure_ascii=False)
        if DRAFT_ONLY_HEADING in leaked:
            raise AcceptanceError(f"A draft edit reached the public: {still!r}")
        if still["pages"][0]["slug"] != first_slug:
            raise AcceptanceError(
                f"Renaming the draft moved the published address: {still['pages'][0]['slug']!r}"
            )
        note("draftStaysInTheDraft", {
            "publishedSlug": still["pages"][0]["slug"],
            "draftSlug": MOVED_SLUG,
            "draftTextLeaked": False,
        })

        # …and one publication later it is live, address and all.
        driver.click_text("Publicera")
        moved = wait_until(
            "the second publication",
            lambda: (
                api(driver, f"/api/brf/{tenant}/website/published")["body"]["pages"][0]
                if api(driver, f"/api/brf/{tenant}/website/published")["body"]["pages"]
                else False
            ),
            timeout=120,
        )
        if moved["slug"] != MOVED_SLUG or DRAFT_ONLY_HEADING not in json.dumps(moved, ensure_ascii=False):
            raise AcceptanceError(f"Publishing did not carry the draft forward: {moved!r}")
        note("publishedAgain", {"seq": moved["seq"], "slug": moved["slug"]})

        # -- 8. rollback republishes without rewriting -----------------------
        driver.click_text("Versioner")
        wait_until(
            "the version list",
            lambda: driver.execute(
                "return document.querySelectorAll('.site-revisions li').length >= 2;"
            ),
            timeout=60,
        )
        driver.screenshot(evidence.path("versions"))
        driver.click_text("Återställ")
        rolled = wait_until(
            "the rollback",
            lambda: (
                api(driver, f"/api/brf/{tenant}/website/published")["body"]["pages"][0]
                if api(driver, f"/api/brf/{tenant}/website/published")["body"]["pages"]
                else False
            ),
            timeout=120,
        )
        if DRAFT_ONLY_HEADING in json.dumps(rolled, ensure_ascii=False):
            raise AcceptanceError(f"Rollback did not take the newer version down: {rolled!r}")
        draft_after = api(driver, f"/api/brf/{tenant}/website/pages/{page['id']}")["body"]
        if DRAFT_ONLY_HEADING not in json.dumps(draft_after, ensure_ascii=False):
            raise AcceptanceError(
                "Rollback threw away what somebody had written in the draft — it must not"
            )
        note("rolledBack", {
            "publicSeq": rolled["seq"],
            "draftKeptItsText": True,
            "revisions": len(
                api(driver, f"/api/brf/{tenant}/website/pages/{page['id']}/revisions")["body"]["revisions"]
            ),
        })

        # -- 9. no model means no invention ----------------------------------
        refusal = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch(`/api/brf/${arguments[0]}/website/ai`, {
              method: 'POST', credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ instruction: 'Skriv en sida om föreningens regler' }),
            }).then((r) => r.json()).then(done).catch((e) => done({ error: String(e) }));
            """,
            [tenant],
        )
        if refusal.get("applied"):
            raise AcceptanceError(
                f"The AI partner wrote to the page on an installation with no model: {refusal!r}"
            )
        note("aiRefusesWithoutModel", {
            "applied": refusal.get("applied"),
            "refusal": (refusal.get("refusal") or refusal.get("message") or "")[:200],
        })

        # -- 10. the history is append-only in fact --------------------------
        workspace = api(driver, f"/api/brf/{tenant}/website")["body"]
        undoable = next((t for t in workspace["history"] if t["undoable"]), None)
        if undoable is None:
            raise AcceptanceError("Nothing in the history could be undone")
        recorded = {t["id"]: t for t in workspace["history"]}
        undone = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch(`/api/brf/${arguments[0]}/website/transactions/${arguments[1]}/undo`, {
              method: 'POST', credentials: 'include',
            }).then((r) => r.json()).then(done).catch((e) => done({ error: String(e) }));
            """,
            [tenant, undoable["id"]],
        )
        after = api(driver, f"/api/brf/{tenant}/website")["body"]["history"]
        for entry in after:
            was = recorded.get(entry["id"])
            if was is None:
                continue
            # Everything stored keeps saying what it said. `undone_by` is
            # derived at read time, so it is excluded from the comparison — that
            # is the whole point of deriving it.
            if {k: v for k, v in entry.items() if k not in ("undone_by", "undoable")} != {
                k: v for k, v in was.items() if k not in ("undone_by", "undoable")
            }:
                raise AcceptanceError(f"An already-recorded history entry changed: {entry!r}")
        if not any(t["undoes"] == undoable["id"] for t in after):
            raise AcceptanceError("The undo left no record of what it undid")
        note("historyAppendOnly", {
            "undid": undoable["summary"],
            "entriesBefore": len(workspace["history"]),
            "entriesAfter": len(after),
            "undoTransaction": undone.get("transaction", {}).get("summary", ""),
        })

        receipt = write_receipt(
            evidence, args.application, args.artifact, started, ok=True,
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
            evidence, args.application, args.artifact, started, ok=False,
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
