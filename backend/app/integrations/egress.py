"""The only place this product may talk to a system it does not own.

Until this module existed, the desktop application had exactly one outbound
address — the model runtime, policed by :mod:`app.model_endpoint` — and every
other byte stayed on the machine. Live Outlook and Fortnox integrations change
that, so the widening is written down here as code rather than left implicit in
whichever adapter happens to construct a URL.

Three rules, all enforced in :class:`ReadOnlyEgress` and none of them optional:

1. **A closed host allowlist.** Each provider declares the exact hosts it may
   reach. A URL for anything else raises before a socket is opened, including
   after a redirect — the redirect target is checked with the same function as
   the original request, because "follow redirects" is how an allowlist that
   only checks the first hop gets walked out of.

2. **GET for data, POST only for tokens.** Reading someone's mailbox or ledger
   is a GET. The single exception is the OAuth token endpoint, which is an
   unavoidable POST and is therefore a *separate method* (:meth:`token_post`)
   restricted to the provider's declared authority host and token path. There
   is no general POST, no PUT, no PATCH and no DELETE, so an adapter cannot
   grow one by passing a different string.

3. **Secrets never reach a log.** :meth:`_log` records method, host and path
   and nothing else. Query strings are dropped whole (Graph puts ``$filter``
   values there, and a token can be smuggled anywhere), and the Authorization
   header is never formatted into a message, an exception or a repr.

The class takes its transport as an argument. In production it is
:mod:`httpx`; in the test suite it is a stub that asserts the exact request
shape. That is what lets the whole integration be tested — including the
refusals — with no credential, no network and no recorded traffic.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

logger = logging.getLogger("brf.integrations.egress")

# Wall-clock ceiling for one call. Long enough for Graph to page a mailbox,
# short enough that a hung TLS handshake does not wedge an operator's click.
DEFAULT_TIMEOUT_S = 30.0

# Retry only what is worth retrying: a rate limit or a transient server fault.
# Never a 4xx that is about us, and never a POST that is not idempotent — the
# token endpoint is excluded because a redeemed authorization code is spent.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_RETRY_SLEEP_S = 20.0

# Hard cap on a single response body. A mailbox MIME fetch is the largest thing
# read here and the parser refuses anything over 25 MB anyway; this stops a
# hostile or broken endpoint from being read into memory without bound.
MAX_RESPONSE_BYTES = 30 * 1024 * 1024


class EgressRefused(RuntimeError):
    """A request was refused before it left the process."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RemoteError(RuntimeError):
    """The remote system answered, and the answer was not usable.

    ``status`` is the HTTP status. ``detail`` is the provider's own message,
    already trimmed — it is shown to an operator, so it must be safe to
    display and must never be built from anything we sent.
    """

    def __init__(self, status: int, detail: str, *, provider: str) -> None:
        super().__init__(f"{provider}: HTTP {status} {detail}".strip())
        self.status = status
        self.detail = detail
        self.provider = provider


@dataclass(frozen=True)
class EgressPolicy:
    """What one provider is allowed to reach, declared once.

    ``api_hosts`` may be read from. ``authority_host`` is where tokens are
    obtained, and ``token_paths`` narrows that to the exact endpoints — an
    authority host with an open path list would let a POST go anywhere on
    login.microsoftonline.com.
    """

    provider: str
    api_hosts: frozenset[str]
    authority_host: str
    token_paths: tuple[str, ...]
    # Paths on the authority host that may be POSTed to *without* a token, for
    # flows that start a login (Microsoft's device-code endpoint). Kept apart
    # from token_paths so the two cannot be confused for one another.
    login_paths: tuple[str, ...] = ()
    user_agent: str = "brf-dokument-ai/0.2 (+local desktop; read-only)"

    def all_hosts(self) -> frozenset[str]:
        return self.api_hosts | {self.authority_host}


@dataclass
class Response:
    status: int
    headers: Mapping[str, str]
    content: bytes

    def json(self) -> Any:
        import json

        if not self.content:
            return None
        return json.loads(self.content.decode("utf-8"))


# A transport is any callable with this shape. httpx.Client.request satisfies
# it after the thin adapter below; a test stub satisfies it directly.
Transport = Callable[..., Response]


def _httpx_transport(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    content: bytes | None,
    timeout: float,
) -> Response:
    import httpx

    # follow_redirects=False, deliberately. A 302 is returned to the caller,
    # which re-enters check_url() for the new location — the allowlist applies
    # to every hop or it applies to none of them.
    reply = httpx.request(
        method,
        url,
        headers=dict(headers),
        content=content,
        timeout=timeout,
        follow_redirects=False,
    )
    return Response(
        status=reply.status_code,
        headers={k.lower(): v for k, v in reply.headers.items()},
        content=reply.content,
    )


@dataclass
class ReadOnlyEgress:
    """Outbound HTTP for one provider, with the rules above enforced."""

    policy: EgressPolicy
    transport: Transport = _httpx_transport
    timeout_s: float = DEFAULT_TIMEOUT_S
    # Injected so tests can assert backoff without sleeping through it.
    sleep: Callable[[float], None] = time.sleep
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    # ---------- the allowlist ----------

    def check_url(self, url: str, *, allow_authority: bool = False) -> tuple[str, str]:
        """Return ``(host, path)`` for a permitted URL, or raise.

        A single function for the original request and every redirect, because
        two functions is how they end up disagreeing.
        """
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise EgressRefused(
                "not_https",
                f"Endast https tillåts mot externa system ({url.split('://', 1)[0]} begärdes).",
            )
        host = (parts.hostname or "").lower()
        permitted = self.policy.all_hosts() if allow_authority else self.policy.api_hosts
        if host not in permitted:
            raise EgressRefused(
                "host_not_allowed",
                f"{host or '(tom värd)'} finns inte i tillåtna värdar för "
                f"{self.policy.provider}: {', '.join(sorted(permitted))}.",
            )
        if parts.port not in (None, 443):
            raise EgressRefused(
                "port_not_allowed", f"Endast port 443 tillåts ({parts.port} begärdes)."
            )
        return host, parts.path or "/"

    # ---------- the two verbs ----------

    def get(
        self,
        url: str,
        *,
        access_token: str | None = None,
        accept: str = "application/json",
        extra_headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Read. The only verb an adapter is given for data."""
        host, path = self.check_url(url)
        headers = {
            "Accept": accept,
            "User-Agent": self.policy.user_agent,
            **dict(extra_headers or {}),
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return self._send("GET", url, host, path, headers=headers, content=None, retry=True)

    def token_post(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        basic_auth: str | None = None,
        purpose: str = "token",
    ) -> Response:
        """The one POST that exists, and only to a declared token endpoint.

        ``purpose`` selects which path list applies: ``"token"`` for redeeming
        or refreshing, ``"login"`` for starting a device-code flow. Anything
        else is refused, so a caller cannot reach a third endpoint by naming it.
        """
        host, path = self.check_url(url, allow_authority=True)
        if host != self.policy.authority_host:
            raise EgressRefused(
                "not_the_authority",
                f"POST tillåts bara mot {self.policy.authority_host}, inte {host}.",
            )
        allowed = {
            "token": self.policy.token_paths,
            "login": self.policy.login_paths,
        }.get(purpose)
        if allowed is None:
            raise EgressRefused("unknown_purpose", f"Okänt POST-syfte: {purpose!r}.")
        if path not in allowed:
            raise EgressRefused(
                "path_not_allowed",
                f"{path} är inte en tillåten {purpose}-endpoint för {self.policy.provider}.",
            )
        from urllib.parse import urlencode

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.policy.user_agent,
        }
        if basic_auth:
            headers["Authorization"] = f"Basic {basic_auth}"
        body = urlencode(dict(form)).encode("ascii")
        # retry=False: an authorization code is single-use and a rotated
        # refresh token is spent the moment the server accepts it. Retrying a
        # token POST that timed out after the server processed it is how a
        # connection loses its refresh token.
        return self._send("POST", url, host, path, headers=headers, content=body, retry=False)

    # ---------- plumbing ----------

    def _log(self, method: str, host: str, path: str) -> None:
        """Method, host, path. Never the query string and never a header.

        Graph puts ``$filter`` and ``$select`` in the query, Fortnox puts
        filters there, and both are places a value with a person's name or —
        after one bad refactor — a token can end up.
        """
        self.calls.append((method, host, path))
        logger.info("%s https://%s%s", method, host, path)

    def _send(
        self,
        method: str,
        url: str,
        host: str,
        path: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
        retry: bool,
    ) -> Response:
        attempts = MAX_ATTEMPTS if retry else 1
        last: Response | None = None
        for attempt in range(1, attempts + 1):
            self._log(method, host, path)
            reply = self.transport(
                method, url, headers=headers, content=content, timeout=self.timeout_s
            )
            if len(reply.content) > MAX_RESPONSE_BYTES:
                raise EgressRefused(
                    "response_too_large",
                    f"Svaret från {host} är större än {MAX_RESPONSE_BYTES} byte.",
                )
            if reply.status in (301, 302, 303, 307, 308):
                location = reply.headers.get("location", "")
                if not location:
                    raise RemoteError(reply.status, "omdirigering utan Location", provider=self.policy.provider)
                # Same check, same function. A redirect to a host outside the
                # allowlist is refused here rather than followed.
                host, path = self.check_url(location, allow_authority=(method == "POST"))
                url = location
                continue
            if retry and reply.status in RETRY_STATUSES and attempt < attempts:
                self.sleep(self._backoff(reply, attempt))
                last = reply
                continue
            return reply
        return last if last is not None else reply  # pragma: no cover - loop always returns

    @staticmethod
    def _backoff(reply: Response, attempt: int) -> float:
        raw = reply.headers.get("retry-after", "")
        try:
            wait = float(raw)
        except (TypeError, ValueError):
            wait = float(2**attempt)
        return max(0.0, min(wait, MAX_RETRY_SLEEP_S))


def read_json(reply: Response, *, provider: str) -> Any:
    """Turn a reply into JSON, or into a :class:`RemoteError` an operator can read."""
    if 200 <= reply.status < 300:
        try:
            return reply.json()
        except ValueError as exc:
            raise RemoteError(reply.status, f"svaret är inte JSON ({exc})", provider=provider) from exc
    raise RemoteError(reply.status, _describe(reply), provider=provider)


def _describe(reply: Response) -> str:
    """The remote system's own error message, trimmed and de-fanged.

    Providers put useful text in wildly different places; take the first one
    that exists and cap it, so a huge HTML error page cannot become a Swedish
    error dialog.
    """
    try:
        payload = reply.json()
    except ValueError:
        payload = None
    # Ordered by how much it helps a person, not by how the payload is shaped:
    # a sentence beats a machine code, and the code is only worth showing when
    # there is no sentence. `error` as a bare string is that machine code in
    # every OAuth error, so it comes last.
    candidates: list[str] = []
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            candidates += [str(error.get("message") or "")]
        candidates += [
            str(payload.get("error_description") or ""),
            str(payload.get("message") or ""),
        ]
        # Some Swedish accounting APIs nest the message one level down.
        info = payload.get("ErrorInformation")
        if isinstance(info, dict):
            candidates.append(str(info.get("message") or info.get("Message") or ""))
        if isinstance(error, dict):
            candidates.append(str(error.get("code") or ""))
        elif isinstance(error, str):
            candidates.append(error)
    text = next((c for c in candidates if c.strip()), "")
    if not text:
        text = reply.content[:200].decode("utf-8", "replace").strip()
    return text[:300]


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "EgressPolicy",
    "EgressRefused",
    "MAX_RESPONSE_BYTES",
    "ReadOnlyEgress",
    "RemoteError",
    "Response",
    "Transport",
    "read_json",
]
