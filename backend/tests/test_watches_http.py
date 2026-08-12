"""The watch routes over real HTTP: who may decide, and whose obligations they are.

The unit suite proves the engine reads dates honestly. This proves the part
that protects an association once those dates are in front of people:

* scanning and every decision is an **admin** act; a member may read and
  nothing else;
* a valid session for Brf B reaches nothing of Brf A's, and gets 404 rather
  than 403 so tenant ids stay unprobeable;
* a re-scan never disturbs a watch a human has decided on;
* a proposal is not an obligation until somebody approves it.
"""

from __future__ import annotations

from pathlib import Path

import pytest


CONTRACT = [
    "Serviceavtal hiss 2026",
    "Mellan foreningen och Nordisk Hissteknik AB.",
    "Avtalet forlangs automatiskt med tolv manader om det inte sags upp",
    "senast tre manader fore den 31 december 2026.",
]


@pytest.fixture()
def seeded(two_tenant_app):
    """A contract with a datable notice clause in each tenant."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.make_integration_fixtures import _invoice_pdf

    env = two_tenant_app
    for brf, headers in (("brf-a", env.admin_a_headers), ("brf-b", env.admin_b_headers)):
        reply = env.client.post(
            f"/api/brf/{brf}/documents",
            files={"file": ("Serviceavtal.pdf", _invoice_pdf(CONTRACT), "application/pdf")},
            headers=headers,
        )
        assert reply.status_code == 200, reply.text
    return env


def scan(env, brf: str, headers: dict):
    reply = env.client.post(f"/api/brf/{brf}/watches/scan", headers=headers)
    assert reply.status_code == 200, reply.text
    return reply.json()


class TestScanAndPropose:
    def test_a_scan_proposes_a_dated_watch_with_its_evidence(self, seeded):
        env = seeded
        result = scan(env, "brf-a", env.admin_a_headers)
        assert result["documentsRead"] >= 1
        notice = next(w for w in result["proposed"] if w["kind"] == "notice_deadline")
        assert notice["due_date"] == "2026-09-30"
        assert notice["status"] == "proposed"
        assert notice["status_label"] == "väntar på godkännande"
        assert notice["responsible"] == ""
        assert notice["citations"][0]["page"] >= 1
        assert notice["derivation"] == "31 dec. 2026 minus 3 månader"

    def test_a_proposal_is_not_yet_on_the_board(self, seeded):
        env = seeded
        scan(env, "brf-a", env.admin_a_headers)
        board = env.client.get("/api/brf/brf-a/watches", headers=env.admin_a_headers).json()
        assert board["proposed"], "förslaget syns inte"
        assert all(not rows for rows in board["buckets"].values()), board["buckets"]

    def test_a_member_may_read_but_not_scan_or_decide(self, seeded):
        env = seeded
        assert (
            env.client.get("/api/brf/brf-a/watches", headers=env.member_a_headers).status_code
            == 200
        )
        assert (
            env.client.post("/api/brf/brf-a/watches/scan", headers=env.member_a_headers).status_code
            == 403
        )
        proposal = scan(env, "brf-a", env.admin_a_headers)["proposed"][0]
        assert (
            env.client.post(
                f"/api/brf/brf-a/watches/{proposal['id']}/decision",
                json={"status": "approved"},
                headers=env.member_a_headers,
            ).status_code
            == 403
        )

    def test_an_unauthenticated_request_reaches_nothing(self, seeded):
        env = seeded
        assert env.client.get("/api/brf/brf-a/watches").status_code == 401
        assert env.client.post("/api/brf/brf-a/watches/scan").status_code == 401


class TestDeciding:
    def _proposal(self, env):
        return scan(env, "brf-a", env.admin_a_headers)["proposed"][0]

    def test_approving_puts_it_on_the_board_with_who_and_when(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        reply = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved", "responsible": "Karin Lindqvist", "remind_lead_days": 60},
            headers=env.admin_a_headers,
        )
        assert reply.status_code == 200, reply.text
        watch = reply.json()["watch"]
        assert watch["status"] == "approved"
        assert watch["responsible"] == "Karin Lindqvist"
        assert watch["remind_at"] == "2026-08-01"
        assert watch["decided_by"] and watch["decided_at"]

        board = env.client.get("/api/brf/brf-a/watches", headers=env.admin_a_headers).json()
        assert not board["proposed"]
        assert any(watch["id"] == w["id"] for rows in board["buckets"].values() for w in rows)

    def test_moving_the_date_keeps_what_the_engine_derived(self, seeded):
        """The audit trail is the pair, not the winner."""
        env = seeded
        proposal = self._proposal(env)
        watch = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved", "due_date": "2026-09-15"},
            headers=env.admin_a_headers,
        ).json()["watch"]
        assert watch["due_date"] == "2026-09-15"
        assert watch["derived_due_date"] == "2026-09-30"
        assert watch["derivation"] == "31 dec. 2026 minus 3 månader"

    def test_a_nonsense_date_is_refused(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        reply = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved", "due_date": "den 15 september"},
            headers=env.admin_a_headers,
        )
        assert reply.status_code == 422

    def test_dismissing_without_a_reason_is_refused(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        bare = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "dismissed"},
            headers=env.admin_a_headers,
        )
        assert bare.status_code == 422
        assert "varför" in bare.json()["detail"]

        explained = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "dismissed", "note": "Avtalet är redan uppsagt 2026-06-01."},
            headers=env.admin_a_headers,
        )
        assert explained.status_code == 200
        assert explained.json()["watch"]["decision_note"].startswith("Avtalet är redan")

    def test_a_decided_watch_survives_a_rescan(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved", "responsible": "Karin"},
            headers=env.admin_a_headers,
        )
        again = scan(env, "brf-a", env.admin_a_headers)
        # Not re-proposed: "we already decided that" is not a new suggestion.
        assert not [w for w in again["proposed"] if w["due_date"] == "2026-09-30"]
        board = env.client.get("/api/brf/brf-a/watches", headers=env.admin_a_headers).json()
        kept = [w for rows in board["buckets"].values() for w in rows]
        assert [w["responsible"] for w in kept] == ["Karin"]

    def test_a_dismissed_watch_is_not_offered_again_either(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "dismissed", "note": "Avtalet avslutat."},
            headers=env.admin_a_headers,
        )
        again = scan(env, "brf-a", env.admin_a_headers)
        assert not [w for w in again["proposed"] if w["due_date"] == "2026-09-30"]

    def test_a_decided_watch_cannot_be_deleted(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved"},
            headers=env.admin_a_headers,
        )
        reply = env.client.delete(
            f"/api/brf/brf-a/watches/{proposal['id']}", headers=env.admin_a_headers
        )
        assert reply.status_code == 409

    def test_a_proposal_may_be_deleted(self, seeded):
        env = seeded
        proposal = self._proposal(env)
        assert (
            env.client.delete(
                f"/api/brf/brf-a/watches/{proposal['id']}", headers=env.admin_a_headers
            ).status_code
            == 200
        )


class TestRecurringRollover:
    def _recurring(self, env):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.make_integration_fixtures import _invoice_pdf

        env.client.post(
            "/api/brf/brf-a/documents",
            files={
                "file": (
                    "Kontrollplan.pdf",
                    _invoice_pdf(
                        [
                            "Kontrollplan",
                            "Obligatorisk ventilationskontroll utfordes den 31 maj 2026",
                            "och aterkommer vart tredje ar.",
                        ]
                    ),
                    "application/pdf",
                )
            },
            headers=env.admin_a_headers,
        )
        proposals = scan(env, "brf-a", env.admin_a_headers)["proposed"]
        return next(w for w in proposals if w["recurrence"] == "triennial")

    def test_completing_a_recurring_watch_creates_the_next_turn(self, seeded):
        env = seeded
        watch = self._recurring(env)
        assert watch["due_date"] == "2029-05-31"
        env.client.post(
            f"/api/brf/brf-a/watches/{watch['id']}/decision",
            json={"status": "approved"},
            headers=env.admin_a_headers,
        )
        reply = env.client.post(
            f"/api/brf/brf-a/watches/{watch['id']}/decision",
            json={"status": "done", "note": "Genomförd och protokollförd."},
            headers=env.admin_a_headers,
        ).json()
        assert reply["watch"]["status"] == "done"
        # The history of what was done survives; the next turn is its own row.
        successor = reply["successor"]
        assert successor is not None
        assert successor["due_date"] == "2032-05-31"
        assert successor["status"] == "approved"
        assert successor["id"] != watch["id"]
        assert reply["watch"]["succeeded_by"] == successor["id"]

    def test_a_one_off_watch_has_no_successor(self, seeded):
        env = seeded
        proposal = scan(env, "brf-a", env.admin_a_headers)["proposed"][0]
        env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "approved"},
            headers=env.admin_a_headers,
        )
        reply = env.client.post(
            f"/api/brf/brf-a/watches/{proposal['id']}/decision",
            json={"status": "done", "note": "Uppsagt."},
            headers=env.admin_a_headers,
        ).json()
        assert reply["successor"] is None


class TestTenantIsolation:
    def test_each_tenant_scans_only_its_own_archive(self, seeded):
        env = seeded
        a = scan(env, "brf-a", env.admin_a_headers)
        b = scan(env, "brf-b", env.admin_b_headers)
        assert a["proposed"] and b["proposed"]
        a_docs = {w["source_document_id"] for w in a["proposed"]}
        b_docs = {w["source_document_id"] for w in b["proposed"]}
        assert not (a_docs & b_docs)

    def test_bs_admin_cannot_read_or_decide_as(self, seeded):
        env = seeded
        proposal = scan(env, "brf-a", env.admin_a_headers)["proposed"][0]
        assert (
            env.client.get("/api/brf/brf-a/watches", headers=env.admin_b_headers).status_code == 404
        )
        assert (
            env.client.post(
                "/api/brf/brf-a/watches/scan", headers=env.admin_b_headers
            ).status_code
            == 404
        )
        assert (
            env.client.post(
                f"/api/brf/brf-a/watches/{proposal['id']}/decision",
                json={"status": "approved"},
                headers=env.admin_b_headers,
            ).status_code
            == 404
        )

    def test_an_id_from_another_tenant_is_simply_unknown(self, seeded):
        env = seeded
        proposal = scan(env, "brf-a", env.admin_a_headers)["proposed"][0]
        scan(env, "brf-b", env.admin_b_headers)
        reply = env.client.post(
            f"/api/brf/brf-b/watches/{proposal['id']}/decision",
            json={"status": "approved"},
            headers=env.admin_b_headers,
        )
        assert reply.status_code == 404

    def test_deleting_the_tenant_takes_its_watches(self, seeded, tmp_path):
        env = seeded
        scan(env, "brf-a", env.admin_a_headers)
        watches = tmp_path / "tenants" / "brf-a" / "watches" / "watches.json"
        assert watches.exists()
        assert env.client.delete("/api/brf/brf-a", headers=env.admin_a_headers).status_code == 200
        assert not watches.exists()


class TestUnresolved:
    def test_a_clause_without_a_date_is_reported_as_unresolved(self, two_tenant_app):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.make_integration_fixtures import _invoice_pdf

        env = two_tenant_app
        env.client.post(
            "/api/brf/brf-a/documents",
            files={
                "file": (
                    "Avtal utan slutdatum.pdf",
                    _invoice_pdf(
                        [
                            "Avtal",
                            "Uppsagning skall ske skriftligen senast tre manader",
                            "fore avtalstidens utgang.",
                        ]
                    ),
                    "application/pdf",
                )
            },
            headers=env.admin_a_headers,
        )
        result = scan(env, "brf-a", env.admin_a_headers)
        assert not result["proposed"], "en odaterbar klausul blev en bevakning"
        assert result["unresolved"], "klausulen rapporterades inte alls"
        row = result["unresolved"][0]
        assert "Uppsägningstid" in row["what"]
        assert row["citations"], "det som inte gick att datera saknar sitt citat"
