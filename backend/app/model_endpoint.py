"""Which model-service endpoints the installed desktop product may contact.

The desktop delivery promises a *controlled self-hosted* generation boundary.
Accepting any ``http(s)://`` URL does not implement that promise — it accepts
every destination on the internet and merely calls it self-hosted.  This module
is the single place where the promise is turned into a decidable rule, so the
policy text, the runtime check and the tests cannot drift apart.

The rule is default-deny.  An endpoint is allowed only if it falls into one of
two named deployment classes:

``loopback``
    ``localhost``, ``127.0.0.0/8`` or ``[::1]``.  Both ``http`` and ``https``
    are allowed because the bytes never leave the machine — this is the class
    the pilot uses, where the model service is reached through an SSH forward.

``private-network``
    An address literal inside ``10.0.0.0/8``, ``172.16.0.0/12``,
    ``192.168.0.0/16`` or ``fc00::/7``.  ``https`` only: the request carries
    the question and verbatim excerpts of the association's documents, and off
    the host those must not cross a network segment in clear text.

Everything else is rejected, including:

* every scheme other than ``http``/``https``;
* every DNS name other than ``localhost`` — a name is a mutable indirection,
  so a name-based allowance is not a destination allowance;
* public address literals (that is the actual defect this closes);
* link-local ``169.254.0.0/16`` and ``fe80::/10``, which is where cloud
  instance-metadata services live;
* multicast, broadcast, unspecified and otherwise reserved addresses;
* credentials embedded in the URL, and query strings or fragments, neither of
  which an OpenAI-compatible base URL has any use for.

The policy governs the endpoint the *installed product* lets an installation
administrator configure.  Development and evaluation runs, which are driven by
``BRF_LLM_BASE_URL`` from a Makefile target on a developer machine and never
ship, are outside it.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

POLICY_ID = "brfv2-model-endpoint-policy/v1"

LOOPBACK_HOSTNAMES = ("localhost",)

LOOPBACK_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)

# Ports are not restricted beyond being a valid TCP port: which port a
# self-hosted inference server listens on is the operator's choice, and once
# the destination host is bounded to the two classes above, narrowing the port
# removes no reachable destination.
MIN_PORT = 1
MAX_PORT = 65535

_DEFAULT_PORTS = {"http": 80, "https": 443}


class EndpointRejected(ValueError):
    """A configured model endpoint is outside the allowed policy.

    Carries a stable ``code`` for tests and evidence next to the Swedish
    message the user actually sees.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EndpointDecision:
    """The full, recordable verdict for one candidate endpoint."""

    url: str
    allowed: bool
    code: str
    reason: str
    deployment_class: str | None = None
    scheme: str | None = None
    host: str | None = None
    port: int | None = None

    def as_dict(self) -> dict:
        return {
            "policy": POLICY_ID,
            "url": self.url,
            "allowed": self.allowed,
            "code": self.code,
            "reason": self.reason,
            "deploymentClass": self.deployment_class,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
        }


def _reject(url: str, code: str, reason: str, **fields) -> EndpointDecision:
    return EndpointDecision(url=url, allowed=False, code=code, reason=reason, **fields)


def _parsed_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The IP literal ``host`` denotes, or ``None`` when it is a name.

    ``urlsplit`` strips the brackets from ``[::1]`` for us, so a bare IPv6
    literal is what arrives here.
    """

    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def classify_endpoint(url: str) -> EndpointDecision:
    """Decide whether ``url`` may be used as the model-service base URL.

    Never raises for a malformed URL — a rejection is a verdict, and callers
    that want an exception use :func:`require_allowed_endpoint`.
    """

    raw = (url or "").strip()
    if not raw:
        return _reject(raw, "empty", "Ingen adress till modelltjänsten är angiven.")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        return _reject(raw, "unparseable", f"Adressen går inte att tolka: {exc}")

    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        return _reject(
            raw,
            "scheme_not_allowed",
            "Modelltjänstens adress måste börja med http:// eller https://.",
            scheme=scheme or None,
        )

    if parts.username or parts.password:
        return _reject(
            raw,
            "credentials_in_url",
            "Adressen får inte innehålla användarnamn eller lösenord — "
            "använd fältet för åtkomsttoken.",
            scheme=scheme,
        )

    if parts.query or parts.fragment:
        return _reject(
            raw,
            "query_or_fragment",
            "Adressen får inte innehålla frågesträng eller fragment.",
            scheme=scheme,
        )

    try:
        host = parts.hostname
    except ValueError as exc:
        return _reject(raw, "unparseable", f"Adressens värdnamn går inte att tolka: {exc}", scheme=scheme)
    if not host:
        return _reject(raw, "no_host", "Adressen saknar värdnamn.", scheme=scheme)
    host = host.lower()

    try:
        port = parts.port
    except ValueError:
        return _reject(
            raw,
            "port_not_allowed",
            f"Porten måste vara ett tal mellan {MIN_PORT} och {MAX_PORT}.",
            scheme=scheme,
            host=host,
        )
    port = port if port is not None else _DEFAULT_PORTS[scheme]
    if not MIN_PORT <= port <= MAX_PORT:
        return _reject(
            raw,
            "port_not_allowed",
            f"Porten måste vara ett tal mellan {MIN_PORT} och {MAX_PORT}.",
            scheme=scheme,
            host=host,
        )

    address = _parsed_address(host)

    if address is None:
        if host in LOOPBACK_HOSTNAMES:
            return EndpointDecision(
                url=raw,
                allowed=True,
                code="loopback_hostname",
                reason="Loopback på den här datorn.",
                deployment_class="loopback",
                scheme=scheme,
                host=host,
                port=port,
            )
        return _reject(
            raw,
            "hostname_not_allowed",
            "Endast localhost eller en IP-adress i det egna nätet är tillåten — "
            "ett domännamn pekar dit namnuppslagningen råkar peka.",
            scheme=scheme,
            host=host,
            port=port,
        )

    if getattr(address, "ipv4_mapped", None) is not None or getattr(address, "sixtofour", None) is not None:
        return _reject(
            raw,
            "ambiguous_address_form",
            "Skriv adressen som en vanlig IPv4-adress i stället för en "
            "IPv6-inbäddad form.",
            scheme=scheme,
            host=host,
            port=port,
        )

    if any(address in net for net in LOOPBACK_NETWORKS):
        return EndpointDecision(
            url=raw,
            allowed=True,
            code="loopback_address",
            reason="Loopback på den här datorn.",
            deployment_class="loopback",
            scheme=scheme,
            host=host,
            port=port,
        )

    if any(address in net for net in PRIVATE_NETWORKS):
        if scheme != "https":
            return _reject(
                raw,
                "plaintext_off_host",
                "En modelltjänst utanför den här datorn kräver https — frågan "
                "och ordagranna utdrag ur föreningens dokument får inte gå i "
                "klartext över nätet.",
                scheme=scheme,
                host=host,
                port=port,
            )
        return EndpointDecision(
            url=raw,
            allowed=True,
            code="private_network_address",
            reason="Självhostad tjänst på ett privat nät, över https.",
            deployment_class="private-network",
            scheme=scheme,
            host=host,
            port=port,
        )

    if address.is_link_local:
        return _reject(
            raw,
            "link_local_address",
            "Länklokala adresser är inte tillåtna.",
            scheme=scheme,
            host=host,
            port=port,
        )

    return _reject(
        raw,
        "address_not_self_hosted",
        "Adressen ligger utanför den här datorn och det egna privata nätet. "
        "Produkten får bara nå en självhostad modelltjänst.",
        scheme=scheme,
        host=host,
        port=port,
    )


def require_allowed_endpoint(url: str) -> EndpointDecision:
    """:func:`classify_endpoint`, but a rejection raises :class:`EndpointRejected`."""

    decision = classify_endpoint(url)
    if not decision.allowed:
        raise EndpointRejected(decision.code, decision.reason)
    return decision


def policy_document() -> dict:
    """The policy in machine-readable form.

    Served to the UI, written into the acceptance evidence and quoted in the
    documentation, so there is exactly one statement of what is allowed.
    """

    return {
        "policy": POLICY_ID,
        "default": "deny",
        "schemes": sorted(_DEFAULT_PORTS),
        "ports": {"min": MIN_PORT, "max": MAX_PORT, "note": "operatörsvald port, inom värdklassen"},
        "deploymentClasses": [
            {
                "name": "loopback",
                "hosts": [*LOOPBACK_HOSTNAMES, *(str(net) for net in LOOPBACK_NETWORKS)],
                "schemes": sorted(_DEFAULT_PORTS),
                "why": "Trafiken lämnar aldrig datorn; täcker pilotens SSH-forward.",
            },
            {
                "name": "private-network",
                "hosts": [str(net) for net in PRIVATE_NETWORKS],
                "schemes": ["https"],
                "why": "Självhostad tjänst på eget nät; klartext får inte korsa ett nätsegment.",
            },
        ],
        "rejected": [
            {"code": "scheme_not_allowed", "what": "Allt utom http och https."},
            {"code": "hostname_not_allowed", "what": "Alla domännamn utom localhost."},
            {"code": "address_not_self_hosted", "what": "Publika IP-adresser."},
            {"code": "plaintext_off_host", "what": "http mot en adress utanför datorn."},
            {"code": "link_local_address", "what": "169.254.0.0/16 och fe80::/10, inklusive metadatatjänster."},
            {"code": "ambiguous_address_form", "what": "IPv4-inbäddade IPv6-former."},
            {"code": "credentials_in_url", "what": "Användarnamn eller lösenord i adressen."},
            {"code": "query_or_fragment", "what": "Frågesträng eller fragment."},
            {"code": "port_not_allowed", "what": f"Portar utanför {MIN_PORT}–{MAX_PORT}."},
        ],
        "authority": "installation-administrator",
    }
