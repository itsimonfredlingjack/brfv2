"""The live integrations, exercised without a credential, a network or a recording.

Every test here drives the real code — the real URLs, the real headers, the
real refusals, the real token bookkeeping — through an injected transport that
asserts what it was asked for and answers with a canned payload. That is the
only honest way to test an OAuth client on a build machine, and it is also the
strictest: a stub that refuses anything but the exact request shape catches a
wrong verb, a wrong host and a leaked secret in a way a live call against a
forgiving server would not.

What is deliberately asserted, beyond "it works":

* no request is ever anything but a GET, except a POST to the provider's own
  token endpoint;
* a URL outside the provider's host allowlist is refused *before* a socket;
* the scope list is a constant and cannot be widened by configuration;
* no access token, refresh token or client secret appears in any API response,
  in the connection record, or in a backup archive;
* a rotated refresh token is persisted before it is used.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.integrations import fortnox as fortnox_mod
from app.integrations import graph_mail as graph_mod
from app.integrations.connections import ConnectionManager, NotConnected
from app.integrations.credentials import CredentialStore, Secrets
from app.integrations.egress import (
    EgressRefused,
    ReadOnlyEgress,
    RemoteError,
    Response,
    read_json,
)
from app.integrations.oauth import OAuthError, PendingLogins

MAIL = Path(__file__).resolve().parent.parent / "fixtures" / "mail"


# ---------------------------------------------------------------------------
# The stub transport
# ---------------------------------------------------------------------------


class StubTransport:
    """Answers a fixed route table and records every request verbatim.

    An unrouted request raises rather than returning a 404: a test that
    silently exercised a URL nobody wrote a route for would be asserting
    nothing.
    """

    def __init__(self, routes: dict[tuple[str, str], object] | None = None) -> None:
        self.routes: dict[tuple[str, str], object] = dict(routes or {})
        self.requests: list[dict] = []

    def route(self, method: str, path: str, payload, status: int = 200, headers=None):
        self.routes[(method, path)] = (payload, status, headers or {})
        return self

    def __call__(self, method, url, *, headers, content, timeout):
        parts = urlsplit(url)
        self.requests.append(
            {
                "method": method,
                "host": parts.hostname,
                "path": parts.path,
                "query": parse_qs(parts.query),
                "headers": dict(headers),
                "body": parse_qs(content.decode("ascii")) if content else {},
            }
        )
        key = (method, parts.path)
        if key not in self.routes:
            raise AssertionError(f"otestad begäran: {method} {parts.path}")
        payload, status, extra = self.routes[key]
        if callable(payload):
            payload = payload(self.requests[-1])
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return Response(status=status, headers={"content-type": "application/json", **extra}, content=body)

    # ---- assertions the tests share ----

    @property
    def methods(self) -> set[str]:
        return {r["method"] for r in self.requests}

    def authorization_for(self, path: str) -> str:
        for request in self.requests:
            if request["path"] == path:
                return request["headers"].get("Authorization", "")
        raise AssertionError(f"ingen begäran mot {path}")


GRAPH_TOKEN_PATH = "/consumers/oauth2/v2.0/token"
GRAPH_DEVICE_PATH = "/consumers/oauth2/v2.0/devicecode"
CLIENT_ID = "11111111-2222-3333-4444-555555555555"


def graph_connected(tmp_path, *, transport: StubTransport) -> ConnectionManager:
    credentials = CredentialStore(tmp_path, tenant_id="t1")
    manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
    manager.configure_graph(
        graph_mod.GraphConfig(client_id=CLIENT_ID, authority="consumers"), user_id="admin"
    )
    credentials.write_secrets(
        graph_mod.PROVIDER,
        Secrets(
            access_token="access-1",
            refresh_token="refresh-1",
            access_expires_epoch=time.time() + 3600,
        ),
    )
    connection = credentials.get_connection(graph_mod.PROVIDER)
    credentials.put_connection(connection.model_copy(update={"status": "connected"}))
    return manager


# ---------------------------------------------------------------------------
# The egress boundary
# ---------------------------------------------------------------------------


class TestEgressBoundary:
    def test_a_host_outside_the_allowlist_is_refused_before_a_socket(self):
        transport = StubTransport()
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=transport)
        with pytest.raises(EgressRefused) as exc:
            egress.get("https://evil.example/v1.0/me")
        assert exc.value.code == "host_not_allowed"
        assert transport.requests == [], "begäran gick iväg trots att den vägrades"

    def test_plain_http_is_refused(self):
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=StubTransport())
        with pytest.raises(EgressRefused) as exc:
            egress.get("http://graph.microsoft.com/v1.0/me")
        assert exc.value.code == "not_https"

    def test_a_redirect_off_the_allowlist_is_not_followed(self):
        transport = StubTransport().route(
            "GET",
            "/v1.0/me",
            {},
            status=302,
            headers={"location": "https://evil.example/steal"},
        )
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=transport)
        with pytest.raises(EgressRefused) as exc:
            egress.get(f"{graph_mod.GRAPH_BASE}/me")
        assert exc.value.code == "host_not_allowed"

    def test_post_is_only_possible_against_a_declared_token_path(self):
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=StubTransport())
        with pytest.raises(EgressRefused) as exc:
            egress.token_post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
                {"a": "b"},
            )
        assert exc.value.code == "path_not_allowed"

    def test_an_api_host_cannot_be_posted_to_at_all(self):
        egress = ReadOnlyEgress(policy=fortnox_mod.policy(), transport=StubTransport())
        with pytest.raises(EgressRefused) as exc:
            egress.token_post(f"{fortnox_mod.API_BASE}/supplierinvoices", {"a": "b"})
        assert exc.value.code == "not_the_authority"

    def test_the_log_never_carries_a_query_string_or_a_header(self, caplog):
        transport = StubTransport().route("GET", "/v1.0/me", {"displayName": "X"})
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=transport)
        with caplog.at_level("INFO", logger="brf.integrations.egress"):
            egress.get(f"{graph_mod.GRAPH_BASE}/me?$select=displayName", access_token="s3cret")
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert "graph.microsoft.com/v1.0/me" in logged
        assert "$select" not in logged
        assert "s3cret" not in logged

    def test_a_rate_limit_is_retried_and_a_token_post_is_not(self):
        calls = {"n": 0}

        def flaky(request):
            calls["n"] += 1
            return {"value": []} if calls["n"] > 1 else {}

        transport = StubTransport()
        transport.routes[("GET", "/v1.0/me/mailFolders/inbox/messages")] = (
            flaky,
            429,
            {"retry-after": "0"},
        )
        egress = ReadOnlyEgress(
            policy=graph_mod.policy(), transport=transport, sleep=lambda _: None
        )
        egress.get(f"{graph_mod.GRAPH_BASE}/me/mailFolders/inbox/messages")
        assert calls["n"] == 3  # MAX_ATTEMPTS

        posts = StubTransport().route("POST", GRAPH_TOKEN_PATH, {"error": "slow"}, status=429)
        post_egress = ReadOnlyEgress(
            policy=graph_mod.policy(), transport=posts, sleep=lambda _: None
        )
        post_egress.token_post(
            f"https://{graph_mod.AUTHORITY_HOST}{GRAPH_TOKEN_PATH}", {"grant_type": "x"}
        )
        assert len(posts.requests) == 1, "en token-POST får aldrig upprepas"

    def test_a_remote_error_carries_the_providers_own_message(self):
        transport = StubTransport().route(
            "GET",
            "/v1.0/me",
            {"error": {"code": "ErrorAccessDenied", "message": "Access is denied."}},
            status=403,
        )
        egress = ReadOnlyEgress(policy=graph_mod.policy(), transport=transport)
        with pytest.raises(RemoteError) as exc:
            read_json(egress.get(f"{graph_mod.GRAPH_BASE}/me"), provider="microsoft-graph")
        assert exc.value.status == 403
        assert "Access is denied." in exc.value.detail


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------


class TestScopesAreAConstant:
    def test_graph_asks_only_for_read_scopes(self):
        config = graph_mod.GraphConfig(client_id=CLIENT_ID).validated()
        assert config.scopes() == ("offline_access", "User.Read", "Mail.Read")
        for scope in config.scopes():
            assert "write" not in scope.lower()
            assert "send" not in scope.lower()

    def test_a_shared_mailbox_adds_only_the_shared_read_scope(self):
        config = graph_mod.GraphConfig(
            client_id=CLIENT_ID, mailbox="styrelsen@brf.example"
        ).validated()
        assert config.scopes()[-1] == "Mail.Read.Shared"

    def test_no_configuration_field_can_reach_the_scope_list(self):
        """The scopes come from a module constant, not from anything typed in."""
        fields = set(graph_mod.GraphConfig.__dataclass_fields__)
        assert "scopes" not in fields and "scope" not in fields

    def test_fortnox_scope_set_is_minimal_and_the_register_is_opt_in(self):
        base = fortnox_mod.FortnoxConfig(
            client_id="abc", redirect_uri="https://x.example/cb"
        ).validated()
        assert base.scopes() == ("supplierinvoice", "companyinformation")
        wider = fortnox_mod.FortnoxConfig(
            client_id="abc", redirect_uri="https://x.example/cb", read_supplier_register=True
        ).validated()
        assert wider.scopes()[-1] == "supplier"


# ---------------------------------------------------------------------------
# Device code sign-in
# ---------------------------------------------------------------------------


class TestDeviceCodeLogin:
    def _transport(self):
        return (
            StubTransport()
            .route(
                "POST",
                GRAPH_DEVICE_PATH,
                {
                    "device_code": "DEVICE-SECRET",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://microsoft.com/devicelogin",
                    "expires_in": 900,
                    "interval": 0,
                },
            )
            .route("GET", "/v1.0/me", {"displayName": "Simon", "mail": "s@example.com"})
        )

    def test_the_operator_is_given_the_short_code_and_never_the_device_code(self, tmp_path):
        transport = self._transport()
        credentials = CredentialStore(tmp_path, tenant_id="t1")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
        manager.configure_graph(graph_mod.GraphConfig(client_id=CLIENT_ID), user_id="admin")
        pending = manager.begin_login(graph_mod.PROVIDER)
        public = pending.public()
        assert public["userCode"] == "ABCD-EFGH"
        assert "DEVICE-SECRET" not in json.dumps(public)

    def test_pending_then_connected_and_the_admin_is_recorded(self, tmp_path):
        transport = self._transport()
        answers = iter(
            [
                ({"error": "authorization_pending"}, 400),
                (
                    {
                        "access_token": "at-1",
                        "refresh_token": "rt-1",
                        "expires_in": 3600,
                        "scope": "Mail.Read User.Read offline_access",
                    },
                    200,
                ),
            ]
        )

        class Sequenced(StubTransport):
            def __call__(self, method, url, **kwargs):
                if urlsplit(url).path == GRAPH_TOKEN_PATH:
                    payload, status = next(answers)
                    self.requests.append({"method": method, "path": GRAPH_TOKEN_PATH, "headers": dict(kwargs["headers"]), "query": {}, "host": urlsplit(url).hostname, "body": {}})
                    return Response(status=status, headers={}, content=json.dumps(payload).encode())
                return super().__call__(method, url, **kwargs)

        sequenced = Sequenced(transport.routes)
        credentials = CredentialStore(tmp_path, tenant_id="t1")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=sequenced)
        manager.configure_graph(graph_mod.GraphConfig(client_id=CLIENT_ID), user_id="admin")
        manager.begin_login(graph_mod.PROVIDER)

        assert manager.finish_device_login(graph_mod.PROVIDER, user_id="admin") is None
        connection = manager.finish_device_login(graph_mod.PROVIDER, user_id="admin")
        assert connection is not None
        assert connection.status == "connected"
        assert connection.connected_by == "admin"
        assert connection.granted_scopes == ["Mail.Read", "User.Read", "offline_access"]
        assert "s@example.com" in connection.account_label

    def test_an_expired_device_code_says_so(self, tmp_path):
        transport = self._transport().route(
            "POST", GRAPH_TOKEN_PATH, {"error": "expired_token"}, status=400
        )
        credentials = CredentialStore(tmp_path, tenant_id="t1")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
        manager.configure_graph(graph_mod.GraphConfig(client_id=CLIENT_ID), user_id="admin")
        manager.begin_login(graph_mod.PROVIDER)
        with pytest.raises(OAuthError) as exc:
            manager.finish_device_login(graph_mod.PROVIDER, user_id="admin")
        assert exc.value.code == "expired"


# ---------------------------------------------------------------------------
# Authorization code sign-in (Fortnox)
# ---------------------------------------------------------------------------


class TestAuthorizationCodeLogin:
    def _manager(self, tmp_path, transport):
        credentials = CredentialStore(tmp_path, tenant_id="t1")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
        manager.configure_fortnox(
            fortnox_mod.FortnoxConfig(
                client_id="client-abc", redirect_uri="https://brf.example/oauth/fortnox"
            ),
            client_secret="shhh",
            user_id="admin",
        )
        return manager, credentials

    def test_the_authorize_url_carries_state_and_the_required_parameters(self, tmp_path):
        manager, _ = self._manager(tmp_path, StubTransport())
        pending = manager.begin_login(fortnox_mod.PROVIDER)
        query = parse_qs(urlsplit(pending.authorize_url).query)
        assert urlsplit(pending.authorize_url).hostname == "apps.fortnox.se"
        assert query["response_type"] == ["code"]
        assert query["access_type"] == ["offline"]
        assert query["account_type"] == ["service"]
        assert query["scope"] == ["supplierinvoice companyinformation"]
        assert query["state"] and query["state"][0] == pending.state

    def test_a_mismatched_state_is_refused(self, tmp_path):
        manager, _ = self._manager(tmp_path, StubTransport())
        manager.begin_login(fortnox_mod.PROVIDER)
        with pytest.raises(OAuthError) as exc:
            manager.complete_code_login(
                fortnox_mod.PROVIDER, code="c", state="not-the-state", user_id="admin"
            )
        assert exc.value.code == "state_mismatch"

    def test_the_token_request_uses_basic_auth_and_never_puts_the_secret_in_the_body(
        self, tmp_path
    ):
        transport = (
            StubTransport()
            .route(
                "POST",
                fortnox_mod.TOKEN_PATH,
                {
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_in": 3600,
                    "scope": "supplierinvoice companyinformation",
                },
            )
            .route("GET", "/3/companyinformation", {"CompanyInformation": {"CompanyName": "Brf X", "OrganizationNumber": "769621-4455"}})
        )
        manager, credentials = self._manager(tmp_path, transport)
        pending = manager.begin_login(fortnox_mod.PROVIDER)
        connection = manager.complete_code_login(
            fortnox_mod.PROVIDER, code="the-code", state=pending.state, user_id="admin"
        )
        assert connection.status == "connected"
        assert connection.account_label == "Brf X (769621-4455)"

        post = next(r for r in transport.requests if r["method"] == "POST")
        assert post["headers"]["Authorization"].startswith("Basic ")
        assert "client_secret" not in post["body"]
        assert post["body"]["grant_type"] == ["authorization_code"]
        assert post["body"]["redirect_uri"] == ["https://brf.example/oauth/fortnox"]

    def test_a_refused_code_is_reported_as_a_refused_code(self, tmp_path):
        transport = StubTransport().route(
            "POST",
            fortnox_mod.TOKEN_PATH,
            {"error": "invalid_grant", "error_description": "Code expired"},
            status=400,
        )
        manager, _ = self._manager(tmp_path, transport)
        pending = manager.begin_login(fortnox_mod.PROVIDER)
        with pytest.raises(OAuthError) as exc:
            manager.complete_code_login(
                fortnox_mod.PROVIDER, code="stale", state=pending.state, user_id="admin"
            )
        assert exc.value.code == "code_rejected"
        assert "Code expired" in exc.value.message


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_a_rotated_refresh_token_is_persisted(self, tmp_path):
        transport = StubTransport().route(
            "POST",
            GRAPH_TOKEN_PATH,
            {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600},
        )
        manager = graph_connected(tmp_path, transport=transport)
        manager.credentials.write_secrets(
            graph_mod.PROVIDER,
            Secrets(access_token="at-1", refresh_token="rt-1", access_expires_epoch=0),
        )
        assert manager.access_token(graph_mod.PROVIDER) == "at-2"
        stored = manager.credentials.read_secrets(graph_mod.PROVIDER)
        assert stored.refresh_token == "rt-2", "den roterade refresh-token skrevs inte"
        assert stored.access_expires_epoch > time.time()

    def test_a_provider_that_does_not_rotate_keeps_the_token_we_hold(self, tmp_path):
        transport = StubTransport().route(
            "POST", GRAPH_TOKEN_PATH, {"access_token": "at-2", "expires_in": 3600}
        )
        manager = graph_connected(tmp_path, transport=transport)
        manager.credentials.write_secrets(
            graph_mod.PROVIDER,
            Secrets(access_token="at-1", refresh_token="rt-1", access_expires_epoch=0),
        )
        manager.access_token(graph_mod.PROVIDER)
        assert manager.credentials.read_secrets(graph_mod.PROVIDER).refresh_token == "rt-1"

    def test_a_refused_refresh_marks_the_connection_and_tells_the_operator(self, tmp_path):
        transport = StubTransport().route(
            "POST",
            GRAPH_TOKEN_PATH,
            {"error": "invalid_grant", "error_description": "AADSTS50173"},
            status=400,
        )
        manager = graph_connected(tmp_path, transport=transport)
        manager.credentials.write_secrets(
            graph_mod.PROVIDER,
            Secrets(access_token="at-1", refresh_token="rt-1", access_expires_epoch=0),
        )
        with pytest.raises(NotConnected):
            manager.access_token(graph_mod.PROVIDER)
        connection = manager.credentials.get_connection(graph_mod.PROVIDER)
        assert connection.status == "expired"
        assert "Anslut igen" in (connection.last_error or "")


# ---------------------------------------------------------------------------
# The Graph adapter
# ---------------------------------------------------------------------------


class TestGraphAdapter:
    def test_listing_asks_for_headers_only_and_never_a_body(self, tmp_path):
        transport = StubTransport().route(
            "GET",
            "/v1.0/me/mailFolders/inbox/messages",
            {
                "value": [
                    {
                        "id": "AAA",
                        "subject": "Faktura",
                        "from": {"emailAddress": {"address": "F@Ex.example", "name": "Faktura"}},
                        "receivedDateTime": "2026-02-03T08:00:00Z",
                        "hasAttachments": True,
                        "internetMessageId": "<a@b>",
                        "bodyPreview": "Hej",
                    },
                    {"id": "BBB", "subject": "Utan bilaga", "hasAttachments": False},
                ]
            },
        )
        manager = graph_connected(tmp_path, transport=transport)
        rows = manager.graph_adapter().list_messages(limit=10)
        assert [r.id for r in rows] == ["AAA"], "meddelanden utan bilagor filtreras bort"
        assert rows[0].from_address == "f@ex.example"

        select = transport.requests[-1]["query"]["$select"][0]
        assert "body" not in select.replace("bodyPreview", "")
        assert transport.methods == {"GET"}

    def test_the_mime_fetch_is_the_message_as_it_stands(self, tmp_path):
        raw = (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()
        transport = StubTransport().route("GET", "/v1.0/me/messages/AAA/$value", raw)
        manager = graph_connected(tmp_path, transport=transport)
        assert manager.graph_adapter().get_message_mime("AAA") == raw
        assert transport.requests[-1]["headers"]["Accept"] == "*/*"
        assert transport.requests[-1]["headers"]["Authorization"] == "Bearer access-1"

    def test_a_shared_mailbox_reads_under_users_not_me(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/v1.0/users/styrelsen@brf.example/mailFolders/inbox/messages", {"value": []}
        )
        credentials = CredentialStore(tmp_path, tenant_id="t1")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
        manager.configure_graph(
            graph_mod.GraphConfig(client_id=CLIENT_ID, mailbox="styrelsen@brf.example"),
            user_id="admin",
        )
        credentials.write_secrets(
            graph_mod.PROVIDER,
            Secrets(access_token="a", refresh_token="r", access_expires_epoch=time.time() + 99),
        )
        manager.graph_adapter().list_messages()
        assert transport.requests[-1]["path"].startswith("/v1.0/users/styrelsen@brf.example")

    def test_a_folder_that_is_neither_well_known_nor_an_id_is_refused(self):
        with pytest.raises(graph_mod.GraphConfigError):
            graph_mod.GraphConfig(client_id=CLIENT_ID, folder="../../etc").validated()

    def test_nothing_in_the_adapter_can_change_the_mailbox(self):
        """No method whose name would move, mark, reply or delete."""
        from app.integrations.protocols import FORBIDDEN_METHOD_STEMS

        for name in dir(graph_mod.GraphMailAdapter):
            if name.startswith("_"):
                continue
            assert name.split("_", 1)[0] not in FORBIDDEN_METHOD_STEMS, name


# ---------------------------------------------------------------------------
# The Fortnox adapter
# ---------------------------------------------------------------------------


FORTNOX_INVOICE = {
    "GivenNumber": "114",
    "InvoiceNumber": "2026-114",
    "SupplierName": "Snösvängen Entreprenad AB",
    "SupplierNumber": "S042",
    "InvoiceDate": "2026-02-03",
    "DueDate": "2026-03-05",
    "Currency": "SEK",
    "Total": "6250.00",
    "VAT": "1250.00",
    "Booked": True,
    "Cancelled": False,
    "SupplierInvoiceRows": [
        {
            "Description": "Maskinell snöröjning med traktor",
            "Quantity": "4",
            "Price": "1250.00",
            "Debit": "5000.00",
            "Account": "6110",
        }
    ],
}


def fortnox_connected(tmp_path, transport) -> ConnectionManager:
    credentials = CredentialStore(tmp_path, tenant_id="gjutformen-12")
    manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
    manager.configure_fortnox(
        fortnox_mod.FortnoxConfig(client_id="c", redirect_uri="https://x.example/cb"),
        client_secret="s",
        user_id="admin",
    )
    credentials.write_secrets(
        fortnox_mod.PROVIDER,
        Secrets(
            access_token="fx-access",
            refresh_token="fx-refresh",
            client_secret="s",
            access_expires_epoch=time.time() + 3600,
        ),
    )
    return manager


class TestFortnoxAdapter:
    def test_a_supplier_invoice_maps_onto_the_domain_snapshot(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE}
        )
        manager = fortnox_connected(tmp_path, transport)
        snapshot = manager.fortnox_adapter().get_invoice("gjutformen-12", "114")
        assert snapshot.supplier_name == "Snösvängen Entreprenad AB"
        assert str(snapshot.total_amount) == "6250.00"
        assert str(snapshot.vat_amount) == "1250.00"
        assert snapshot.tenant_id == "gjutformen-12"
        assert snapshot.adapter == "fortnox"
        assert len(snapshot.lines) == 1
        assert str(snapshot.lines[0].unit_price) == "1250.00"
        # Fortnox supplier invoices have no period field, and the mapping does
        # not invent one.
        assert snapshot.period_start is None and snapshot.period_end is None
        # An amount is a Decimal that serialises as a string, never a float.
        assert snapshot.model_dump(mode="json")["total_amount"] == "6250.00"

    def test_the_mapping_preview_names_the_source_field_for_every_value(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE}
        )
        manager = fortnox_connected(tmp_path, transport)
        preview = manager.fortnox_adapter().mapping_preview("gjutformen-12", "114")
        by_target = {row["target"]: row for row in preview["fields"]}
        assert by_target["total_amount"]["sourceField"] == "Total"
        assert by_target["supplier_name"]["value"] == "Snösvängen Entreprenad AB"
        assert by_target["period_start"]["matched"] is False
        assert "periodgranskning" in by_target["period_start"]["note"]
        # A row amount comes from Debit when Total is absent, and the preview
        # says which.
        assert preview["rows"][0][-1]["sourceField"] == "Debit"
        assert preview["observedNotChanged"]["Booked"] is True

    def test_the_supplier_register_is_only_read_when_it_was_opted_into(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE}
        )
        manager = fortnox_connected(tmp_path, transport)
        manager.fortnox_adapter().get_invoice("gjutformen-12", "114")
        assert not any(r["path"].startswith("/3/suppliers") for r in transport.requests)

    def test_an_opted_in_register_read_anchors_on_the_organisation_number(self, tmp_path):
        transport = (
            StubTransport()
            .route("GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE})
            .route(
                "GET",
                "/3/suppliers/S042",
                {"Supplier": {"OrganisationNumber": "556812-3344", "Name": "Snösvängen"}},
            )
        )
        credentials = CredentialStore(tmp_path, tenant_id="gjutformen-12")
        manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
        manager.configure_fortnox(
            fortnox_mod.FortnoxConfig(
                client_id="c", redirect_uri="https://x.example/cb", read_supplier_register=True
            ),
            client_secret="s",
            user_id="admin",
        )
        credentials.write_secrets(
            fortnox_mod.PROVIDER,
            Secrets(access_token="a", refresh_token="r", client_secret="s", access_expires_epoch=time.time() + 99),
        )
        snapshot = manager.fortnox_adapter().get_invoice("gjutformen-12", "114")
        assert "556812-3344" in (snapshot.supplier_ref or "")

    def test_every_fortnox_request_is_a_get(self, tmp_path):
        transport = (
            StubTransport()
            .route("GET", "/3/supplierinvoices", {"SupplierInvoices": [FORTNOX_INVOICE]})
            .route("GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE})
        )
        manager = fortnox_connected(tmp_path, transport)
        adapter = manager.fortnox_adapter()
        adapter.list_invoices("gjutformen-12")
        adapter.get_invoice("gjutformen-12", "114")
        assert transport.methods == {"GET"}

    def test_an_unknown_document_number_is_a_lookup_error(self, tmp_path):
        manager = fortnox_connected(tmp_path, StubTransport())
        with pytest.raises(LookupError):
            manager.fortnox_adapter().get_invoice("gjutformen-12", "inte-ett-nummer")


# ---------------------------------------------------------------------------
# Where the secrets are, and are not
# ---------------------------------------------------------------------------


class TestSecretHandling:
    def test_the_connection_record_carries_no_secret(self, tmp_path):
        manager = graph_connected(tmp_path, transport=StubTransport())
        blob = json.dumps(manager.status(), ensure_ascii=False)
        for secret in ("access-1", "refresh-1"):
            assert secret not in blob

    def test_the_secret_file_is_0600_inside_a_0700_directory(self, tmp_path):
        manager = graph_connected(tmp_path, transport=StubTransport())
        path = tmp_path / "credentials" / "microsoft-graph.json"
        assert path.exists()
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert oct(path.parent.stat().st_mode & 0o777) == "0o700"

    def test_disconnect_removes_the_secret_and_keeps_the_record(self, tmp_path):
        manager = graph_connected(tmp_path, transport=StubTransport())
        assert manager.disconnect(graph_mod.PROVIDER) is True
        assert manager.credentials.read_secrets(graph_mod.PROVIDER) is None
        connection = manager.credentials.get_connection(graph_mod.PROVIDER)
        assert connection.status == "revoked"
        assert connection.configured_by == "admin"

    def test_pointing_at_another_mailbox_invalidates_the_sign_in(self, tmp_path):
        manager = graph_connected(tmp_path, transport=StubTransport())
        manager.configure_graph(
            graph_mod.GraphConfig(client_id=CLIENT_ID, mailbox="annan@brf.example"),
            user_id="admin",
        )
        assert manager.credentials.read_secrets(graph_mod.PROVIDER) is None
        assert manager.credentials.get_connection(graph_mod.PROVIDER).status == "configured"

    def test_a_backup_contains_the_connection_and_not_the_token(self, tmp_path):
        from app.desktop import create_backup

        data_root = tmp_path / "data"
        integrations = data_root / "tenants" / "t1" / "integrations"
        integrations.mkdir(parents=True)
        manager = graph_connected(integrations, transport=StubTransport())
        assert (integrations / "credentials" / "microsoft-graph.json").exists()

        result = create_backup(data_root, tmp_path / "backups")
        archive_path = tmp_path / "backups" / result["name"]
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            blob = b"".join(archive.read(n) for n in names)
            manifest = json.loads(archive.read("brfv2-backup.json"))
        assert not any("credentials/" in n for n in names), names
        assert b"refresh-1" not in blob
        assert any(n.endswith("connections.json") for n in names)
        assert manifest["excludedCredentialFiles"] == 1

    def test_one_tenants_credentials_are_invisible_to_another(self, tmp_path):
        a = CredentialStore(tmp_path / "a", tenant_id="a")
        b = CredentialStore(tmp_path / "b", tenant_id="b")
        a.write_secrets("fortnox", Secrets(access_token="a-token"))
        assert b.read_secrets("fortnox") is None
        assert b.list_connections() == []

    def test_a_connection_file_from_another_tenant_is_refused(self, tmp_path):
        from app.integrations.credentials import CONNECTIONS_FILE, ConnectionError_

        (tmp_path / CONNECTIONS_FILE).write_text(
            json.dumps([{"provider": "fortnox", "tenant_id": "someone-else"}]),
            encoding="utf-8",
        )
        store = CredentialStore(tmp_path, tenant_id="mine")
        with pytest.raises(ConnectionError_):
            store.list_connections()

    def test_using_an_unconfigured_provider_says_what_to_do(self, tmp_path):
        manager = ConnectionManager(
            CredentialStore(tmp_path, tenant_id="t1"), pending=PendingLogins()
        )
        with pytest.raises(NotConnected) as exc:
            manager.access_token("fortnox")
        assert "konfigurerad" in str(exc.value)
