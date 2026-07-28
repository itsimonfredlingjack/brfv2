"""Real Tauri/WebKitGTK acceptance for the XS-46 desktop spike.

Run from the repository root after ``make desktop-build``:

    backend/.venv/bin/python backend/scripts/desktop_acceptance.py

Only the Python standard library is used.  The test drives the release binary
through tauri-driver/WebKitWebDriver, so it exercises the native webview rather
than a standalone browser. WebKitWebDriver does not implement W3C element/value
for WRY; text is therefore set through WebKit's DOM and the chat is submitted
through the application's real ``keydown Enter`` handler.
"""

from __future__ import annotations

import base64
from http.cookies import SimpleCookie
from http.client import HTTPException
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


STARTUP_SCHEMA = "brfv2-desktop-startup/v1"
DRIVER_ORIGIN = "http://127.0.0.1:4444"


class AcceptanceError(RuntimeError):
    pass


class WebDriver:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.session_id: str | None = None

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            f"{self.origin}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise AcceptanceError(f"WebDriver {method} {path}: HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, HTTPException, OSError) as exc:
            raise AcceptanceError(f"WebDriver {method} {path}: {exc}") from exc
        value = payload.get("value")
        if isinstance(value, dict) and value.get("error"):
            raise AcceptanceError(
                f"WebDriver {method} {path}: {value['error']}: {value.get('message', '')}"
            )
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
        self.request("POST", self._path("/timeouts"), {"script": 15_000})

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
        value = self.request(
            "POST",
            self._path("/window/rect"),
            {"width": width, "height": height},
        )
        if not isinstance(value, dict):
            raise AcceptanceError(f"Unexpected window rect: {value!r}")
        return value

    def close(self) -> None:
        if self.session_id:
            try:
                self.request("DELETE", f"/session/{self.session_id}")
            finally:
                self.session_id = None


def wait_until(label: str, check: Any, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (AcceptanceError, HTTPError, URLError) as exc:
            last_error = exc
        time.sleep(0.2)
    suffix = f" Last error: {last_error}" if last_error else ""
    raise AcceptanceError(f"Timed out waiting for {label}.{suffix}")


def click_by_label(driver: WebDriver, label: str) -> None:
    clicked = driver.execute(
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


def response_headers(url: str) -> dict[str, str]:
    with urlopen(url, timeout=5) as response:
        response.read(1)
        return {key.lower(): value for key, value in response.headers.items()}


def desktop_cookie_contract(origin: str) -> dict[str, Any]:
    login = Request(
        f"{origin}/api/auth/login",
        data=json.dumps({"email": "max@demo.se", "password": "max-demo-2026"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(login, timeout=10) as response:
        response.read()
        set_cookie = response.headers.get("Set-Cookie", "")
    parsed = SimpleCookie()
    parsed.load(set_cookie)
    matching = [(name, morsel) for name, morsel in parsed.items() if name.startswith("brf_desktop_")]
    if len(matching) != 1:
        raise AcceptanceError(f"Expected one desktop Set-Cookie header, got: {set_cookie!r}")
    name, morsel = matching[0]
    contract = {
        "namePrefix": "brf_desktop_",
        "httpOnly": bool(morsel["httponly"]),
        "path": morsel["path"],
        "sameSite": morsel["samesite"].capitalize(),
    }
    if not contract["httpOnly"] or contract["path"] != "/api/" or contract["sameSite"] != "Lax":
        raise AcceptanceError(f"Unsafe desktop cookie attributes: {contract!r}")
    logout = Request(
        f"{origin}/api/auth/logout",
        data=b"",
        method="POST",
        headers={"Cookie": f"{name}={morsel.value}"},
    )
    with urlopen(logout, timeout=10) as response:
        response.read()
        if response.status != 200:
            raise AcceptanceError(f"Cookie probe logout failed: HTTP {response.status}")
    return contract


def port_is_closed(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    application = repo / "src-tauri/target/release/brfv2-desktop-spike"
    evidence_dir = repo / "docs/evidence"
    if not application.is_file():
        raise AcceptanceError(f"Release binary missing: {application}; run make desktop-build")

    driver_logs: list[str] = []
    process = subprocess.Popen(
        ["tauri-driver"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    def read_driver() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            driver_logs.append(line)

    threading.Thread(target=read_driver, daemon=True).start()
    driver = WebDriver(DRIVER_ORIGIN)
    startup: dict[str, Any] | None = None
    results: dict[str, Any] = {}

    try:
        wait_until("tauri-driver", lambda: driver.request("GET", "/status"), timeout=15)
        driver.create_session(application)
        try:
            wait_until(
                "initial application route",
                lambda: driver.execute(
                    "return Boolean(document.querySelector('input[type=email]')) "
                    "|| Boolean(document.querySelector('select[aria-label=\"Byt aktiv förening\"]'));"
                ),
            )
        except AcceptanceError as exc:
            page = driver.execute(
                """
                return {
                  href: location.href,
                  readyState: document.readyState,
                  title: document.title,
                  body: document.body?.innerText.slice(0, 1000),
                  html: document.documentElement?.outerHTML.slice(0, 1000)
                };
                """
            )
            tail = "\n".join(driver_logs[-30:])
            raise AcceptanceError(f"{exc}\nPage: {page!r}\nDriver tail:\n{tail}") from exc
        if driver.execute(
            "return Boolean(document.querySelector('select[aria-label=\"Byt aktiv förening\"]'));"
        ):
            logged_out = driver.execute_async(
                """
                const done = arguments[arguments.length - 1];
                fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
                  .then(response => done({ status: response.status }))
                  .catch(error => done({ error: String(error) }));
                """
            )
            if logged_out.get("status") != 200:
                raise AcceptanceError(f"Could not reset persisted desktop session: {logged_out!r}")
            driver.execute("location.reload(); return true;")
            wait_until(
                "login form after session reset",
                lambda: driver.execute("return Boolean(document.querySelector('input[type=email]'));"),
            )

        driver.execute(
            """
            window.__xs46Errors = [];
            window.addEventListener('error', (event) =>
              window.__xs46Errors.push(String(event.message || event.error)));
            window.addEventListener('unhandledrejection', (event) =>
              window.__xs46Errors.push(String(event.reason)));
            return true;
            """
        )

        driver.type("input[type=email]", "max@demo.se")
        driver.type("input[type=password]", "max-demo-2026")
        login_form = driver.execute(
            """
            const email = document.querySelector('input[type=email]');
            const password = document.querySelector('input[type=password]');
            const button = document.querySelector('button[type=submit]');
            return {
              email: email?.value,
              passwordLength: password?.value.length,
              submitDisabled: button?.disabled
            };
            """
        )
        if login_form != {
            "email": "max@demo.se",
            "passwordLength": len("max-demo-2026"),
            "submitDisabled": False,
        }:
            raise AcceptanceError(f"Login form did not accept input: {login_form!r}")
        driver.click("button[type=submit]")
        wait_until(
            "authenticated workspace",
            lambda: driver.execute(
                "return Boolean(document.querySelector('select[aria-label=\"Byt aktiv förening\"]'));"
            ),
        )

        readiness = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch('/api/desktop/readiness', { credentials: 'include' })
              .then(async response => done({
                status: response.status,
                body: await response.json(),
                origin: location.origin
              }))
              .catch(error => done({ error: String(error) }));
            """
        )
        if readiness.get("status") != 200 or readiness["body"].get("schema") != STARTUP_SCHEMA:
            raise AcceptanceError(f"Invalid readiness response: {readiness!r}")
        startup = readiness["body"]
        if startup.get("origin") != readiness.get("origin"):
            raise AcceptanceError(f"UI/API origin mismatch: {readiness!r}")

        me = driver.execute_async(
            """
            const done = arguments[arguments.length - 1];
            fetch('/api/auth/me', { credentials: 'include' })
              .then(async response => done({ status: response.status, body: await response.json() }))
              .catch(error => done({ error: String(error) }));
            """
        )
        if me.get("status") != 200 or me["body"].get("user", {}).get("email") != "max@demo.se":
            raise AcceptanceError(f"/api/auth/me did not authenticate: {me!r}")

        webdriver_cookies = driver.cookies()
        cookie_contract = desktop_cookie_contract(startup["origin"])

        set_select(driver, 'select[aria-label="Byt aktiv förening"]', "sjoutsikten-7")
        wait_until(
            "tenant switch to Sjöutsikten",
            lambda: driver.execute(
                "return document.querySelector('select[aria-label=\"Byt aktiv förening\"]').value "
                "=== 'sjoutsikten-7';"
            ),
        )
        set_select(driver, 'select[aria-label="Byt aktiv förening"]', "gjutformen-12")
        wait_until(
            "tenant switch back to Gjutformen",
            lambda: driver.execute(
                "return document.querySelector('select[aria-label=\"Byt aktiv förening\"]').value "
                "=== 'gjutformen-12';"
            ),
        )

        click_by_label(driver, "AI-chatt")
        wait_until(
            "general chat input",
            lambda: driver.execute(
                "return Boolean(document.querySelector('input[placeholder=\"Ställ en generell fråga till AI:n...\"]'));"
            ),
        )
        driver.type(
            'input[placeholder="Ställ en generell fråga till AI:n..."]',
            "Var har styrelsen sitt säte?",
        )
        driver.press_enter('input[placeholder="Ställ en generell fråga till AI:n..."]')
        wait_until(
            "grounded answer and citation",
            lambda: driver.execute(
                "return document.body.innerText.includes('Styrelsen har sitt säte i Göteborgs kommun') "
                "&& document.body.innerText.includes('Stadgar Brf Gjutformen 12.pdf');"
            ),
            timeout=45,
        )
        click_by_label(driver, "Stadgar Brf Gjutformen 12.pdf")
        highlight = wait_until(
            "PDF page and citation highlight",
            lambda: driver.execute(
                """
                const marker = document.querySelector('[data-testid="citation-highlight"]');
                const page = document.querySelector('[data-testid="pdf-page-indicator"]');
                if (!marker || !page || !page.textContent.includes('Sida 1 av 3')) return false;
                const rect = marker.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && {
                  page: page.textContent.trim(),
                  rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                };
                """
            ),
            timeout=45,
        )
        driver.screenshot(evidence_dir / "xs46-tauri-answer-highlight.png")

        zoom_before = driver.execute(
            "return [...document.querySelectorAll('.pdf-actions span')].map(e => e.textContent)"
            ".find(text => text.includes('%'));"
        )
        click_by_label(driver, "Zooma in")
        zoom_after = wait_until(
            "PDF zoom",
            lambda: driver.execute(
                "return [...document.querySelectorAll('.pdf-actions span')].map(e => e.textContent)"
                ".find(text => text.includes('%')) === '110%' && '110%';"
            ),
        )

        click_by_label(driver, "Tillbaka")
        click_by_label(driver, "AI-chatt")
        wait_until(
            "chat restored",
            lambda: driver.execute(
                "return Boolean(document.querySelector('input[placeholder=\"Ställ en generell fråga till AI:n...\"]'));"
            ),
        )
        driver.type(
            'input[placeholder="Ställ en generell fråga till AI:n..."]',
            "Vilka öppettider har föreningens planetarium?",
        )
        click_by_label(driver, "Skicka fråga")
        try:
            wait_until(
                "insufficient-data refusal",
                lambda: driver.execute(
                    """
                    const messages = [...document.querySelectorAll('.chat-message.ai')];
                    const latest = messages.at(-1);
                    return Boolean(latest?.querySelector('.chat-refusal-header'))
                      && latest.querySelectorAll('.citation-pill').length === 0;
                    """
                ),
                timeout=45,
            )
        except AcceptanceError as exc:
            refusal_state = driver.execute(
                """
                return {
                  input: document.querySelector(
                    'input[placeholder="Ställ en generell fråga till AI:n..."]'
                  )?.value,
                  sendDisabled: document.querySelector(
                    'button[aria-label="Skicka fråga"]'
                  )?.disabled,
                  messages: [...document.querySelectorAll('.chat-message')]
                    .map(message => message.textContent.trim()).slice(-4),
                  errors: window.__xs46Errors
                };
                """
            )
            raise AcceptanceError(f"{exc} State: {refusal_state!r}") from exc
        latest_ai = driver.execute(
            """
            const messages = [...document.querySelectorAll('.chat-message.ai')];
            const latest = messages.at(-1);
            return latest && {
              text: latest.innerText,
              citations: latest.querySelectorAll('.citation-pill').length
            };
            """
        )
        if not latest_ai or latest_ai["citations"] != 0:
            raise AcceptanceError(f"Refusal unexpectedly contains citations: {latest_ai!r}")
        driver.screenshot(evidence_dir / "xs46-tauri-refusal.png")

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

        headers = response_headers(f"{startup['origin']}/brfv2/")
        csp = headers.get("content-security-policy", "")
        if "default-src 'none'" not in csp or "connect-src 'self'" not in csp:
            raise AcceptanceError(f"Restrictive CSP missing: {csp!r}")

        runtime_errors = driver.execute("return window.__xs46Errors;")
        if runtime_errors:
            raise AcceptanceError(f"Webview runtime errors: {runtime_errors!r}")

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
              value: 'XS-46 IPC SHOULD BE DENIED'
            }).then(
              value => done({ allowed: true, result: String(value) }),
              error => done({ allowed: false, result: String(error) })
            );
            """
        )
        if ipc_attempt["allowed"]:
            raise AcceptanceError(f"Remote HTTP page obtained Tauri IPC permission: {ipc_attempt!r}")

        results = {
            "startup": startup,
            "platform": {
                "userAgent": driver.execute("return navigator.userAgent;"),
                "devicePixelRatio": compact_layout["devicePixelRatio"],
            },
            "sameOrigin": readiness["origin"],
            "authenticatedUser": me["body"]["user"]["email"],
            "tenantSwitch": ["gjutformen-12", "sjoutsikten-7", "gjutformen-12"],
            "cookie": {
                **cookie_contract,
                "webdriverEnumerated": len(webdriver_cookies),
            },
            "supportedAnswer": {
                "citation": "Stadgar Brf Gjutformen 12.pdf s.1",
                "highlight": highlight,
            },
            "pdfZoom": {"before": zoom_before, "after": zoom_after},
            "keyboard": {
                "mode": "WebKit DOM events",
                "chatSubmit": "Enter",
                "nativeWebDriverElementValue": "unsupported by WebKitWebDriver for WRY",
                "nativeWaylandAutomation": "blocked by this KWin/WebKit automation environment",
            },
            "refusal": {"citations": latest_ai["citations"]},
            "compactWindow": {"rect": compact_rect, "layout": compact_layout},
            "security": {
                "csp": csp,
                "globalTauri": global_tauri,
                "remoteIpcSetTitle": ipc_attempt,
                "runtimeErrors": runtime_errors,
            },
            "screenshots": [
                "docs/evidence/xs46-tauri-answer-highlight.png",
                "docs/evidence/xs46-tauri-refusal.png",
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

    if startup is None:
        tail = "\n".join(driver_logs[-30:])
        raise AcceptanceError(f"Desktop startup contract was not observed.\n{tail}")
    port = int(startup["port"])
    wait_until("desktop loopback port cleanup", lambda: port_is_closed(port), timeout=10)
    results["cleanup"] = {"port": port, "closed": True, "tauriDriverExit": process.returncode}
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
