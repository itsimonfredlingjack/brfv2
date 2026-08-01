"""The live-integration routes over real HTTP: who may do what, and to whose data.

The unit suite proves the OAuth client and the adapters behave. This one proves
the thing that protects an association once they are wired into the product:

* configuring and connecting an external system is an **admin** act, and a
  member gets 403 rather than a quiet success;
* a valid session for Brf B reaches nothing of Brf A's — not the connection,
  not the mailbox, not the aliases — and gets 404 rather than 403, so a tenant
  id stays unprobeable;
* no route ever returns an access token, a refresh token or a client secret;
* one tenant's sign-in is not another tenant's sign-in, even mid-flow.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

MAIL = Path(__file__).resolve().parent.parent / "fixtures" / "mail"

GRAPH_DEVICE_PATH = "/consumers/oauth2/v2.0/devicecode"
GRAPH_TOKEN_PATH = "/consumers/oauth2/v2.0/token"
CLIENT_ID = "11111111-2222-3333-4444-555555555555"

GRAPH_CONFIG = {"client_id": CLIENT_ID, "authority": "consumers", "folder": "inbox"}


def configure_graph(env, brf: str, headers: dict, **overrides):
    body = {**GRAPH_CONFIG, **overrides}
    return env.client.put(
        f"/api/brf/{brf}/integrations/connections/microsoft-graph", json=body, headers=headers
    )


def connect_graph(env, brf: str, headers: dict, *, access_token: str = "at-1") -> None:
    """Configure and complete a device-code sign-in against the stub."""
    env.transport.route(
        "POST",
        GRAPH_DEVICE_PATH,
        {
            "device_code": "DEV",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
            "interval": 0,
        },
    )
    env.transport.route(
        "POST",
        GRAPH_TOKEN_PATH,
        {
            "access_token": access_token,
            "refresh_token": "rt-1",
            "expires_in": 3600,
            "scope": "Mail.Read User.Read offline_access",
        },
    )
    env.transport.route("GET", "/v1.0/me", {"displayName": "Simon", "mail": "s@example.com"})
    assert configure_graph(env, brf, headers).status_code == 200
    assert (
        env.client.post(
            f"/api/brf/{brf}/integrations/connections/microsoft-graph/login", headers=headers
        ).status_code
        == 200
    )
    reply = env.client.post(
        f"/api/brf/{brf}/integrations/connections/microsoft-graph/login/poll", headers=headers
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "connected", reply.text


class TestWhoMayConnect:
    def test_a_member_may_read_the_status_but_not_configure(self, live_integration_app):
        env = live_integration_app
        assert (
            env.client.get(
                "/api/brf/brf-a/integrations/connections", headers=env.member_a_headers
            ).status_code
            == 200
        )
        assert configure_graph(env, "brf-a", env.member_a_headers).status_code == 403

    def test_a_member_may_not_browse_the_mailbox(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        r = env.client.get(
            "/api/brf/brf-a/integrations/mailbox/messages", headers=env.member_a_headers
        )
        assert r.status_code == 403

    def test_an_unauthenticated_request_reaches_nothing(self, live_integration_app):
        env = live_integration_app
        assert env.client.get("/api/brf/brf-a/integrations/connections").status_code == 401
        assert (
            env.client.post(
                "/api/brf/brf-a/integrations/connections/microsoft-graph/login"
            ).status_code
            == 401
        )

    def test_an_invalid_configuration_is_refused_with_a_readable_reason(
        self, live_integration_app
    ):
        env = live_integration_app
        r = configure_graph(env, "brf-a", env.admin_a_headers, client_id="inte-ett-guid")
        assert r.status_code == 422
        assert "GUID" in r.json()["detail"]

    def test_fortnox_without_a_client_secret_is_refused(self, live_integration_app):
        env = live_integration_app
        r = env.client.put(
            "/api/brf/brf-a/integrations/connections/fortnox",
            json={"client_id": "abc", "redirect_uri": "https://brf.example/cb"},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert "klienthemlighet" in r.json()["detail"]


class TestTenantIsolation:
    def test_bs_admin_cannot_configure_as(self, live_integration_app):
        env = live_integration_app
        assert configure_graph(env, "brf-a", env.admin_b_headers).status_code == 404

    def test_bs_admin_cannot_see_as_connection(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        assert (
            env.client.get(
                "/api/brf/brf-a/integrations/connections", headers=env.admin_b_headers
            ).status_code
            == 404
        )
        own = env.client.get(
            "/api/brf/brf-b/integrations/connections", headers=env.admin_b_headers
        ).json()
        assert own["microsoft-graph"]["configured"] is False
        assert own["microsoft-graph"]["connection"] is None

    def test_as_connection_does_not_let_b_read_a_mailbox(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        # B has no connection of its own; the honest answer is 409, and it is
        # about B's own tenant — never a read that borrows A's credential.
        r = env.client.get(
            "/api/brf/brf-b/integrations/mailbox/messages", headers=env.admin_b_headers
        )
        assert r.status_code == 409
        assert "konfigurerad" in r.json()["detail"]

    def test_a_pending_sign_in_belongs_to_one_tenant(self, live_integration_app):
        env = live_integration_app
        env.transport.route(
            "POST",
            GRAPH_DEVICE_PATH,
            {"device_code": "DEV", "user_code": "AAAA", "expires_in": 900, "interval": 0},
        )
        assert configure_graph(env, "brf-a", env.admin_a_headers).status_code == 200
        assert configure_graph(env, "brf-b", env.admin_b_headers).status_code == 200
        env.client.post(
            "/api/brf/brf-a/integrations/connections/microsoft-graph/login",
            headers=env.admin_a_headers,
        )
        status_b = env.client.get(
            "/api/brf/brf-b/integrations/connections", headers=env.admin_b_headers
        ).json()
        assert status_b["microsoft-graph"]["pendingLogin"] is None
        # And B cannot finish A's sign-in.
        r = env.client.post(
            "/api/brf/brf-b/integrations/connections/microsoft-graph/login/poll",
            headers=env.admin_b_headers,
        )
        assert r.status_code == 409

    def test_aliases_are_per_tenant(self, live_integration_app):
        env = live_integration_app
        created = env.client.post(
            "/api/brf/brf-a/integrations/supplier-aliases",
            json={"invoice_name": "Snösvängen AB", "document_name": "Snösvängen Entreprenad AB"},
            headers=env.admin_a_headers,
        )
        assert created.status_code == 200, created.text
        assert (
            env.client.get(
                "/api/brf/brf-b/integrations/supplier-aliases", headers=env.admin_b_headers
            ).json()
            == []
        )
        assert (
            env.client.get(
                "/api/brf/brf-a/integrations/supplier-aliases", headers=env.admin_b_headers
            ).status_code
            == 404
        )

    def test_deleting_the_tenant_takes_its_credentials(self, live_integration_app, tmp_path):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        secret = tmp_path / "tenants" / "brf-a" / "integrations" / "credentials" / "microsoft-graph.json"
        assert secret.exists()
        assert (
            env.client.delete("/api/brf/brf-a", headers=env.admin_a_headers).status_code == 200
        )
        assert not secret.exists()
        assert not secret.parent.parent.exists()


class TestNoSecretEverLeaves:
    def test_no_route_returns_a_token(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers, access_token="TOP-SECRET-TOKEN")
        for path in (
            "/api/brf/brf-a/integrations/connections",
            "/api/brf/brf-a/integrations/format",
        ):
            body = env.client.get(path, headers=env.admin_a_headers).text
            assert "TOP-SECRET-TOKEN" not in body
            assert "rt-1" not in body

    def test_the_status_shows_the_account_the_scopes_and_the_hosts(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        status = env.client.get(
            "/api/brf/brf-a/integrations/connections", headers=env.admin_a_headers
        ).json()["microsoft-graph"]
        assert status["connection"]["status"] == "connected"
        assert status["connection"]["account_label"] == "s@example.com"
        assert status["connection"]["connected_by"]
        # The expiry is the token's, not the moment it was stored.
        assert status["connection"]["access_expires_at"] > status["connection"]["connected_at"]
        assert status["scopes"] == ["offline_access", "User.Read", "Mail.Read"]
        assert status["hosts"] == ["graph.microsoft.com", "login.microsoftonline.com"]

    def test_a_fortnox_client_secret_is_never_echoed(self, live_integration_app):
        env = live_integration_app
        r = env.client.put(
            "/api/brf/brf-a/integrations/connections/fortnox",
            json={
                "client_id": "abc",
                "client_secret": "THE-CLIENT-SECRET",
                "redirect_uri": "https://brf.example/cb",
            },
            headers=env.admin_a_headers,
        )
        assert r.status_code == 200, r.text
        assert "THE-CLIENT-SECRET" not in r.text
        status = env.client.get(
            "/api/brf/brf-a/integrations/connections", headers=env.admin_a_headers
        ).text
        assert "THE-CLIENT-SECRET" not in status


class TestMailboxImport:
    def test_a_chosen_message_is_imported_through_the_ordinary_path(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        raw = (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()
        env.transport.route(
            "GET",
            "/v1.0/me/mailFolders/inbox/messages",
            {
                "value": [
                    {
                        "id": "AAA",
                        "subject": "Faktura",
                        "from": {"emailAddress": {"address": "f@ex.example", "name": "F"}},
                        "receivedDateTime": "2026-02-03T08:00:00Z",
                        "hasAttachments": True,
                        "internetMessageId": "<a@b>",
                    }
                ]
            },
        )
        env.transport.route("GET", "/v1.0/me/messages/AAA/$value", raw)

        listed = env.client.get(
            "/api/brf/brf-a/integrations/mailbox/messages", headers=env.admin_a_headers
        ).json()
        assert [m["id"] for m in listed["messages"]] == ["AAA"]

        imported = env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/AAA/import",
            headers=env.admin_a_headers,
        )
        assert imported.status_code == 200, imported.text
        event = imported.json()
        import hashlib

        assert event["content_sha256"] == hashlib.sha256(raw).hexdigest()
        assert event["provenance"]["method"] == "graph-mailbox-import"
        assert event["provenance"]["adapter"] == "microsoft-graph"
        assert event["attachments"] and event["attachments"][0]["ingested"] is True
        assert event["attachments"][0]["archived"] is False

    def test_the_same_message_twice_is_one_event(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        raw = (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()
        env.transport.route("GET", "/v1.0/me/messages/AAA/$value", raw)
        first = env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/AAA/import",
            headers=env.admin_a_headers,
        )
        again = env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/AAA/import",
            headers=env.admin_a_headers,
        )
        assert again.status_code == 409
        assert again.headers["X-Existing-Source-Event"] == first.json()["id"]

    def test_a_message_outside_the_format_is_refused_atomically(self, live_integration_app):
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        env.transport.route(
            "GET",
            "/v1.0/me/messages/BAD/$value",
            (MAIL / "underlag-i-kalkylblad.eml").read_bytes(),
        )
        r = env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/BAD/import",
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert r.headers["X-Import-Rejection"] == "unsupported_attachment"
        assert (
            env.client.get(
                "/api/brf/brf-a/integrations/source-events", headers=env.admin_a_headers
            ).json()
            == []
        )

    def test_importing_a_message_changes_nothing_in_the_mailbox(self, live_integration_app):
        """No PATCH to mark read, no move, no delete — and no way to make one."""
        env = live_integration_app
        connect_graph(env, "brf-a", env.admin_a_headers)
        env.transport.route(
            "GET",
            "/v1.0/me/messages/AAA/$value",
            (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
        )
        env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/AAA/import",
            headers=env.admin_a_headers,
        )
        graph_calls = [r for r in env.transport.requests if r["host"] == "graph.microsoft.com"]
        assert graph_calls, "inga anrop mot Graph gjordes"
        assert {r["method"] for r in graph_calls} == {"GET"}


class TestArchiveAdoptionOverHttp:
    def _import(self, env):
        connect_graph(env, "brf-a", env.admin_a_headers)
        env.transport.route(
            "GET",
            "/v1.0/me/messages/AAA/$value",
            (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
        )
        return env.client.post(
            "/api/brf/brf-a/integrations/mailbox/messages/AAA/import",
            headers=env.admin_a_headers,
        ).json()

    def test_adoption_requires_a_note_and_records_who(self, live_integration_app):
        env = live_integration_app
        event = self._import(env)
        path = (
            f"/api/brf/brf-a/integrations/source-events/{event['id']}"
            f"/attachments/{event['attachments'][0]['id']}/archive"
        )
        assert env.client.post(path, json={"note": ""}, headers=env.admin_a_headers).status_code == 422
        ok = env.client.post(
            path, json={"note": "Föreningens exemplar."}, headers=env.admin_a_headers
        )
        assert ok.status_code == 200, ok.text
        attachment = ok.json()["attachments"][0]
        assert attachment["archived"] is True
        assert attachment["archive_note"] == "Föreningens exemplar."
        assert attachment["archived_by"]

        undone = env.client.delete(path, headers=env.admin_a_headers)
        assert undone.status_code == 200
        assert undone.json()["attachments"][0]["archived"] is False

    def test_a_member_may_not_adopt(self, live_integration_app):
        env = live_integration_app
        event = self._import(env)
        path = (
            f"/api/brf/brf-a/integrations/source-events/{event['id']}"
            f"/attachments/{event['attachments'][0]['id']}/archive"
        )
        r = env.client.post(path, json={"note": "x"}, headers=env.member_a_headers)
        assert r.status_code == 403


class TestLiveInvoiceSource:
    def test_the_fixture_source_still_works_with_nothing_connected(self, live_integration_app):
        env = live_integration_app
        r = env.client.get(
            "/api/brf/brf-a/integrations/available-invoices", headers=env.admin_a_headers
        )
        assert r.status_code == 200
        assert r.json()["source"] == "fixture"

    def test_an_unknown_source_is_refused(self, live_integration_app):
        env = live_integration_app
        r = env.client.get(
            "/api/brf/brf-a/integrations/available-invoices?source=sap",
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422

    def test_the_live_source_needs_a_connection(self, live_integration_app):
        env = live_integration_app
        for reply in (
            env.client.get(
                "/api/brf/brf-a/integrations/available-invoices?source=fortnox",
                headers=env.admin_a_headers,
            ),
            env.client.post(
                "/api/brf/brf-a/integrations/invoices",
                json={"external_ref": "114", "source": "fortnox"},
                headers=env.admin_a_headers,
            ),
            env.client.get(
                "/api/brf/brf-a/integrations/invoices/mapping-preview?external_ref=114",
                headers=env.admin_a_headers,
            ),
        ):
            # 409, not 500: "nobody has connected anything" is a state of the
            # installation, not a fault in the request.
            assert reply.status_code == 409, reply.text

    def test_a_live_invoice_is_read_and_previewed(self, live_integration_app):
        env = live_integration_app
        from tests.test_integrations_live import FORTNOX_INVOICE

        env.transport.route(
            "POST",
            "/oauth-v1/token",
            {
                "access_token": "fx",
                "refresh_token": "fr",
                "expires_in": 3600,
                "scope": "supplierinvoice companyinformation",
            },
        )
        env.transport.route(
            "GET",
            "/3/companyinformation",
            {"CompanyInformation": {"CompanyName": "Brf A", "OrganizationNumber": "1"}},
        )
        env.transport.route(
            "GET", "/3/supplierinvoices", {"SupplierInvoices": [FORTNOX_INVOICE]}
        )
        env.transport.route(
            "GET", "/3/supplierinvoices/114", {"SupplierInvoice": FORTNOX_INVOICE}
        )

        assert (
            env.client.put(
                "/api/brf/brf-a/integrations/connections/fortnox",
                json={
                    "client_id": "abc",
                    "client_secret": "s",
                    "redirect_uri": "https://brf.example/cb",
                },
                headers=env.admin_a_headers,
            ).status_code
            == 200
        )
        begun = env.client.post(
            "/api/brf/brf-a/integrations/connections/fortnox/login", headers=env.admin_a_headers
        ).json()
        # An operator who pastes the whole redirect address is understood.
        completed = env.client.post(
            "/api/brf/brf-a/integrations/connections/fortnox/login/complete",
            json={
                "code": f"https://brf.example/cb?code=THE-CODE&state={begun['authorizeUrl'].split('state=')[1].split('&')[0]}"
            },
            headers=env.admin_a_headers,
        )
        assert completed.status_code == 200, completed.text

        listed = env.client.get(
            "/api/brf/brf-a/integrations/available-invoices?source=fortnox",
            headers=env.admin_a_headers,
        ).json()
        assert listed["adapter"] == "fortnox"
        assert listed["invoices"][0]["external_ref"] == "114"
        assert listed["invoices"][0]["booked"] is True

        preview = env.client.get(
            "/api/brf/brf-a/integrations/invoices/mapping-preview?external_ref=114",
            headers=env.admin_a_headers,
        ).json()
        assert preview["externalRef"] == "114"
        assert any(f["target"] == "total_amount" and f["sourceField"] == "Total" for f in preview["fields"])

        stored = env.client.post(
            "/api/brf/brf-a/integrations/invoices",
            json={"external_ref": "114", "source": "fortnox"},
            headers=env.admin_a_headers,
        )
        assert stored.status_code == 200, stored.text
        assert stored.json()["adapter"] == "fortnox"
        assert stored.json()["total_amount"] == "6250.00"

        # Everything that touched Fortnox was a GET, except the token POST.
        fortnox_calls = [r for r in env.transport.requests if r["host"] == "api.fortnox.se"]
        assert {r["method"] for r in fortnox_calls} == {"GET"}
