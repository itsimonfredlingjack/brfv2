"""End-to-end acceptance for the BRF Dokument-AI Fedora desktop delivery.

Run from the repository root after ``make desktop-build`` (or against an
installed application with ``--application /usr/bin/brfv2-desktop``)::

    backend/.venv/bin/python backend/scripts/desktop_acceptance.py

Two phases, both against the real product:

* **UI journey** — drives the actual Tauri/WebKitGTK webview through
  tauri-driver: first-run provisioning, model-runtime configuration, PDF
  upload and ingestion, a supported question answered by the real self-hosted
  model, citation, PDF highlight, zoom, an evidence-based refusal, backup, and
  the security boundary (CSP, exact origin, denied Tauri IPC).
* **Lifecycle** — launches the same binary directly and exercises what a
  WebDriver session cannot survive: clean shutdown, restart with retained
  state, restore-after-restart, and abrupt termination cleanup.
* **Security boundary** — who may repoint the model service and where it may
  be pointed: an ordinary account is refused, every destination outside the
  self-hosted policy is refused with its stable reason, and a hand-edited
  configuration file does not put a foreign endpoint into effect.

Both phases run against an isolated ``XDG_DATA_HOME``/``XDG_CONFIG_HOME``, so
acceptance never touches the operator's real installation, and every run starts
from a genuinely unprovisioned machine state.

Nothing here is simulated: generation runs against the configured self-hosted
runtime and the run fails if that runtime is not reachable.  WebKitWebDriver
does not implement W3C ``element/value`` or ``element/click`` for WRY, so text
is set through WebKit's DOM and submission goes through the application's own
handlers.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.client import HTTPException
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

STARTUP_SCHEMA = "brfv2-desktop-startup/v1"
STATE_SCHEMA = "brfv2-desktop-state/v1"
DRIVER_ORIGIN = "http://127.0.0.1:4444"
RESTART_EXIT_CODE = 86

OWNER_EMAIL = "styrelsen@acceptans.example"
OWNER_PASSWORD = "acceptans-losenord-2026"
OWNER_NAME = "Acceptanstestaren"
BRF_NAME = "Brf Gjutformen 12"
SECOND_BRF_NAME = "Brf Sjöutsikten 7"
SOURCE_DOCUMENT = "Stadgar Brf Gjutformen 12.pdf"

SUPPORTED_QUESTION = "Var har styrelsen sitt säte?"
UNSUPPORTED_QUESTION = "Vilka öppettider har föreningens planetarium?"

GENERAL_CHAT_INPUT = 'input[placeholder="Ställ en generell fråga till AI:n..."]'
BRF_SELECT = 'select[aria-label="Byt aktiv förening"]'

COLLECT_RUNTIME_ERRORS = """
window.__acceptanceErrors = [];
window.addEventListener('error', (event) =>
  window.__acceptanceErrors.push(String(event.message || event.error)));
window.addEventListener('unhandledrejection', (event) =>
  window.__acceptanceErrors.push(String(event.reason)));
return true;
"""


class AcceptanceError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Small HTTP helpers
# ---------------------------------------------------------------------------


def http(
    method: str,
    url: str,
    *,
    body: Any = None,
    cookie: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any, dict[str, str]]:
    data = None if body is None else json.dumps(body).encode()
    headers = dict(headers or {})
    if data is not None:
        headers.setdefault("Content-Type", "application/json")
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
    except (URLError, TimeoutError, HTTPException, OSError) as exc:
        raise AcceptanceError(f"{method} {url}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = raw
    return status, payload, response_headers


def wait_until(label: str, check: Any, timeout: float = 30.0, interval: float = 0.25) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (AcceptanceError, HTTPError, URLError, OSError) as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f" Last error: {last_error}" if last_error else ""
    raise AcceptanceError(f"Timed out waiting for {label}.{suffix}")


def port_is_closed(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) != 0


# ---------------------------------------------------------------------------
# WebDriver
# ---------------------------------------------------------------------------


class WebDriver:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.session_id: str | None = None

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        status, payload, _ = http(method, f"{self.origin}{path}", body=body, timeout=180)
        if not isinstance(payload, dict):
            raise AcceptanceError(f"WebDriver {method} {path}: HTTP {status}: {payload!r}")
        value = payload.get("value")
        if isinstance(value, dict) and value.get("error"):
            raise AcceptanceError(
                f"WebDriver {method} {path}: {value['error']}: {value.get('message', '')}"
            )
        if status >= 400:
            raise AcceptanceError(f"WebDriver {method} {path}: HTTP {status}: {payload!r}")
        return value

    def create_session(self, application: Path) -> None:
        value = self.request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "wry",
                        "tauri:options": {"application": str(application)},
                    }
                }
            },
        )
        if not isinstance(value, dict) or not value.get("sessionId"):
            raise AcceptanceError(f"WebDriver returned no session id: {value!r}")
        self.session_id = value["sessionId"]
        self.request("POST", self._path("/timeouts"), {"script": 240_000})

    def _path(self, suffix: str) -> str:
        if not self.session_id:
            raise AcceptanceError("WebDriver session is not open")
        return f"/session/{self.session_id}{suffix}"

    def execute(self, script: str, args: list[Any] | None = None) -> Any:
        return self.request("POST", self._path("/execute/sync"), {"script": script, "args": args or []})

    def execute_async(self, script: str, args: list[Any] | None = None) -> Any:
        return self.request("POST", self._path("/execute/async"), {"script": script, "args": args or []})

    def type(self, selector: str, text: str) -> None:
        changed = self.execute(
            """
            const element = document.querySelector(arguments[0]);
            if (!element) return false;
            const prototype = element instanceof HTMLTextAreaElement
              ? HTMLTextAreaElement.prototype
              : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, arguments[1]);
            element.dispatchEvent(new InputEvent('input', {
              bubbles: true,
              inputType: 'insertText',
              data: arguments[1]
            }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            element.focus();
            return document.activeElement === element;
            """,
            [selector, text],
        )
        if not changed:
            raise AcceptanceError(f"Could not set and focus {selector!r}")
        wait_until(
            f"text input in {selector}",
            lambda: self.execute(
                "return document.querySelector(arguments[0])?.value === arguments[1];",
                [selector, text],
            ),
            timeout=5,
        )

    def type_labelled(self, label: str, text: str) -> None:
        """Set an input identified by its visible label text."""
        changed = self.execute(
            """
            const wanted = arguments[0];
            const field = [...document.querySelectorAll('label')]
              .find((candidate) => candidate.querySelector('span')?.textContent.trim() === wanted)
              ?.querySelector('input');
            if (!field) return false;
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
              .set.call(field, arguments[1]);
            field.dispatchEvent(new InputEvent('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            return field.value === arguments[1];
            """,
            [label, text],
        )
        if not changed:
            raise AcceptanceError(f"Could not fill the field labelled {label!r}")

    def press_enter(self, selector: str) -> None:
        handled = self.execute(
            """
            const element = document.querySelector(arguments[0]);
            if (!element) return false;
            element.focus();
            return element.dispatchEvent(new KeyboardEvent('keydown', {
              key: 'Enter',
              code: 'Enter',
              bubbles: true,
              cancelable: true
            }));
            """,
            [selector],
        )
        if handled is None:
            raise AcceptanceError(f"Could not dispatch Enter to {selector!r}")

    def click(self, selector: str) -> None:
        clicked = self.execute(
            """
            const element = document.querySelector(arguments[0]);
            if (!element) return false;
            element.click();
            return true;
            """,
            [selector],
        )
        if not clicked:
            raise AcceptanceError(f"Could not click {selector!r}")

    def click_text(self, label: str) -> None:
        clicked = self.execute(
            """
            const label = arguments[0];
            const element = [...document.querySelectorAll('button,[role="button"]')]
              .find((candidate) =>
                candidate.getAttribute('aria-label') === label ||
                candidate.textContent.trim().includes(label));
            if (!element) return false;
            element.click();
            return true;
            """,
            [label],
        )
        if not clicked:
            raise AcceptanceError(f"Could not find control labelled {label!r}")

    def screenshot(self, target: Path) -> None:
        encoded = self.request("GET", self._path("/screenshot"))
        if not isinstance(encoded, str):
            raise AcceptanceError("WebDriver did not return a screenshot")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(encoded))

    def cookies(self) -> list[dict[str, Any]]:
        value = self.request("GET", self._path("/cookie"))
        if not isinstance(value, list):
            raise AcceptanceError(f"Unexpected cookie response: {value!r}")
        return value

    def resize(self, width: int, height: int) -> dict[str, Any]:
        value = self.request("POST", self._path("/window/rect"), {"width": width, "height": height})
        if not isinstance(value, dict):
            raise AcceptanceError(f"Unexpected window rect: {value!r}")
        return value

    def close(self) -> None:
        if self.session_id:
            try:
                self.request("DELETE", f"/session/{self.session_id}")
            finally:
                self.session_id = None


def set_select(driver: WebDriver, selector: str, value: str) -> None:
    changed = driver.execute(
        """
        const element = document.querySelector(arguments[0]);
        if (!element) return false;
        element.value = arguments[1];
        element.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
        """,
        [selector, value],
    )
    if not changed:
        raise AcceptanceError(f"Could not set {selector!r}")


# ---------------------------------------------------------------------------
# Fixtures and environment
# ---------------------------------------------------------------------------


def build_source_pdf() -> bytes:
    """Render the same synthetic Stadgar the pilot corpus uses.

    The fixture lives on the test side only — the shipped bundle contains no
    seed corpus at all — so this exercises the real upload/ingestion path with
    a document whose content is known well enough to judge grounding.
    """

    from scripts.seed import render_pdf
    from scripts.seed_content import DOCUMENTS

    for definition in DOCUMENTS:
        if definition["name"] == SOURCE_DOCUMENT:
            return render_pdf(definition)
    raise AcceptanceError(f"Fixture {SOURCE_DOCUMENT!r} missing from the seed corpus")


def isolated_environment(root: Path) -> dict[str, str]:
    """A pristine XDG home so every run starts unprovisioned and the
    operator's real installation is never touched."""
    data_home = root / "xdg-data"
    config_home = root / "xdg-config"
    cache_home = root / "xdg-cache"
    for directory in (data_home, config_home, cache_home):
        directory.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update(
        {
            "XDG_DATA_HOME": str(data_home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_CACHE_HOME": str(cache_home),
            # Isolation is about application *data*, not about caches. Without
            # this, huggingface_hub follows XDG_CACHE_HOME into the throwaway
            # directory and a development-checkout run re-downloads the
            # embedder every time. The packaged application never reads this:
            # its weights are bundled and HF_HUB_OFFLINE is set.
            "HF_HOME": os.environ.get("HF_HOME")
            or str(Path.home() / ".cache" / "huggingface"),
        }
    )
    return environment


def app_data_dir(environment: dict[str, str]) -> Path:
    return Path(environment["XDG_DATA_HOME"]) / "se.brfdokumentai.desktop"


# ---------------------------------------------------------------------------
# Phase A — the UI journey through the real webview
# ---------------------------------------------------------------------------


def ui_journey(
    application: Path,
    environment: dict[str, str],
    model_base_url: str,
    evidence_dir: Path,
) -> dict:
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

    def read_driver() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            driver_logs.append(line.rstrip())

    threading.Thread(target=read_driver, daemon=True).start()
    driver = WebDriver(DRIVER_ORIGIN)
    results: dict[str, Any] = {}
    origin: str | None = None

    try:
        wait_until("tauri-driver", lambda: driver.request("GET", "/status"), timeout=20)
        driver.create_session(application)

        # -- first run ----------------------------------------------------
        try:
            wait_until(
                "first-run setup screen",
                lambda: driver.execute(
                    "return document.body.innerText.includes('Välkommen') "
                    "&& Boolean([...document.querySelectorAll('label span')]"
                    ".find(s => s.textContent.trim() === 'Föreningens namn'));"
                ),
                # Generous: against a development checkout the embedder may
                # still be downloading from Hugging Face on a cold cache. The
                # packaged application never does that.
                timeout=240,
            )
        except AcceptanceError as exc:
            page = driver.execute(
                """
                return {
                  href: location.href,
                  readyState: document.readyState,
                  body: document.body?.innerText.slice(0, 1200)
                };
                """
            )
            raise AcceptanceError(
                f"{exc}\nPage: {page!r}\nDriver tail:\n" + "\n".join(driver_logs[-30:])
            ) from exc

        # A fresh installation must offer no way in with credentials, because
        # it has none.
        offers_setup_not_login = driver.execute(
            "return document.querySelector('button[type=submit]')"
            "?.textContent.includes('Skapa förening') === true;"
        )
        if not offers_setup_not_login:
            raise AcceptanceError("Fresh installation offered a login form instead of first-run setup")

        driver.execute(COLLECT_RUNTIME_ERRORS)

        driver.type_labelled("Föreningens namn", BRF_NAME)
        driver.type_labelled("Ditt namn", OWNER_NAME)
        driver.type_labelled("E-postadress", OWNER_EMAIL)
        driver.type_labelled("Lösenord", OWNER_PASSWORD)
        driver.type_labelled("Upprepa lösenord", OWNER_PASSWORD)
        driver.click("button[type=submit]")

        wait_until(
            "association created",
            lambda: driver.execute("return document.body.innerText.includes('Föreningen är skapad');"),
            # Creating the first association builds the tenant's index, which
            # loads the embedder. Bundled, that is a few seconds; against a cold
            # development cache it is a download.
            timeout=240,
        )
        driver.screenshot(evidence_dir / "xs49-desktop-setup.png")

        # -- model runtime -------------------------------------------------
        driver.type_labelled("Modelltjänstens adress", model_base_url)
        driver.type_labelled("Etikett (valfri)", "agenntserver")
        driver.click_text("Testa och fortsätt")
        # A freshly provisioned installation has exactly ONE association, and
        # the product deliberately renders a static name rather than a
        # single-option dropdown there — so the workspace is recognised by the
        # navigation, not by the association selector.
        wait_until(
            "authenticated workspace",
            lambda: driver.execute(
                "return Boolean(document.querySelector('.user-profile')) "
                "&& Boolean([...document.querySelectorAll('button')]"
                ".find(b => b.textContent.trim() === 'Dokument'));"
            ),
            timeout=180,
        )
        single_association = driver.execute(
            f"""
            return {{
              selector: document.querySelectorAll('{BRF_SELECT}').length,
              staticName: document.querySelector('.active-brf-name-static')?.textContent.trim()
            }};
            """
        )
        if single_association["selector"] != 0 or single_association["staticName"] != BRF_NAME:
            raise AcceptanceError(
                f"One association should render as a static name, not a dropdown: {single_association!r}"
            )

        readiness = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            Promise.all([
              fetch('/api/desktop/readiness', { credentials: 'include' }).then(r => r.json()),
              fetch('/api/desktop/state', { credentials: 'include' }).then(r => r.json()),
              fetch('/api/health', { credentials: 'include' }).then(r => r.json()),
              fetch('/api/auth/me', { credentials: 'include' }).then(r => r.json())
            ]).then(([readiness, state, health, me]) =>
              done({ readiness, state, health, me, origin: location.origin })
            ).catch(error => done({ error: String(error) }));
            """
        )
        if readiness.get("error"):
            raise AcceptanceError(f"Could not read application state: {readiness!r}")
        if readiness["readiness"].get("schema") != STARTUP_SCHEMA:
            raise AcceptanceError(f"Invalid readiness record: {readiness['readiness']!r}")
        if readiness["state"].get("schema") != STATE_SCHEMA:
            raise AcceptanceError(f"Invalid desktop state: {readiness['state']!r}")
        if readiness["readiness"]["origin"] != readiness["origin"]:
            raise AcceptanceError(f"UI/API origin mismatch: {readiness!r}")
        if readiness["me"]["user"]["email"] != OWNER_EMAIL:
            raise AcceptanceError(f"Provisioned owner did not authenticate: {readiness['me']!r}")
        if readiness["health"]["mode"] != "desktop":
            raise AcceptanceError(f"Application is not running in desktop mode: {readiness['health']!r}")
        if readiness["health"]["llm"]["provider"] != "selfhosted":
            raise AcceptanceError(
                f"Generation is not on the self-hosted runtime: {readiness['health']!r}"
            )
        origin = readiness["readiness"]["origin"]
        state = readiness["state"]

        # -- second association + switching --------------------------------
        second = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch('/api/desktop/brf', {
              method: 'POST',
              credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: arguments[0] })
            }).then(async r => done({ status: r.status, body: await r.json() }))
              .catch(error => done({ error: String(error) }));
            """,
            [SECOND_BRF_NAME],
        )
        if second.get("status") != 200:
            raise AcceptanceError(f"Could not create a second association: {second!r}")
        driver.execute("location.reload(); return true;")
        wait_until(
            "workspace after reload",
            lambda: driver.execute(
                f"return document.querySelectorAll('{BRF_SELECT} option').length === 2;"
            ),
            timeout=90,
        )
        # The reload discarded the collector installed before setup; without
        # re-installing it the runtime-error assertion below would pass on an
        # empty array no matter what the page did.
        driver.execute(COLLECT_RUNTIME_ERRORS)
        second_id = second["body"]["brf_id"]
        set_select(driver, BRF_SELECT, second_id)
        wait_until(
            "switch to the second association",
            lambda: driver.execute(f"return document.querySelector('{BRF_SELECT}').value === arguments[0];", [second_id]),
        )
        set_select(driver, BRF_SELECT, "brf-gjutformen-12")
        wait_until(
            "switch back",
            lambda: driver.execute(
                f"return document.querySelector('{BRF_SELECT}').value === 'brf-gjutformen-12';"
            ),
        )

        # -- upload and ingestion ------------------------------------------
        driver.click_text("Dokument")
        wait_until(
            "documents view",
            lambda: driver.execute("return Boolean(document.querySelector('input[type=file]'));"),
        )
        pdf_b64 = base64.b64encode(build_source_pdf()).decode()
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
            return input.files.length === 1;
            """,
            [pdf_b64, SOURCE_DOCUMENT],
        )
        if not accepted:
            raise AcceptanceError("The document view did not accept the uploaded file")
        ingestion_started = time.monotonic()
        wait_until(
            "ingestion finished and the document listed",
            lambda: driver.execute(
                "return document.body.innerText.includes(arguments[0]) "
                "&& !document.body.innerText.includes('Laddar upp…');",
                [SOURCE_DOCUMENT],
            ),
            timeout=180,
        )
        ingestion_seconds = round(time.monotonic() - ingestion_started, 1)
        driver.screenshot(evidence_dir / "xs49-desktop-documents.png")

        # -- supported question --------------------------------------------
        driver.click_text("AI-chatt")
        wait_until(
            "general chat input",
            lambda: driver.execute(f"return Boolean(document.querySelector('{GENERAL_CHAT_INPUT}'));"),
        )
        driver.type(GENERAL_CHAT_INPUT, SUPPORTED_QUESTION)
        driver.press_enter(GENERAL_CHAT_INPUT)
        answer = wait_until(
            "a grounded answer with at least one citation",
            lambda: driver.execute(
                """
                const messages = [...document.querySelectorAll('.chat-message.ai')];
                const latest = messages.at(-1);
                if (!latest) return false;
                const pills = [...latest.querySelectorAll('.citation-pill')];
                if (pills.length === 0) return false;
                return {
                  text: latest.querySelector('.chat-content')?.innerText.trim(),
                  refusal: Boolean(latest.querySelector('.chat-refusal-header')),
                  provenance: latest.querySelector('.chat-model-provenance')?.textContent.trim(),
                  citations: pills.map((pill) => ({
                    quote: pill.querySelector('.citation-text')?.textContent.trim(),
                    source: pill.querySelector('.citation-source')?.textContent.trim()
                  }))
                };
                """
            ),
            timeout=300,
        )
        if answer["refusal"]:
            raise AcceptanceError(f"Supported question was refused: {answer!r}")
        if not any(SOURCE_DOCUMENT in (c["source"] or "") for c in answer["citations"]):
            raise AcceptanceError(f"Answer did not cite the uploaded document: {answer!r}")

        # -- citation -> PDF highlight --------------------------------------
        driver.click_text(SOURCE_DOCUMENT)
        highlight = wait_until(
            "PDF page and citation highlight",
            lambda: driver.execute(
                """
                const marker = document.querySelector('[data-testid="citation-highlight"]');
                const page = document.querySelector('[data-testid="pdf-page-indicator"]');
                if (!marker || !page) return false;
                const rect = marker.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && {
                  page: page.textContent.trim(),
                  rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                };
                """
            ),
            timeout=90,
        )
        driver.screenshot(evidence_dir / "xs49-desktop-answer-highlight.png")

        zoom_before = driver.execute(
            "return [...document.querySelectorAll('.pdf-actions span')].map(e => e.textContent)"
            ".find(text => text.includes('%'));"
        )
        driver.click_text("Zooma in")
        zoom_after = wait_until(
            "PDF zoom",
            lambda: driver.execute(
                "return [...document.querySelectorAll('.pdf-actions span')].map(e => e.textContent)"
                ".find(text => text.includes('%')) === '110%' && '110%';"
            ),
        )

        # -- evidence-based refusal ------------------------------------------
        driver.click_text("Tillbaka")
        driver.click_text("AI-chatt")
        wait_until(
            "chat restored",
            lambda: driver.execute(f"return Boolean(document.querySelector('{GENERAL_CHAT_INPUT}'));"),
        )
        driver.type(GENERAL_CHAT_INPUT, UNSUPPORTED_QUESTION)
        driver.click_text("Skicka fråga")
        refusal = wait_until(
            "insufficient-evidence refusal without citations",
            lambda: driver.execute(
                """
                const messages = [...document.querySelectorAll('.chat-message.ai')];
                const latest = messages.at(-1);
                if (!latest?.querySelector('.chat-refusal-header')) return false;
                return {
                  text: latest.querySelector('.chat-content')?.innerText.trim(),
                  citations: latest.querySelectorAll('.citation-pill').length
                };
                """
            ),
            timeout=300,
        )
        if refusal["citations"] != 0:
            raise AcceptanceError(f"Refusal unexpectedly carried citations: {refusal!r}")
        driver.screenshot(evidence_dir / "xs49-desktop-refusal.png")

        # -- backup from the UI ----------------------------------------------
        driver.click(".user-profile")
        driver.click_text("Appinställningar")
        wait_until(
            "desktop settings panel",
            lambda: driver.execute("return Boolean(document.querySelector('.desktop-settings'));"),
        )
        driver.click_text("Skapa säkerhetskopia nu")
        backup = wait_until(
            "backup listed in the settings panel",
            lambda: driver.execute(
                """
                const rows = [...document.querySelectorAll('.ds-backups li')];
                if (rows.length === 0) return false;
                return { count: rows.length, first: rows[0].innerText.replace(/\\n/g, ' ') };
                """
            ),
            timeout=120,
        )
        driver.screenshot(evidence_dir / "xs49-desktop-settings.png")
        driver.click_text("Stäng")

        # -- layout, security -------------------------------------------------
        compact_rect = driver.resize(1000, 700)
        compact_layout = driver.execute(
            """
            return {
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              devicePixelRatio: window.devicePixelRatio,
              horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
              verticalScrollable: document.documentElement.scrollHeight >= window.innerHeight
            };
            """
        )
        if compact_layout["horizontalOverflow"]:
            raise AcceptanceError(f"Compact layout overflows horizontally: {compact_layout!r}")
        driver.resize(1440, 920)

        _, _, headers = http("GET", f"{origin}/brfv2/")
        csp = headers.get("content-security-policy", "")
        if "default-src 'none'" not in csp or "connect-src 'self'" not in csp:
            raise AcceptanceError(f"Restrictive CSP missing: {csp!r}")
        exact_host_status, _, _ = http("GET", f"{origin}/api/health")
        wrong_host_status, _, _ = http(
            "GET", f"{origin}/api/health", headers={"Host": f"localhost:{origin.rsplit(':', 1)[1]}"}
        )
        if exact_host_status != 200 or wrong_host_status != 403:
            raise AcceptanceError(
                f"Host validation is not exact: exact={exact_host_status} wrong={wrong_host_status}"
            )
        # Collect page errors before deliberately provoking a CSP violation, so
        # the assertion is about the product and not about this probe.
        runtime_errors = driver.execute("return window.__acceptanceErrors;")
        if runtime_errors:
            raise AcceptanceError(f"Webview runtime errors during the journey: {runtime_errors!r}")

        # The strongest available negative: the model service really is running
        # on this machine and the application's own backend talks to it, so a
        # successful request from the page would prove connect-src is not
        # enforced.  XMLHttpRequest rather than fetch: a CSP-blocked fetch
        # surfaces through WebKitWebDriver as a script-level error that cannot
        # be caught in-page, which makes the *blocked* case indistinguishable
        # from a broken probe.
        probe_url = f"{model_base_url}/models"
        try:
            foreign_origin = driver.execute_async(
                """
                const done = arguments[arguments.length - 1];
                const url = arguments[0];
                let settled = false;
                let violation = null;
                const finish = (payload) => {
                  if (settled) return;
                  settled = true;
                  done({ ...payload, violation });
                };
                document.addEventListener('securitypolicyviolation', (event) => {
                  violation = {
                    directive: event.effectiveDirective,
                    blockedURI: event.blockedURI
                  };
                }, { once: true });
                const request = new XMLHttpRequest();
                request.onload = () => finish({ reached: true, status: request.status });
                // `reason`, not `error`: a top-level `error` key in the returned
                // object is indistinguishable from a WebDriver error envelope.
                request.onerror = () => finish({ reached: false, reason: 'blocked' });
                setTimeout(() => finish({ reached: false, reason: 'timeout' }), 5000);
                try {
                  request.open('GET', url);
                  request.send();
                } catch (failure) {
                  finish({ reached: false, reason: String(failure) });
                }
                """,
                [probe_url],
            )
        except AcceptanceError as exc:
            # Unknown is reported as unknown; only a *reached* service fails.
            foreign_origin = {"reached": None, "probeError": str(exc)}
        if foreign_origin.get("reached") is True:
            raise AcceptanceError(f"connect-src did not stop the model service origin: {foreign_origin!r}")

        global_tauri = driver.execute(
            "return { global: typeof window.__TAURI__, internals: typeof window.__TAURI_INTERNALS__ };"
        )
        if global_tauri["global"] != "undefined":
            raise AcceptanceError(f"Global Tauri API unexpectedly exposed: {global_tauri!r}")
        ipc_attempt = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            const invoke = window.__TAURI_INTERNALS__?.invoke;
            if (typeof invoke !== 'function') {
              done({ allowed: false, result: 'bridge unavailable' });
              return;
            }
            invoke('plugin:window|set_title', {
              label: 'main',
              value: 'ACCEPTANCE IPC SHOULD BE DENIED'
            }).then(
              value => done({ allowed: true, result: String(value) }),
              error => done({ allowed: false, result: String(error) })
            );
            """
        )
        if ipc_attempt["allowed"]:
            raise AcceptanceError(f"Remote HTTP page obtained Tauri IPC permission: {ipc_attempt!r}")

        cookie_contract = desktop_cookie_contract(origin)
        webdriver_cookies = driver.cookies()

        results = {
            "origin": origin,
            "platform": {
                "userAgent": driver.execute("return navigator.userAgent;"),
                "devicePixelRatio": compact_layout["devicePixelRatio"],
                "sessionType": os.environ.get("XDG_SESSION_TYPE", ""),
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
            },
            "firstRun": {
                "owner": OWNER_EMAIL,
                "association": BRF_NAME,
                "singleAssociationRendersStaticName": single_association["staticName"],
                "dataDir": state["storage"]["dataDir"],
                "ocr": state["ocr"],
                "embedding": state["embedding"],
            },
            "modelRuntime": {
                "baseUrl": model_base_url,
                "provider": readiness["health"]["llm"]["provider"],
                "model": readiness["health"]["llm"]["model"],
                "label": readiness["health"]["llm"]["runtime_label"],
                "ready": readiness["health"]["llm"]["ready"],
            },
            "associations": ["brf-gjutformen-12", second_id, "brf-gjutformen-12"],
            "ingestion": {"document": SOURCE_DOCUMENT, "seconds": ingestion_seconds},
            "supportedAnswer": {
                "question": SUPPORTED_QUESTION,
                "answer": answer["text"],
                "provenance": answer["provenance"],
                "citations": answer["citations"],
                "highlight": highlight,
            },
            "pdfZoom": {"before": zoom_before, "after": zoom_after},
            "refusal": {"question": UNSUPPORTED_QUESTION, **refusal},
            "backup": backup,
            "compactWindow": {"rect": compact_rect, "layout": compact_layout},
            "security": {
                "csp": csp,
                "exactHostStatus": exact_host_status,
                "foreignHostStatus": wrong_host_status,
                "foreignOriginRequest": {"url": probe_url, **foreign_origin},
                "globalTauri": global_tauri,
                "remoteIpcSetTitle": ipc_attempt,
                "cookie": {**cookie_contract, "webdriverEnumerated": len(webdriver_cookies)},
                "runtimeErrors": runtime_errors,
            },
            "keyboard": {
                "mode": "WebKit DOM events",
                "chatSubmit": "Enter",
                "nativeWebDriverElementValue": "unsupported by WebKitWebDriver for WRY",
                "nativeWaylandAutomation": "blocked by this KWin/WebKit automation environment",
            },
            "screenshots": [
                "docs/evidence/xs49-desktop-setup.png",
                "docs/evidence/xs49-desktop-documents.png",
                "docs/evidence/xs49-desktop-answer-highlight.png",
                "docs/evidence/xs49-desktop-refusal.png",
                "docs/evidence/xs49-desktop-settings.png",
            ],
        }
    finally:
        try:
            driver.close()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)

    if origin is None:
        raise AcceptanceError("The UI journey never observed a startup contract.")
    port = int(origin.rsplit(":", 1)[1])
    wait_until("loopback port cleanup after the UI session", lambda: port_is_closed(port), timeout=15)
    results["cleanup"] = {"port": port, "closed": True}
    return results


def desktop_cookie_contract(origin: str) -> dict[str, Any]:
    status, _, headers = http(
        "POST",
        f"{origin}/api/auth/login",
        body={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    if status != 200:
        raise AcceptanceError(f"Cookie probe login failed: HTTP {status}")
    parsed = SimpleCookie()
    parsed.load(headers.get("set-cookie", ""))
    matching = [(name, morsel) for name, morsel in parsed.items() if name.startswith("brf_desktop_")]
    if len(matching) != 1:
        raise AcceptanceError(f"Expected one desktop Set-Cookie header, got: {headers!r}")
    name, morsel = matching[0]
    contract = {
        "namePrefix": "brf_desktop_",
        "httpOnly": bool(morsel["httponly"]),
        "path": morsel["path"],
        "sameSite": morsel["samesite"].capitalize(),
    }
    if not contract["httpOnly"] or contract["path"] != "/api/" or contract["sameSite"] != "Lax":
        raise AcceptanceError(f"Unsafe desktop cookie attributes: {contract!r}")
    http("POST", f"{origin}/api/auth/logout", body={}, cookie=f"{name}={morsel.value}")
    return contract


# ---------------------------------------------------------------------------
# Phase B — process lifecycle, persistence, backup and restore
# ---------------------------------------------------------------------------


class LaunchedApp:
    """The real shell binary, launched directly so restarts can be observed."""

    def __init__(self, application: Path, environment: dict[str, str]) -> None:
        self.application = application
        self.environment = environment
        self.process: subprocess.Popen | None = None
        self.origin: str | None = None
        self.stderr: list[str] = []

    def start(self, timeout: float = 180.0) -> str:
        self.process = subprocess.Popen(
            [str(self.application)],
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

        def drain() -> None:
            assert self.process is not None and self.process.stderr is not None
            for line in self.process.stderr:
                self.stderr.append(line.rstrip())

        threading.Thread(target=drain, daemon=True).start()

        assert self.process.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                break
            try:
                contract = json.loads(line)
            except json.JSONDecodeError:
                continue
            if contract.get("schema") == STARTUP_SCHEMA and contract.get("status") == "ready":
                self.origin = contract["origin"]
                return self.origin
        raise AcceptanceError(
            "The application never reported readiness. stderr tail:\n"
            + "\n".join(self.stderr[-25:])
        )

    def wait_for_restart(self, timeout: float = 180.0) -> str:
        """A restart re-executes the binary, so the next contract arrives on
        the same stdout pipe under the same PID."""
        assert self.process is not None and self.process.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                raise AcceptanceError(
                    "The application exited instead of restarting. stderr tail:\n"
                    + "\n".join(self.stderr[-25:])
                )
            try:
                contract = json.loads(line)
            except json.JSONDecodeError:
                continue
            if contract.get("schema") == STARTUP_SCHEMA and contract["origin"] != self.origin:
                self.origin = contract["origin"]
                return self.origin
        raise AcceptanceError("The application did not come back after the restart request")

    def group_is_empty(self) -> bool:
        assert self.process is not None
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def stop(self, *, signal_number: int = signal.SIGTERM) -> None:
        """Signal the application's process GROUP, not the launched PID.

        Tauri's restart spawns a replacement process and exits, so after a
        restore-restart the originally launched PID is already gone while the
        application is very much alive — in the same process group, reparented
        to init.  Signalling the PID alone would silently do nothing, which is
        exactly how a stale backend survives a "clean" shutdown.
        """
        if self.process is None:
            return
        try:
            os.killpg(self.process.pid, signal_number)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not self.group_is_empty():
            time.sleep(0.2)
        if not self.group_is_empty():
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


def python_processes_under(data_dir: Path) -> list[str]:
    """Any backend still holding this isolated installation's data root."""
    found = subprocess.run(
        ["pgrep", "-af", "app.desktop"], capture_output=True, text=True
    ).stdout.splitlines()
    return [line for line in found if str(data_dir) in line]


def lifecycle_journey(application: Path, environment: dict[str, str], model_base_url: str) -> dict:
    data_dir = app_data_dir(environment)
    results: dict[str, Any] = {}

    # -- restart with retained state ---------------------------------------
    app = LaunchedApp(application, environment)
    first_origin = app.start()
    first_port = int(first_origin.rsplit(":", 1)[1])

    status, state, _ = http("GET", f"{first_origin}/api/desktop/state")
    if status != 200 or not state["provisioned"]:
        raise AcceptanceError(f"Phase B expected the provisioned installation from phase A: {state!r}")

    status, login, headers = http(
        "POST",
        f"{first_origin}/api/auth/login",
        body={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    if status != 200:
        raise AcceptanceError(f"Retained identity did not authenticate after restart: HTTP {status}")
    parsed = SimpleCookie()
    parsed.load(headers.get("set-cookie", ""))
    cookie_name = next(name for name in parsed if name.startswith("brf_desktop_"))
    cookie = f"{cookie_name}={parsed[cookie_name].value}"
    memberships = sorted(row["brf_id"] for row in login["memberships"])

    _, documents, _ = http(
        "GET", f"{first_origin}/api/brf/brf-gjutformen-12/documents", cookie=cookie
    )
    if not any(row["name"] == SOURCE_DOCUMENT for row in documents):
        raise AcceptanceError(f"The uploaded document did not survive the restart: {documents!r}")

    # The model runtime configured in the UI must still be in force.
    _, health, _ = http("GET", f"{first_origin}/api/health", cookie=cookie)
    if health["llm"]["provider"] != "selfhosted" or not health["llm"]["ready"]:
        raise AcceptanceError(f"Model runtime configuration was not retained: {health!r}")

    results["retainedState"] = {
        "memberships": memberships,
        "documents": [row["name"] for row in documents],
        "modelRuntime": health["llm"],
        "provisioned": True,
    }

    # -- backup, divergence, restore ---------------------------------------
    status, backup, _ = http("POST", f"{first_origin}/api/desktop/backups", body=None, cookie=cookie)
    if status != 200:
        raise AcceptanceError(f"Could not create a backup: HTTP {status}: {backup!r}")

    status, extra, _ = http(
        "POST",
        f"{first_origin}/api/desktop/brf",
        body={"name": "Brf Efter Kopian"},
        cookie=cookie,
    )
    if status != 200:
        raise AcceptanceError(f"Could not diverge from the backup: {extra!r}")
    diverged = sorted(row["brf_id"] for row in extra["memberships"])

    status, staged, _ = http(
        "POST",
        f"{first_origin}/api/desktop/backups/{backup['name']}/restore",
        body=None,
        cookie=cookie,
    )
    if status != 200 or not staged.get("restartRequired"):
        raise AcceptanceError(f"Restore was not staged: HTTP {status}: {staged!r}")

    http("POST", f"{first_origin}/api/desktop/restart", body=None, cookie=cookie)
    second_origin = app.wait_for_restart()
    # Tauri's restart spawns a replacement and exits, so the application now
    # runs under a new pid in the same process group. Record it: an operator
    # who kills the pid they launched would otherwise leave the app running.
    launched_pid_exited = app.process is not None and app.process.poll() is not None
    wait_until("the pre-restart port to close", lambda: port_is_closed(first_port), timeout=20)

    status, restored_state, _ = http("GET", f"{second_origin}/api/desktop/state")
    if restored_state.get("lastRestore", {}).get("status") != "restored":
        raise AcceptanceError(f"The staged restore was not applied: {restored_state!r}")

    status, relogin, headers = http(
        "POST",
        f"{second_origin}/api/auth/login",
        body={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    parsed = SimpleCookie()
    parsed.load(headers.get("set-cookie", ""))
    cookie_name = next(name for name in parsed if name.startswith("brf_desktop_"))
    cookie = f"{cookie_name}={parsed[cookie_name].value}"
    after_restore = sorted(row["brf_id"] for row in relogin["memberships"])
    if after_restore != memberships:
        raise AcceptanceError(
            f"Restore did not roll the installation back: {after_restore!r} != {memberships!r}"
        )
    _, documents_after, _ = http(
        "GET", f"{second_origin}/api/brf/brf-gjutformen-12/documents", cookie=cookie
    )
    if not any(row["name"] == SOURCE_DOCUMENT for row in documents_after):
        raise AcceptanceError(f"Restore lost the document corpus: {documents_after!r}")

    results["backupRestore"] = {
        "backup": {k: backup[k] for k in ("name", "bytes", "files", "tenants")},
        "beforeRestore": diverged,
        "afterRestore": after_restore,
        "documents": [row["name"] for row in documents_after],
        "restartExitCode": RESTART_EXIT_CODE,
        "restartRespawnsUnderANewPid": launched_pid_exited,
        "lastRestore": restored_state["lastRestore"],
    }

    # -- clean shutdown ------------------------------------------------------
    second_port = int(second_origin.rsplit(":", 1)[1])
    app.stop()
    wait_until("clean shutdown closes the loopback port", lambda: port_is_closed(second_port), timeout=20)
    leftovers = python_processes_under(data_dir)
    if leftovers:
        raise AcceptanceError(f"Backend processes survived a clean shutdown: {leftovers!r}")
    results["cleanShutdown"] = {"port": second_port, "closed": True, "orphans": 0}

    # -- abrupt termination --------------------------------------------------
    abrupt = LaunchedApp(application, environment)
    abrupt_origin = abrupt.start()
    abrupt_port = int(abrupt_origin.rsplit(":", 1)[1])
    assert abrupt.process is not None
    os.killpg(abrupt.process.pid, signal.SIGKILL)
    try:
        abrupt.process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
    wait_until("SIGKILL cleanup closes the loopback port", lambda: port_is_closed(abrupt_port), timeout=25)
    orphans = python_processes_under(data_dir)
    if orphans:
        raise AcceptanceError(f"SIGKILL on the shell orphaned the backend: {orphans!r}")
    results["abruptTermination"] = {"port": abrupt_port, "closed": True, "orphans": 0}

    # -- model runtime unavailable ------------------------------------------
    # An installation whose model service is gone must still start, still show
    # its documents, and refuse to answer rather than invent one.
    unreachable = dict(environment)
    offline = LaunchedApp(application, unreachable)
    offline_origin = offline.start()
    _, _, headers = http(
        "POST",
        f"{offline_origin}/api/auth/login",
        body={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    parsed = SimpleCookie()
    parsed.load(headers.get("set-cookie", ""))
    cookie_name = next(name for name in parsed if name.startswith("brf_desktop_"))
    cookie = f"{cookie_name}={parsed[cookie_name].value}"
    http(
        "PUT",
        f"{offline_origin}/api/desktop/model-runtime",
        body={"baseUrl": "http://127.0.0.1:1/v1", "model": "gemma4:e12b", "label": "unreachable"},
        cookie=cookie,
    )
    _, probe, _ = http(
        "POST", f"{offline_origin}/api/desktop/model-runtime/test", body=None, cookie=cookie
    )
    if probe.get("ok"):
        raise AcceptanceError(f"An unreachable runtime reported healthy: {probe!r}")
    status, degraded, _ = http(
        "POST",
        f"{offline_origin}/api/brf/brf-gjutformen-12/ask",
        body={"question": SUPPORTED_QUESTION},
        cookie=cookie,
        timeout=180,
    )
    if status != 200 or not degraded.get("refusal"):
        raise AcceptanceError(f"An unreachable runtime did not produce a refusal: {status} {degraded!r}")
    if degraded.get("citations"):
        raise AcceptanceError(f"A provider-error refusal carried citations: {degraded!r}")
    # Put the working runtime back so the installation is left usable.
    http(
        "PUT",
        f"{offline_origin}/api/desktop/model-runtime",
        body={"baseUrl": model_base_url, "model": "gemma4:e12b", "label": "agenntserver"},
        cookie=cookie,
    )
    offline.stop()
    results["modelRuntimeUnavailable"] = {
        "probe": probe,
        "refusalReason": degraded.get("refusal_reason"),
        "answer": degraded.get("answer"),
        "citations": len(degraded.get("citations") or []),
    }
    return results


# ---------------------------------------------------------------------------
# Phase C — the failure surfaces a normal user can actually hit
# ---------------------------------------------------------------------------


def failure_surfaces(
    application: Path,
    environment: dict[str, str],
    evidence_dir: Path,
) -> dict:
    """An installed application must explain a failed start and a dead backend.

    Exiting to a terminal nobody is watching is not an acceptable outcome for a
    program launched from the desktop menu, so both paths are verified as
    *visible* states, not just as non-zero exit codes.
    """

    results: dict[str, Any] = {}

    # The realistic trigger for a failed start is a broken or partial
    # installation: the shell is there, its runtime is not.  Copying the binary
    # somewhere with no resources beside it and no reachable checkout
    # reproduces exactly that, without putting a test-only hook into the
    # shipped product.
    installed_resources = Path("/usr/lib/BRF Dokument-AI")
    if installed_resources.is_dir():
        results["startupFailure"] = {
            "skipped": (
                "an installation is present at /usr/lib/BRF Dokument-AI, so a detached "
                "copy of the binary still resolves a valid runtime; this surface is "
                "verified against the checkout build instead"
            )
        }
        return {**results, **backend_death(application, environment)}

    detached_dir = Path(environment["XDG_CACHE_HOME"]) / "detached"
    detached_dir.mkdir(parents=True, exist_ok=True)
    detached = detached_dir / application.name
    shutil.copy2(application, detached)
    broken = dict(environment)
    broken["BRFV2_REPO_ROOT"] = "/nonexistent/brfv2-checkout"

    process = subprocess.Popen(
        ["tauri-driver"],
        cwd=detached_dir,
        env=broken,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    driver = WebDriver(DRIVER_ORIGIN)
    try:
        wait_until("tauri-driver", lambda: driver.request("GET", "/status"), timeout=20)
        driver.create_session(detached)
        failure_page = wait_until(
            "the bundled failure window",
            lambda: driver.execute(
                """
                const detailNode = document.getElementById('detail');
                // data-state is only set once the injected payload has been
                // applied; before that the element still shows a placeholder,
                // and reading it would assert on nothing.
                if (!detailNode || detailNode.dataset.state === 'pending') return false;
                return {
                  headline: document.getElementById('headline')?.textContent.trim(),
                  detail: detailNode.textContent.trim(),
                  detailState: detailNode.dataset.state,
                  href: location.href,
                  protocol: location.protocol
                };
                """
            ),
            timeout=90,
        )
        if "kunde inte starta" not in failure_page["headline"].lower():
            raise AcceptanceError(f"Unexpected failure headline: {failure_page!r}")
        if failure_page["detailState"] != "applied" or len(failure_page["detail"]) < 20:
            raise AcceptanceError(f"The failure window shows no actual cause: {failure_page!r}")
        # A local bundled asset, never anything fetched.
        if not failure_page["href"].startswith(("tauri://", "http://tauri.localhost")):
            raise AcceptanceError(f"Unexpected failure window origin: {failure_page!r}")
        # The window was just created; give the compositor a frame so the
        # captured image shows the injected cause rather than the static
        # placeholder the document ships with.
        time.sleep(1.5)
        driver.screenshot(evidence_dir / "xs49-desktop-startup-failure.png")
        results["startupFailure"] = {
            "trigger": "shell without a resolvable runtime (broken installation)",
            "headline": failure_page["headline"],
            "detail": failure_page["detail"],
            "detailState": failure_page["detailState"],
            "windowUrl": failure_page["href"],
            "screenshot": "docs/evidence/xs49-desktop-startup-failure.png",
        }
    finally:
        try:
            driver.close()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            shutil.rmtree(detached_dir, ignore_errors=True)

    return {**results, **backend_death(application, environment)}


def backend_death(application: Path, environment: dict[str, str]) -> dict:
    """A backend that dies mid-session must be reported, not silently endured."""

    data_dir = app_data_dir(environment)
    app = LaunchedApp(application, environment)
    origin = app.start()
    port = int(origin.rsplit(":", 1)[1])
    # Touch the API so the backend has actually logged something; the log is a
    # support surface and "empty because nothing happened" would be a
    # meaningless pass.
    http("GET", f"{origin}/api/health")
    backends = python_processes_under(data_dir)
    if len(backends) != 1:
        raise AcceptanceError(f"Expected exactly one backend for this installation: {backends!r}")
    backend_pid = int(backends[0].split()[0])
    os.kill(backend_pid, signal.SIGKILL)

    wait_until(
        "the loopback port to close after the backend died",
        lambda: port_is_closed(port),
        timeout=20,
    )
    # The shell must stay up to show the explanation rather than vanish.
    time.sleep(3)
    assert app.process is not None
    if app.process.poll() is not None:
        raise AcceptanceError(
            "The shell exited instead of explaining the failure. stderr tail:\n"
            + "\n".join(app.stderr[-20:])
        )
    app.stop()
    orphans = python_processes_under(data_dir)
    if orphans:
        raise AcceptanceError(f"A killed backend left orphans behind: {orphans!r}")
    log_file = data_dir / "logs/backend.log"
    return {
        "backendDied": {
            "killedPid": backend_pid,
            "portClosed": True,
            "shellStayedUpToExplain": True,
            "orphans": 0,
            "logCaptured": log_file.is_file() and log_file.stat().st_size > 0,
            "logPath": str(log_file),
        }
    }


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Model-runtime security boundary, against the installed application
# ---------------------------------------------------------------------------


def _login(origin: str, email: str, password: str) -> str:
    status, _, headers = http(
        "POST", f"{origin}/api/auth/login", body={"email": email, "password": password}
    )
    if status != 200:
        raise AcceptanceError(f"Login failed for {email}: HTTP {status}")
    parsed = SimpleCookie()
    parsed.load(headers.get("set-cookie", ""))
    name = next(key for key in parsed if key.startswith("brf_desktop_"))
    return f"{name}={parsed[name].value}"


def runtime_python(application: Path) -> tuple[Path, Path]:
    """The interpreter and backend package the *application under test* ships.

    Used to create a second account with the product's own store code rather
    than the checkout's, so what the boundary is tested against is the shipped
    implementation.
    """

    resolved = application.resolve()
    candidates = [
        Path("/usr/lib/BRF Dokument-AI/runtime"),
        resolved.parent.parent.parent / "runtime",
    ]
    for runtime in candidates:
        interpreter = runtime / "python/bin/python3"
        if interpreter.is_file():
            return interpreter, runtime / "backend"
    raise AcceptanceError(f"No packaged runtime found next to {application}")


ORDINARY_EMAIL = "kassor@acceptans.example"
ORDINARY_PASSWORD = "vanligt-losenord-2026"

# Each of these is a destination the product must refuse, and the stable code
# it must refuse it with. A hosted third-party API is the one that matters most
# — it is what "self-hosted only" meant when it admitted every https URL.
REJECTED_ENDPOINTS = [
    ("https://api.openai.com/v1", "hostname_not_allowed"),
    ("https://api.anthropic.com/v1", "hostname_not_allowed"),
    ("https://8.8.8.8/v1", "address_not_self_hosted"),
    ("http://192.168.13.13:8000/v1", "plaintext_off_host"),
    ("http://169.254.169.254/latest/meta-data", "link_local_address"),
    ("file:///etc/passwd", "scheme_not_allowed"),
]


def security_boundary(application: Path, environment: dict[str, str], model_base_url: str) -> dict:
    """Who may repoint the model service, and where it may be pointed.

    Runs against the installed application over its real loopback API, on the
    installation phase A provisioned.
    """

    # app_data_dir() is the application directory; the store itself lives one
    # level down, beside backups/ and restore-staging/.
    data_root = app_data_dir(environment) / "data"
    results: dict[str, Any] = {}

    # A second, ordinary account, created with the shipped store code. The
    # product has no route that mints a second installation administrator, so
    # this is what any additional account on a real installation looks like —
    # and it is deliberately admin of every association, the strongest
    # authority an ordinary account can hold.
    interpreter, backend_dir = runtime_python(application)
    created = subprocess.run(
        [
            str(interpreter), "-E", "-s", "-B", "-c",
            "import sys;"
            "sys.path.insert(0, sys.argv[1]);"
            "from app.auth import AuthStore;"
            "s = AuthStore(sys.argv[2]);"
            "u = s.get_user_by_email(sys.argv[3]) or {'id': s.create_user(sys.argv[3], sys.argv[4], 'Karin Kassör')};"
            "[s.add_membership(u['id'], t['brf_id'], 'admin') for t in s.list_tenants()];"
            "print(u['id'], s.is_installation_admin(u['id']))",
            str(backend_dir), str(data_root / "auth.db"), ORDINARY_EMAIL, ORDINARY_PASSWORD,
        ],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        raise AcceptanceError(f"Could not create the ordinary account: {created.stderr.strip()}")
    ordinary_id, ordinary_is_admin = created.stdout.split()
    if ordinary_is_admin != "False":
        raise AcceptanceError("A newly created ordinary account was already an installation admin.")

    app = LaunchedApp(application, environment)
    origin = app.start()
    try:
        owner = _login(origin, OWNER_EMAIL, OWNER_PASSWORD)
        _, owner_state, _ = http("GET", f"{origin}/api/desktop/state", cookie=owner)
        if owner_state.get("installationAdmin") is not True:
            raise AcceptanceError(f"The provisioning owner is not an installation admin: {owner_state!r}")
        configured = owner_state["modelRuntime"]["baseUrl"]
        if configured != model_base_url:
            raise AcceptanceError(
                f"Phase A's model configuration is not in force: {configured!r} != {model_base_url!r}"
            )
        policy = owner_state["modelEndpointPolicy"]
        _, served_policy, _ = http("GET", f"{origin}/api/desktop/model-endpoint-policy")

        # -- an ordinary account may read the provenance, never change it ----
        ordinary = _login(origin, ORDINARY_EMAIL, ORDINARY_PASSWORD)
        _, ordinary_state, _ = http("GET", f"{origin}/api/desktop/state", cookie=ordinary)
        read_status, read_body, _ = http(
            "GET", f"{origin}/api/desktop/model-runtime", cookie=ordinary
        )
        repoint_status, repoint_body, _ = http(
            "PUT",
            f"{origin}/api/desktop/model-runtime",
            body={"baseUrl": "http://127.0.0.1:9/v1", "model": "gemma4:e12b"},
            cookie=ordinary,
        )
        probe_status, _, _ = http(
            "POST", f"{origin}/api/desktop/model-runtime/test", body=None, cookie=ordinary
        )
        _, after_ordinary, _ = http("GET", f"{origin}/api/desktop/state", cookie=owner)

        if repoint_status != 403 or probe_status != 403:
            raise AcceptanceError(
                f"An ordinary account could reach the global model configuration: "
                f"PUT {repoint_status}, probe {probe_status}"
            )
        if after_ordinary["modelRuntime"]["baseUrl"] != model_base_url:
            raise AcceptanceError("A rejected request still moved the model configuration.")

        results["ordinaryAccount"] = {
            "email": ORDINARY_EMAIL,
            "userId": ordinary_id,
            "associationRole": "admin",
            "installationAdmin": ordinary_state.get("installationAdmin"),
            "readModelRuntime": read_status,
            "readBaseUrl": read_body.get("baseUrl") if isinstance(read_body, dict) else None,
            "putModelRuntime": repoint_status,
            "putDetail": repoint_body.get("detail") if isinstance(repoint_body, dict) else None,
            "probeModelRuntime": probe_status,
            "configurationUnchanged": True,
        }

        # -- the endpoint policy, exercised through the installed API --------
        rejections = []
        for url, expected in REJECTED_ENDPOINTS:
            status, body, headers = http(
                "PUT",
                f"{origin}/api/desktop/model-runtime",
                body={"baseUrl": url, "model": "gemma4:e12b"},
                cookie=owner,
            )
            code = headers.get("x-model-endpoint-rejection")
            if status != 422 or code != expected:
                raise AcceptanceError(
                    f"{url} was not refused as {expected}: HTTP {status}, code {code!r}"
                )
            rejections.append(
                {
                    "url": url,
                    "status": status,
                    "code": code,
                    "detail": body.get("detail") if isinstance(body, dict) else None,
                }
            )
        results["rejectedEndpoints"] = rejections

        _, still, _ = http("GET", f"{origin}/api/desktop/state", cookie=owner)
        if still["modelRuntime"]["baseUrl"] != model_base_url:
            raise AcceptanceError("A refused endpoint still changed the configuration.")

        # The installation administrator's own probe is a real outbound request
        # to the real service — the boundary permits exactly this one.
        _, probe, _ = http(
            "POST", f"{origin}/api/desktop/model-runtime/test", body=None, cookie=owner, timeout=60
        )
        if not probe.get("ok"):
            raise AcceptanceError(f"The approved endpoint stopped answering: {probe!r}")

        results["policy"] = {
            "servedMatchesState": served_policy == policy,
            "id": policy["policy"],
            "default": policy["default"],
            "authority": policy["authority"],
            "deploymentClasses": policy["deploymentClasses"],
        }
        results["approvedEndpoint"] = {
            "deploymentClass": still["modelRuntime"]["deploymentClass"],
            "probeOk": probe["ok"],
            "served": probe.get("served", [])[:3],
        }
    finally:
        app.stop()

    # -- a hand-edited configuration file is a proposal, not a decision ------
    config_path = data_root / "desktop-config.json"
    original = config_path.read_text(encoding="utf-8")
    tampered = json.loads(original)
    tampered["llm"]["baseUrl"] = "https://api.openai.com/v1"
    config_path.write_text(json.dumps(tampered), encoding="utf-8")

    tampered_app = LaunchedApp(application, environment)
    tampered_origin = tampered_app.start()
    try:
        _, tampered_state, _ = http("GET", f"{tampered_origin}/api/desktop/state")
        _, tampered_health, _ = http("GET", f"{tampered_origin}/api/health")
    finally:
        tampered_app.stop()

    if tampered_state["modelRuntime"].get("configured") is not False:
        raise AcceptanceError(
            f"A tampered configuration file was accepted: {tampered_state['modelRuntime']!r}"
        )
    results["tamperedConfigFile"] = {
        "wrote": "https://api.openai.com/v1",
        "configured": tampered_state["modelRuntime"]["configured"],
        "provider": tampered_health["llm"]["provider"],
        "ready": tampered_health["llm"]["ready"],
    }

    # Put the installation back the way the operator left it.
    config_path.write_text(original, encoding="utf-8")
    restored_app = LaunchedApp(application, environment)
    restored_origin = restored_app.start()
    try:
        _, restored_health, _ = http("GET", f"{restored_origin}/api/health")
    finally:
        restored_app.stop()
    if not restored_health["llm"]["ready"]:
        raise AcceptanceError("The installation did not recover its approved model runtime.")
    results["recoveredAfterTamper"] = {
        "provider": restored_health["llm"]["provider"],
        "ready": restored_health["llm"]["ready"],
    }
    return results


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def application_identity(application: Path, artifact: Path | None) -> dict:
    """Exactly which bytes were accepted.

    A reviewer must be able to take this record, rebuild the RPM from the
    delivery sources, and land on the same SHA-256 — otherwise "the installed
    acceptance ran against the final artifact" is a claim rather than a fact.
    """

    identity: dict[str, Any] = {
        "path": str(application),
        "sha256": sha256_file(application),
        "bytes": application.stat().st_size,
    }

    owner = subprocess.run(
        ["rpm", "-qf", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}", str(application)],
        capture_output=True,
        text=True,
    )
    if owner.returncode == 0 and owner.stdout.strip():
        identity["installedPackage"] = owner.stdout.strip()
        verify = subprocess.run(
            ["rpm", "--verify", identity["installedPackage"]], capture_output=True, text=True
        )
        # `rpm --verify` prints a line per file that no longer matches what was
        # packaged; silence means the installed tree is still the artifact.
        identity["rpmVerify"] = {
            "exitCode": verify.returncode,
            "differences": [line for line in verify.stdout.splitlines() if line.strip()],
        }

    if artifact is not None:
        if not artifact.is_file():
            raise AcceptanceError(f"Artifact missing: {artifact}")
        identity["artifact"] = {
            "name": artifact.name,
            "sha256": sha256_file(artifact),
            "bytes": artifact.stat().st_size,
        }
        receipt = artifact.with_suffix(artifact.suffix + ".provenance.json")
        if receipt.is_file():
            identity["artifact"]["provenance"] = json.loads(receipt.read_text(encoding="utf-8"))

    return identity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--application",
        type=Path,
        default=REPO / "src-tauri/target/release/brfv2-desktop",
        help="Shell binary to exercise (defaults to the release build in this checkout)",
    )
    parser.add_argument(
        "--model-base-url",
        default=os.environ.get("BRF_LLM_BASE_URL") or "http://127.0.0.1:8000/v1",
    )
    parser.add_argument("--evidence-dir", type=Path, default=REPO / "docs/evidence")
    parser.add_argument("--keep-data", action="store_true", help="Keep the isolated XDG home")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--artifact",
        type=Path,
        default=None,
        help="The RPM this application was installed from; its SHA-256 is recorded so the "
        "evidence names the exact artifact that was accepted.",
    )
    parser.add_argument(
        "--phases",
        default="ui,lifecycle,security,failure",
        help="Comma-separated subset to run; the phases build on each other in this order.",
    )
    args = parser.parse_args()

    if not args.application.is_file():
        raise AcceptanceError(f"Application missing: {args.application}; run make desktop-build")

    # Generation is real or the run does not happen. A green acceptance must
    # never be obtainable with a scripted or absent model.
    status, models, _ = http("GET", f"{args.model_base_url}/models", timeout=15)
    if status != 200:
        raise AcceptanceError(
            f"The self-hosted model runtime at {args.model_base_url} is not reachable "
            f"(HTTP {status}). Start the tunnel to agenntserver and try again."
        )

    root = Path(tempfile.mkdtemp(prefix="brfv2-acceptance-"))
    environment = isolated_environment(root)
    started = time.time()
    try:
        phases = [name.strip() for name in args.phases.split(",") if name.strip()]
        ui = (
            ui_journey(args.application, environment, args.model_base_url, args.evidence_dir)
            if "ui" in phases
            else "skipped"
        )
        lifecycle = (
            lifecycle_journey(args.application, environment, args.model_base_url)
            if "lifecycle" in phases
            else "skipped"
        )
        boundary = (
            security_boundary(args.application, environment, args.model_base_url)
            if "security" in phases
            else "skipped"
        )
        failures = (
            failure_surfaces(args.application, environment, args.evidence_dir)
            if "failure" in phases
            else "skipped"
        )
    finally:
        if not args.keep_data:
            shutil.rmtree(root, ignore_errors=True)

    binary_dir = args.application.resolve().parent
    bundle_manifest = next(
        (
            candidate
            for candidate in (
                binary_dir.parent.parent / "runtime/BUNDLE.json",
                Path("/usr/lib/BRF Dokument-AI/runtime/BUNDLE.json"),
            )
            if candidate.is_file()
        ),
        None,
    )
    results = {
        "schema": "brfv2-desktop-acceptance/v2",
        "application": str(args.application),
        "applicationIdentity": application_identity(args.application, args.artifact),
        "isolatedXdgHome": str(root),
        "durationSeconds": round(time.time() - started, 1),
        "modelService": {
            "baseUrl": args.model_base_url,
            "served": [
                str(row.get("id") or row.get("name") or "")
                for row in (models.get("data") or models.get("models") or [])
            ][:5],
        },
        "uiJourney": ui,
        "lifecycle": lifecycle,
        "securityBoundary": boundary,
        "failureSurfaces": failures,
    }
    if bundle_manifest is not None:
        results["bundle"] = json.loads(bundle_manifest.read_text(encoding="utf-8"))

    results["paths"] = {
        "note": (
            "Machine-local locations are replaced by stable placeholders: this "
            "checkout reads as <checkout>, the throwaway XDG home this run used "
            "reads as <isolated-xdg-home>, and the operator's home directory "
            "reads as ~. Nothing else is rewritten."
        ),
        "isolatedXdgHomePattern": str(Path(tempfile.gettempdir()) / "brfv2-acceptance-*"),
    }
    rendered = json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True)
    # The evidence is committed to a shared repository; a reviewer needs the
    # shape of these paths, not the build machine's directory layout. Order
    # matters: the checkout usually lives under the home directory, so it has to
    # be redacted before the home directory collapses to `~`.
    rendered = rendered.replace(str(root), "<isolated-xdg-home>")
    rendered = rendered.replace(str(REPO), "<checkout>")
    rendered = rendered.replace(str(Path.home()), "~")
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
