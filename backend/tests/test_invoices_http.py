"""The invoice workspace over real HTTP: isolation, authority, idempotence.

The unit suite proves the case logic. This proves the thing that actually
protects an association: that an authenticated admin of Brf B, holding a
genuinely valid session, cannot see or touch Brf A's invoice cases, their
comments or their review statuses — and that a member of Brf A can read the
workspace but cannot decide anything in it.

It also drives the one journey the workspace exists for, end to end and twice:
read an invoice in → one case with findings → a person comments, sets a status
and takes work on → refresh → the same records, not a second set.

Every request carries its session explicitly as a Cookie header and the shared
jar is cleared, so "no header" genuinely means "unauthenticated".
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def seeded(two_tenant_app):
    """Both tenants with one fixture invoice read into each.

    The fixture accounting dataset is scoped by ``AssociationRef``, and neither
    ``brf-a`` nor ``brf-b`` appears in it — so the invoices here are posted
    through the store directly, which is also the shortest way to give the two
    tenants deliberately distinguishable data.
    """
    import uuid
    from decimal import Decimal

    from app.integrations.models import InvoiceSnapshot, utc_now_iso

    env = two_tenant_app

    def put(brf_id: str, secret: str, supplier: str) -> InvoiceSnapshot:
        store = env.registry.get(brf_id)
        return store.integrations.upsert_invoice(
            InvoiceSnapshot(
                id=uuid.uuid4().hex[:12],
                tenant_id=brf_id,
                adapter="fixture-accounting",
                external_ref=f"SI-{secret}",
                supplier_name=supplier,
                invoice_number=f"NR-{secret}",
                invoice_date="2026-05-01",
                due_date="2026-05-31",
                total_amount=Decimal("1000.00"),
                currency="SEK",
                retrieved_at=utc_now_iso(),
                source_dataset="test",
                content_sha256="0" * 64,
            )
        )

    env.invoice_a = put("brf-a", env.secret_a, "Alfa Städ AB")
    env.invoice_b = put("brf-b", env.secret_b, "Beta Hiss AB")
    return env


def _cases(env, brf_id: str, headers) -> list[dict]:
    r = env.client.get(f"/api/brf/{brf_id}/invoices", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["cases"]


class TestIsolation:
    def test_each_tenant_sees_only_its_own_invoices(self, seeded):
        env = seeded
        a = _cases(env, "brf-a", env.admin_a_headers)
        b = _cases(env, "brf-b", env.admin_b_headers)
        assert [c["supplier_name"] for c in a] == ["Alfa Städ AB"]
        assert [c["supplier_name"] for c in b] == ["Beta Hiss AB"]
        assert env.secret_b not in str(a)
        assert env.secret_a not in str(b)

    def test_a_stranger_gets_404_never_403(self, seeded):
        env = seeded
        # 404, not 403: a 403 confirms the tenant exists.
        assert env.client.get("/api/brf/brf-a/invoices", headers=env.admin_b_headers).status_code == 404
        case_id = _cases(env, "brf-a", env.admin_a_headers)[0]["id"]
        r = env.client.get(
            f"/api/brf/brf-a/invoices/cases/{case_id}", headers=env.admin_b_headers
        )
        assert r.status_code == 404

    def test_an_unauthenticated_request_is_refused(self, seeded):
        env = seeded
        assert env.client.get("/api/brf/brf-a/invoices").status_code == 401

    def test_another_tenants_case_id_is_not_reachable_from_here(self, seeded):
        env = seeded
        foreign = _cases(env, "brf-b", env.admin_b_headers)[0]["id"]
        r = env.client.get(
            f"/api/brf/brf-a/invoices/cases/{foreign}", headers=env.admin_a_headers
        )
        assert r.status_code == 404


class TestAuthority:
    def test_a_member_may_read_the_workspace(self, seeded):
        env = seeded
        assert env.client.get("/api/brf/brf-a/invoices", headers=env.member_a_headers).status_code == 200

    def test_a_member_may_not_decide_anything(self, seeded):
        env = seeded
        case_id = _cases(env, "brf-a", env.admin_a_headers)[0]["id"]
        for path, body in (
            (f"/api/brf/brf-a/invoices/cases/{case_id}", {"review_status": "closed"}),
            (f"/api/brf/brf-a/invoices/cases/{case_id}/comment", {"note": "hej"}),
            (f"/api/brf/brf-a/invoices/cases/{case_id}/refresh", None),
            ("/api/brf/brf-a/invoices/import", {"external_ref": "SI-1", "source": "fixture"}),
        ):
            r = env.client.post(path, json=body, headers=env.member_a_headers)
            assert r.status_code == 403, (path, r.status_code)


class TestTheJourney:
    def test_one_invoice_from_source_to_settled_case(self, seeded):
        env = seeded
        case = _cases(env, "brf-a", env.admin_a_headers)[0]

        # 1. The case exists, with the source and the local status kept apart.
        assert case["review_status"] == "not_reviewed"
        assert "godkänn" not in case["review_status_label"].lower()
        assert case["source_status"] is None  # the fixture source has no such notion

        # 2. Analysis runs on request and produces findings with evidence or
        #    an honest statement that there is none.
        r = env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case['id']}/refresh",
            headers=env.admin_a_headers,
        )
        assert r.status_code == 200, r.text
        detail = env.client.get(
            f"/api/brf/brf-a/invoices/cases/{case['id']}", headers=env.admin_a_headers
        ).json()
        assert detail["findings"], "granskningen ska alltid säga något"
        for finding in detail["findings"]:
            assert finding["verdict_label"] in ("överensstämmer", "möjlig avvikelse", "kan inte verifieras")
            if finding["verdict"] != "matches":
                assert finding["uncertainty"], "ett fynd som inte är en match måste säga vad som är osäkert"

        # 3. A person comments, names themselves responsible and takes a position.
        assert env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case['id']}/comment",
            json={"note": "Bad leverantören om avtalet."},
            headers=env.admin_a_headers,
        ).status_code == 200
        assert env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case['id']}",
            json={"responsible": "Anna", "review_status": "awaiting_documentation", "note": "Väntar avtalet"},
            headers=env.admin_a_headers,
        ).status_code == 200

        # 4. Work is taken on, and the case's own history says so.
        task = env.client.post(
            "/api/brf/brf-a/tasks",
            json={
                "title": "Begär avtalet från Alfa Städ",
                "responsible": "Anna",
                "origin_kind": "invoice_case",
                "origin_ref": case["id"],
            },
            headers=env.admin_a_headers,
        )
        assert task.status_code == 200, task.text
        assert task.json()["origin"]["kind_label"] == "Fakturaärende"

        detail = env.client.get(
            f"/api/brf/brf-a/invoices/cases/{case['id']}", headers=env.admin_a_headers
        ).json()
        kinds = [e["kind"] for e in detail["case"]["timeline"]]
        assert kinds[0] == "case_opened"
        assert {"analysis_run", "commented", "status_changed", "assigned", "task_created"} <= set(kinds)
        assert [t["title"] for t in detail["tasks"]] == ["Begär avtalet från Alfa Städ"]
        assert detail["case"]["review_status_label"] == "Väntar på underlag"
        assert detail["case"]["responsible"] == "Anna"
        # The machine entries and the human ones are told apart for the reader.
        human = {e["kind"] for e in detail["case"]["timeline"] if e["human"]}
        assert human == {"commented", "status_changed", "assigned", "task_created"}

        # 5. Refreshing changes nothing that was already recorded.
        before = detail["case"]["timeline"]
        assert env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case['id']}/refresh",
            headers=env.admin_a_headers,
        ).status_code == 200
        after = env.client.get(
            f"/api/brf/brf-a/invoices/cases/{case['id']}", headers=env.admin_a_headers
        ).json()
        assert len(after["case"]["timeline"]) == len(before)
        assert len(after["findings"]) == len(detail["findings"])
        assert len(_cases(env, "brf-a", env.admin_a_headers)) == 1
        assert after["case"]["review_status"] == "awaiting_documentation"

    def test_a_status_that_hides_a_missing_sentence_is_refused(self, seeded):
        env = seeded
        case_id = _cases(env, "brf-a", env.admin_a_headers)[0]["id"]
        r = env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case_id}",
            json={"review_status": "needs_investigation", "note": "   "},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert "utreda" in r.json()["detail"]

    def test_an_empty_comment_is_refused(self, seeded):
        env = seeded
        case_id = _cases(env, "brf-a", env.admin_a_headers)[0]["id"]
        r = env.client.post(
            f"/api/brf/brf-a/invoices/cases/{case_id}/comment",
            json={"note": "  "},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422

    def test_an_unknown_source_is_named_rather_than_guessed(self, seeded):
        env = seeded
        r = env.client.post(
            "/api/brf/brf-a/invoices/import",
            json={"external_ref": "SI-1", "source": "visma"},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert "fixture" in r.json()["detail"]

    def test_reading_the_same_invoice_in_twice_leaves_one_case(self, two_tenant_app):
        """The fixture dataset belongs to the seeded demo association, so this
        drives the real import route against a tenant that owns it."""
        import sys
        from pathlib import Path

        backend_root = str(Path(__file__).resolve().parent.parent)
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
        from scripts.seed import seed_demo

        env = two_tenant_app
        seed_demo(env.registry, env.auth)
        env.auth.add_membership(
            env.auth.verify_login("admin-a@a.se", "lösenord-a-admin"), "gjutformen-12", "admin"
        )
        headers = env.admin_a_headers

        first = env.client.post(
            "/api/brf/gjutformen-12/invoices/import",
            json={"external_ref": "SI-2026-114", "source": "fixture"},
            headers=headers,
        )
        assert first.status_code == 200, first.text
        second = env.client.post(
            "/api/brf/gjutformen-12/invoices/import",
            json={"external_ref": "SI-2026-114", "source": "fixture"},
            headers=headers,
        )
        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]
        assert len(second.json()["timeline"]) == len(first.json()["timeline"])

        rows = env.client.get("/api/brf/gjutformen-12/invoices", headers=headers).json()
        assert len(rows["cases"]) == 1
        assert rows["counts"]["total"] == 1
