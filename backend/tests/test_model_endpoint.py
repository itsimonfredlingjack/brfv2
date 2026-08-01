"""The model-endpoint policy: what "controlled self-hosted" actually admits.

These tests are the executable half of the policy text in
:mod:`app.model_endpoint`. If the two ever disagree, this file fails.
"""

from __future__ import annotations

import pytest

from app.model_endpoint import (
    POLICY_ID,
    EndpointRejected,
    classify_endpoint,
    policy_document,
    require_allowed_endpoint,
)

ALLOWED = [
    # The pilot's own topology: the model runs on agenntserver and the port is
    # SSH-forwarded, so the client's destination is genuinely loopback.
    ("http://127.0.0.1:8000/v1", "loopback"),
    ("http://localhost:8000/v1", "loopback"),
    ("https://127.0.0.1:8443/v1", "loopback"),
    ("http://127.5.4.3:11434/v1", "loopback"),
    ("http://[::1]:8000/v1", "loopback"),
    # A self-hosted service elsewhere on the operator's own network, over TLS.
    ("https://10.1.2.3:8000/v1", "private-network"),
    ("https://172.16.0.9/v1", "private-network"),
    ("https://192.168.1.50:8000/v1", "private-network"),
    ("https://[fd00::1]:8000/v1", "private-network"),
]

REJECTED = [
    # The defect this policy closes: a hosted third-party API is neither
    # loopback nor the operator's network, and calling it "self-hosted only"
    # because it is https does not make it so.
    ("https://api.anthropic.com/v1", "hostname_not_allowed"),
    ("https://api.openai.com/v1", "hostname_not_allowed"),
    ("https://model.example.com:8000/v1", "hostname_not_allowed"),
    # A name that today resolves to a private address is still a name.
    ("https://agenntserver.local:8000/v1", "hostname_not_allowed"),
    ("https://8.8.8.8/v1", "address_not_self_hosted"),
    ("http://93.184.216.34:8000/v1", "address_not_self_hosted"),
    # Off-host plaintext: the request carries verbatim document excerpts.
    ("http://192.168.1.50:8000/v1", "plaintext_off_host"),
    ("http://10.1.2.3:8000/v1", "plaintext_off_host"),
    # Cloud instance metadata and other link-local destinations.
    ("http://169.254.169.254/latest/meta-data", "link_local_address"),
    ("https://[fe80::1]:8000/v1", "link_local_address"),
    # Not an HTTP destination at all.
    ("file:///etc/passwd", "scheme_not_allowed"),
    ("ftp://127.0.0.1/v1", "scheme_not_allowed"),
    ("127.0.0.1:8000", "scheme_not_allowed"),
    # Shapes an OpenAI-compatible base URL has no use for, and that only make
    # the destination harder to read.
    ("http://user:secret@127.0.0.1:8000/v1", "credentials_in_url"),
    ("http://127.0.0.1:8000/v1?upstream=https://api.openai.com", "query_or_fragment"),
    ("http://[::ffff:127.0.0.1]:8000/v1", "ambiguous_address_form"),
    ("http://:8000/v1", "no_host"),
    ("http://127.0.0.1:99999/v1", "port_not_allowed"),
]


@pytest.mark.parametrize("url,deployment_class", ALLOWED)
def test_allowed_endpoints(url, deployment_class):
    decision = classify_endpoint(url)
    assert decision.allowed is True, decision.reason
    assert decision.deployment_class == deployment_class
    assert require_allowed_endpoint(url) == decision


@pytest.mark.parametrize("url,code", REJECTED)
def test_rejected_endpoints(url, code):
    decision = classify_endpoint(url)
    assert decision.allowed is False
    assert decision.code == code
    assert decision.deployment_class is None
    with pytest.raises(EndpointRejected) as raised:
        require_allowed_endpoint(url)
    assert raised.value.code == code
    # Every rejection has to be able to explain itself to the person who typed
    # the address; a bare code in a dialog is not an explanation.
    assert len(raised.value.message) > 20


def test_an_empty_address_is_a_state_not_an_error():
    decision = classify_endpoint("")
    assert decision.allowed is False
    assert decision.code == "empty"


def test_the_published_policy_matches_the_implementation():
    """The document served to the UI and written into evidence is generated
    from the same constants the checks use — no second, drifting copy."""
    document = policy_document()
    assert document["policy"] == POLICY_ID
    assert document["default"] == "deny"
    assert document["authority"] == "installation-administrator"

    classes = {row["name"]: row for row in document["deploymentClasses"]}
    assert set(classes) == {"loopback", "private-network"}
    assert classes["private-network"]["schemes"] == ["https"]
    assert sorted(classes["loopback"]["schemes"]) == ["http", "https"]

    published_codes = {row["code"] for row in document["rejected"]}
    assert {code for _, code in REJECTED} <= published_codes | {"no_host"}

    # Every deployment class the document advertises is actually reachable, and
    # nothing outside the two classes is.
    assert {decision for _, decision in ALLOWED} == set(classes)
