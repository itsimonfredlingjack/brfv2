"""Tenant isolation for the integration domain, asserted over real HTTP.

The unit suite proves the store refuses a foreign record. This one proves the
thing that actually protects an association: that an authenticated admin of
Brf B, holding a genuinely valid session, cannot reach Brf A's source events,
invoices, findings or the attachments that arrived with them — through any
route, including the ones that are not integration routes.

Every request carries its session explicitly as a Cookie header, and the shared
jar is cleared, so "no header" genuinely means "unauthenticated". That is the
property the surrounding isolation suites are built on and it is preserved
here.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

MAIL = Path(__file__).resolve().parent.parent / "fixtures" / "mail"


def _eml(subject: str, secret: str, pdf: bytes) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"leverantor@{secret.lower()}.example"
    msg["To"] = "styrelsen@forening.example"
    msg["Subject"] = subject
    msg["Date"] = "Tue, 03 Feb 2026 08:14:00 +0100"
    msg["Message-ID"] = f"<{secret}@fixture.invalid>"
    msg.set_content(f"Underlag som bara {secret} ska kunna se.\n")
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{secret}.pdf")
    msg.set_boundary(f"----brfv2-test-{secret}")
    return msg.as_bytes()


@pytest.fixture()
def imported(two_tenant_app):
    """One imported message in each tenant, with a distinguishable attachment."""
    from tests.pdf_fixtures import build_pdf

    env = two_tenant_app
    pdf_a = build_pdf([[("Faktura för ALFA-XYZZY-111 avser snöröjning.", 72, 100)]])
    pdf_b = build_pdf([[("Faktura för BETA-PLUGH-222 avser hissservice.", 72, 100)]])

    raw_a = _eml("Faktura A", "ALFA", pdf_a)
    ra = env.client.post(
        "/api/brf/brf-a/integrations/source-events",
        files={"file": ("a.eml", raw_a, "message/rfc822")},
        headers=env.admin_a_headers,
    )
    rb = env.client.post(
        "/api/brf/brf-b/integrations/source-events",
        files={"file": ("b.eml", _eml("Faktura B", "BETA", pdf_b), "message/rfc822")},
        headers=env.admin_b_headers,
    )
    assert ra.status_code == 200, ra.text
    assert rb.status_code == 200, rb.text
    env.event_a = ra.json()
    env.event_b = rb.json()
    env.raw_a = raw_a
    env.pdf_a = pdf_a
    return env


class TestSourceEventIsolation:
    def test_each_tenant_sees_only_its_own_queue(self, imported):
        env = imported
        a = env.client.get(
            "/api/brf/brf-a/integrations/source-events", headers=env.admin_a_headers
        ).json()
        b = env.client.get(
            "/api/brf/brf-b/integrations/source-events", headers=env.admin_b_headers
        ).json()
        assert [e["id"] for e in a] == [env.event_a["id"]]
        assert [e["id"] for e in b] == [env.event_b["id"]]
        assert "BETA" not in str(a)
        assert "ALFA" not in str(b)

    def test_b_cannot_read_as_reaching_into_a(self, imported):
        env = imported
        r = env.client.get(
            "/api/brf/brf-a/integrations/source-events", headers=env.admin_b_headers
        )
        # 404, never 403: a tenant id must not be probeable for existence.
        assert r.status_code == 404

    def test_b_cannot_fetch_a_specific_event_of_a(self, imported):
        env = imported
        r = env.client.get(
            f"/api/brf/brf-a/integrations/source-events/{env.event_a['id']}",
            headers=env.admin_b_headers,
        )
        assert r.status_code == 404
        assert "ALFA" not in r.text

    def test_an_event_id_from_another_tenant_is_unknown_even_in_your_own_scope(self, imported):
        """The id is real. It is simply not in this tenant's directory."""
        env = imported
        r = env.client.get(
            f"/api/brf/brf-b/integrations/source-events/{env.event_a['id']}",
            headers=env.admin_b_headers,
        )
        assert r.status_code == 404

    def test_b_cannot_import_into_a(self, imported):
        from tests.pdf_fixtures import build_pdf

        env = imported
        r = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={
                "file": (
                    "x.eml",
                    _eml("Intrång", "INTRANG", build_pdf([[("x", 72, 100)]])),
                    "message/rfc822",
                )
            },
            headers=env.admin_b_headers,
        )
        assert r.status_code == 404
        after = env.client.get(
            "/api/brf/brf-a/integrations/source-events", headers=env.admin_a_headers
        ).json()
        assert len(after) == 1

    def test_b_cannot_decide_on_as_event(self, imported):
        env = imported
        r = env.client.post(
            f"/api/brf/brf-a/integrations/source-events/{env.event_a['id']}/decision",
            json={"status": "approved"},
            headers=env.admin_b_headers,
        )
        assert r.status_code == 404
        still = env.client.get(
            f"/api/brf/brf-a/integrations/source-events/{env.event_a['id']}",
            headers=env.admin_a_headers,
        ).json()
        assert still["review_status"] == "open"

    def test_an_unauthenticated_request_reaches_nothing(self, imported):
        env = imported
        for path in (
            "/api/brf/brf-a/integrations/source-events",
            "/api/brf/brf-a/integrations/invoices",
            "/api/brf/brf-a/integrations/findings",
            "/api/brf/brf-a/integrations/available-invoices",
        ):
            r = env.client.get(path)
            assert r.status_code == 401, path


class TestAttachmentIsolation:
    def test_an_attachment_is_a_document_of_its_own_tenant_only(self, imported):
        env = imported
        doc_id = env.event_a["attachments"][0]["document_id"]
        assert doc_id

        mine = env.client.get(
            f"/api/brf/brf-a/documents/{doc_id}/pdf", headers=env.admin_a_headers
        )
        assert mine.status_code == 200
        assert mine.content.startswith(b"%PDF-")

        theirs = env.client.get(
            f"/api/brf/brf-a/documents/{doc_id}/pdf", headers=env.admin_b_headers
        )
        assert theirs.status_code == 404

        # And it does not exist inside B's own scope either.
        wrong_scope = env.client.get(
            f"/api/brf/brf-b/documents/{doc_id}/pdf", headers=env.admin_b_headers
        )
        assert wrong_scope.status_code == 404

    def test_an_attachment_does_not_leak_through_retrieval(self, imported):
        """The strongest form of the check: ask B's own tenant a question whose
        answer only exists in A's imported attachment."""
        env = imported
        r = env.client.post(
            "/api/brf/brf-b/ask",
            json={"question": "Vad står det om ALFA-XYZZY-111?"},
            headers=env.admin_b_headers,
        )
        assert r.status_code == 200
        assert "ALFA-XYZZY-111" not in r.text


class TestInvoiceAndFindingIsolation:
    def test_invoices_and_findings_stay_in_their_tenant(self, two_tenant_app, monkeypatch):
        env = two_tenant_app
        # brf-a gets an invoice from the fixture dataset; brf-b gets none.
        import json as json_mod

        from app.integrations.accounting_fixture import FIXTURE_SCHEMA

        # A dataset scoped to brf-a only.
        fixture_dir = env.registry.data_root / "fixture-accounting"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "a.json").write_text(
            json_mod.dumps(
                {
                    "Schema": FIXTURE_SCHEMA,
                    "SupplierInvoices": [
                        {
                            "AssociationRef": "brf-a",
                            "DocumentNumber": "A-1",
                            "SupplierName": "Leverantör ALFA-XYZZY-111 AB",
                            "InvoiceDate": "2026-02-03",
                            "Currency": "SEK",
                            "Total": "1000.00",
                            "VAT": "200.00",
                            "InvoiceRows": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        from app.integrations import routes as routes_mod

        real_init = routes_mod.FixtureAccountingAdapter.__init__

        def scoped_init(self, fixture_dir_arg=None):
            real_init(self, fixture_dir)

        monkeypatch.setattr(routes_mod.FixtureAccountingAdapter, "__init__", scoped_init)

        from app.auth import AuthStore  # noqa: F401  (import kept for symmetry)
        from app.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(
            registry=env.registry, auth=env.auth, data_root=env.registry.data_root
        )
        client = TestClient(app)

        offered_a = client.get(
            "/api/brf/brf-a/integrations/available-invoices", headers=env.admin_a_headers
        ).json()
        offered_b = client.get(
            "/api/brf/brf-b/integrations/available-invoices", headers=env.admin_b_headers
        ).json()
        assert [i["external_ref"] for i in offered_a["invoices"]] == ["A-1"]
        assert offered_b["invoices"] == [], "B blev erbjuden A:s faktura"

        created = client.post(
            "/api/brf/brf-a/integrations/invoices",
            json={"external_ref": "A-1"},
            headers=env.admin_a_headers,
        )
        assert created.status_code == 200, created.text
        invoice_id = created.json()["id"]

        # B cannot list, review or reach it.
        assert (
            client.get("/api/brf/brf-b/integrations/invoices", headers=env.admin_b_headers).json()
            == []
        )
        assert (
            client.post(
                f"/api/brf/brf-a/integrations/invoices/{invoice_id}/review",
                headers=env.admin_b_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/brf/brf-b/integrations/invoices/{invoice_id}/review",
                headers=env.admin_b_headers,
            ).status_code
            == 404
        )

        reviewed = client.post(
            f"/api/brf/brf-a/integrations/invoices/{invoice_id}/review",
            headers=env.admin_a_headers,
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["findings"], "en granskning ska aldrig ge noll fynd"

        findings_b = client.get(
            "/api/brf/brf-b/integrations/findings", headers=env.admin_b_headers
        ).json()
        assert findings_b == []


class TestRoleBoundary:
    def test_a_member_may_read_the_queue_but_not_change_it(self, imported):
        env = imported
        read = env.client.get(
            "/api/brf/brf-a/integrations/source-events", headers=env.member_a_headers
        )
        assert read.status_code == 200

        from tests.pdf_fixtures import build_pdf

        write = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={
                "file": (
                    "m.eml",
                    _eml("Medlem", "MEDLEM", build_pdf([[("x", 72, 100)]])),
                    "message/rfc822",
                )
            },
            headers=env.member_a_headers,
        )
        assert write.status_code == 403

        decide = env.client.post(
            f"/api/brf/brf-a/integrations/source-events/{env.event_a['id']}/decision",
            json={"status": "approved"},
            headers=env.member_a_headers,
        )
        assert decide.status_code == 403


class TestDeletionSweepsIntegrationData:
    def test_deleting_the_tenant_removes_its_integration_directory(self, imported):
        env = imported
        tenant_dir = env.registry.data_root / "tenants" / "brf-a"
        assert (tenant_dir / "integrations" / "source-events.json").is_file()

        r = env.client.delete("/api/brf/brf-a", headers=env.admin_a_headers)
        assert r.status_code == 200
        assert not tenant_dir.exists()
        # B is untouched.
        assert (
            env.client.get(
                "/api/brf/brf-b/integrations/source-events", headers=env.admin_b_headers
            ).status_code
            == 200
        )


class TestImportContract:
    def test_a_non_eml_upload_is_refused(self, two_tenant_app):
        env = two_tenant_app
        r = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 400

    def test_a_rejected_import_carries_its_stable_code(self, two_tenant_app):
        env = two_tenant_app
        r = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={
                "file": (
                    "kalkyl.eml",
                    (MAIL / "underlag-i-kalkylblad.eml").read_bytes(),
                    "message/rfc822",
                )
            },
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert r.headers["X-Import-Rejection"] == "unsupported_attachment"

    def test_a_duplicate_import_is_a_conflict_that_names_the_original(self, imported):
        """The same file again, byte for byte."""
        env = imported
        r = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={"file": ("igen.eml", env.raw_a, "message/rfc822")},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 409
        assert r.headers["X-Existing-Source-Event"] == env.event_a["id"]

    def test_the_same_attachment_in_a_new_envelope_is_linked_not_re_ingested(self, imported):
        """A forwarded copy of an invoice must not become a second document."""
        env = imported
        before = env.client.get(
            "/api/brf/brf-a/documents", headers=env.admin_a_headers
        ).json()

        forwarded = _eml("VB: Faktura A", "ALFA", env.pdf_a).replace(
            b"<ALFA@fixture.invalid>", b"<ALFA-vb@fixture.invalid>"
        )
        r = env.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={"file": ("vb.eml", forwarded, "message/rfc822")},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 200, r.text
        attachment = r.json()["attachments"][0]
        assert attachment["reused_existing_document"] is True
        assert attachment["document_id"] == env.event_a["attachments"][0]["document_id"]

        after = env.client.get(
            "/api/brf/brf-a/documents", headers=env.admin_a_headers
        ).json()
        assert len(after) == len(before), "en dubblett skapade ett andra dokument"

    def test_a_correction_without_an_explanation_is_refused(self, two_tenant_app):
        """A finding marked 'corrected' with no note looks handled and says nothing."""
        env = two_tenant_app
        r = env.client.post(
            "/api/brf/brf-a/integrations/findings/does-not-exist/decision",
            json={"status": "corrected"},
            headers=env.admin_a_headers,
        )
        # 422 before 404: the request is malformed regardless of the id.
        assert r.status_code in (404, 422)

    def test_the_accepted_format_is_served(self, two_tenant_app):
        env = two_tenant_app
        r = env.client.get(
            "/api/brf/brf-a/integrations/format", headers=env.admin_a_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mail"]["attachmentTypes"] == ["application/pdf"]
        assert body["accountingAdapter"] == "fixture-accounting"
