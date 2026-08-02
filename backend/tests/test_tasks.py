"""Uppgifter och ansvar: the evidence travels, the history is append-only.

What is asserted here is mostly about what a task *keeps*:

* the citations of the finding or watch it came from, so the passage behind the
  work still opens later;
* every change as its own event with who and when, never an edit in place;
* the fact that it existed at all — work is cancelled with a reason, never
  deleted.

Nothing here needs a credential, a network endpoint or a running model.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest


CONTRACT = [
    "Serviceavtal hiss 2026",
    "Avtalet galler fran och med den 1 februari 2026 till och med den 31 januari 2028.",
    "Avtalet far sagas upp skriftligen senast sex manader fore avtalstidens utgang.",
]


@pytest.fixture()
def app_with_watch(two_tenant_app):
    """Two tenants, and a real watch in A to build a task from."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.make_integration_fixtures import _invoice_pdf

    env = two_tenant_app
    reply = env.client.post(
        "/api/brf/brf-a/documents",
        files={"file": ("Serviceavtal.pdf", _invoice_pdf(CONTRACT), "application/pdf")},
        headers=env.admin_a_headers,
    )
    assert reply.status_code == 200, reply.text
    scanned = env.client.post("/api/brf/brf-a/watches/scan", headers=env.admin_a_headers)
    assert scanned.status_code == 200, scanned.text
    env.watch = next(
        w for w in scanned.json()["proposed"] if w["kind"] == "notice_deadline"
    )
    return env


def create(env, brf="brf-a", headers=None, **body):
    payload = {"title": "Säg upp hissavtalet", **body}
    return env.client.post(
        f"/api/brf/{brf}/tasks", json=payload, headers=headers or env.admin_a_headers
    )


class TestCreating:
    def test_a_manual_task_is_created_by_a_person_and_says_so(self, app_with_watch):
        env = app_with_watch
        reply = create(env, description="Ring leverantören först.", responsible="Karin")
        assert reply.status_code == 200, reply.text
        task = reply.json()
        assert task["status"] == "open"
        assert task["status_label"] == "att göra"
        assert task["responsible"] == "Karin"
        assert task["origin"]["kind"] == "manual"
        assert task["origin"]["kind_label"] == "Skapad för hand"
        assert task["created_by"]
        # The first thing in the history is that somebody made it.
        assert [e["kind"] for e in task["activity"]] == ["created"]
        assert task["activity"][0]["by"] == task["created_by"]

    def test_a_task_from_a_watch_carries_the_watch_evidence(self, app_with_watch):
        env = app_with_watch
        reply = create(env, origin_kind="watch", origin_ref=env.watch["id"])
        assert reply.status_code == 200, reply.text
        task = reply.json()
        assert task["origin"]["kind"] == "watch"
        assert task["origin"]["ref_id"] == env.watch["id"]
        assert "2027-07-31" in task["origin"]["label"]
        # The citation is copied, so the passage behind the work still opens.
        assert task["citations"], "uppgiften bar inte med sig bevakningens citat"
        assert task["citations"][0]["document_name"] == "Serviceavtal.pdf"
        assert task["source_document_name"] == "Serviceavtal.pdf"

    def test_a_task_from_a_finding_carries_the_finding_evidence(self, app_with_watch):
        env = app_with_watch
        from app.integrations.models import ReviewFinding, utc_now_iso
        from app.schemas import CitationOut

        store = env.registry.get("brf-a")
        citation = CitationOut.model_validate(env.watch["citations"][0])
        finding = store.integrations.replace_findings_for_invoice(
            "inv-1",
            [
                ReviewFinding(
                    id="f1",
                    tenant_id="brf-a",
                    finding_type="invoice_contract_amount",
                    created_at=utc_now_iso(),
                    invoice_id="inv-1",
                    verdict="possible_deviation",
                    suggestion="Fakturabeloppet är 2 000 kronor högre än det citerade villkoret.",
                    citations=[citation],
                ).with_label()
            ],
        )[0]

        task = create(env, origin_kind="finding", origin_ref=finding.id).json()
        assert task["origin"]["kind"] == "finding"
        assert task["origin"]["kind_label"] == "Fakturagranskning"
        assert "möjlig avvikelse" in task["origin"]["label"]
        assert "2 000 kronor" in task["origin"]["label"]
        # The finding's citation came along, so the passage still opens.
        assert task["citations"][0]["document_name"] == citation.document_name
        assert task["source_document_id"] == citation.document_id

    def test_an_unknown_origin_reference_is_refused(self, app_with_watch):
        env = app_with_watch
        assert create(env, origin_kind="watch", origin_ref="finns-inte").status_code == 404
        assert create(env, origin_kind="mystik", origin_ref="x").status_code == 422
        assert create(env, origin_kind="watch", origin_ref="").status_code == 422

    def test_a_task_needs_a_title(self, app_with_watch):
        env = app_with_watch
        assert create(env, title="   ").status_code == 422

    def test_a_bad_date_is_refused(self, app_with_watch):
        env = app_with_watch
        assert create(env, due_date="den 30 september").status_code == 422

    def test_existing_work_for_an_origin_is_findable(self, app_with_watch):
        """So two people do not create the same task a week apart."""
        env = app_with_watch
        created = create(env, origin_kind="watch", origin_ref=env.watch["id"]).json()
        rows = env.client.get(
            f"/api/brf/brf-a/tasks/for/watch/{env.watch['id']}", headers=env.admin_a_headers
        ).json()
        assert [t["id"] for t in rows] == [created["id"]]
        assert (
            env.client.get(
                "/api/brf/brf-a/tasks/for/watch/nagot-annat", headers=env.admin_a_headers
            ).json()
            == []
        )


class TestChanging:
    def _task(self, env):
        return create(env, responsible="Karin", due_date="2027-07-31").json()

    def update(self, env, task_id, **body):
        return env.client.post(
            f"/api/brf/brf-a/tasks/{task_id}", json=body, headers=env.admin_a_headers
        )

    def test_every_change_writes_its_own_event(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        after = self.update(
            env, task["id"], status="in_progress", responsible="Jonas", due_date="2027-06-30"
        ).json()
        kinds = [e["kind"] for e in after["activity"]]
        assert kinds == ["created", "status_changed", "assigned", "due_changed"]
        by_kind = {e["kind"]: e for e in after["activity"]}
        assert by_kind["status_changed"]["from_value"] == "open"
        assert by_kind["status_changed"]["to_value"] == "in_progress"
        assert by_kind["assigned"]["from_value"] == "Karin"
        assert by_kind["assigned"]["to_value"] == "Jonas"
        assert by_kind["due_changed"]["from_value"] == "2027-07-31"
        assert by_kind["due_changed"]["to_value"] == "2027-06-30"

    def test_setting_a_field_to_what_it_already_is_writes_nothing(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        reply = self.update(env, task["id"], responsible="Karin")
        assert reply.status_code == 422
        assert "Inget att ändra" in reply.json()["detail"]

    def test_blocking_and_cancelling_need_a_reason(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        assert self.update(env, task["id"], status="blocked").status_code == 422
        assert self.update(env, task["id"], status="cancelled").status_code == 422
        ok = self.update(env, task["id"], status="blocked", note="Väntar på leverantörens svar.")
        assert ok.status_code == 200
        assert ok.json()["activity"][-1]["note"] == "Väntar på leverantörens svar."

    def test_marking_done_needs_no_ceremony(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        done = self.update(env, task["id"], status="done").json()
        assert done["status"] == "done"
        assert done["active"] is False
        assert done["activity"][-1]["kind"] == "status_changed"

    def test_a_comment_changes_nothing_but_is_recorded(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        after = env.client.post(
            f"/api/brf/brf-a/tasks/{task['id']}/comment",
            json={"note": "Talat med Nordisk Hissteknik, de återkommer."},
            headers=env.admin_a_headers,
        ).json()
        assert after["status"] == task["status"]
        assert after["activity"][-1]["kind"] == "noted"
        assert after["activity"][-1]["kind_label"] == "kommentar"
        assert (
            env.client.post(
                f"/api/brf/brf-a/tasks/{task['id']}/comment",
                json={"note": "  "},
                headers=env.admin_a_headers,
            ).status_code
            == 422
        )

    def test_history_only_ever_grows(self, app_with_watch):
        """The store refuses a write that would shorten the trail."""
        from app.tasks.store import TaskStoreError

        env = app_with_watch
        task = self._task(env)
        store = env.registry.get("brf-a")
        record = store.tasks.get_task(task["id"])
        with pytest.raises(TaskStoreError):
            store.tasks.update_task(record.model_copy(update={"activity": []}))

    def test_there_is_no_way_to_delete_a_task(self, app_with_watch):
        env = app_with_watch
        task = self._task(env)
        reply = env.client.delete(f"/api/brf/brf-a/tasks/{task['id']}", headers=env.admin_a_headers)
        assert reply.status_code in (404, 405)
        assert env.client.get("/api/brf/brf-a/tasks", headers=env.admin_a_headers).json()["counts"][
            "active"
        ] == 1


class TestTheBoard:
    def test_overdue_comes_first_and_undated_last(self, app_with_watch):
        env = app_with_watch
        create(env, title="Försenad", due_date="2020-01-01")
        create(env, title="Odaterad")
        create(env, title="Senare", due_date="2099-01-01")
        board = env.client.get("/api/brf/brf-a/tasks", headers=env.admin_a_headers).json()
        assert [t["title"] for t in board["active"]] == ["Försenad", "Senare", "Odaterad"]
        assert board["active"][0]["overdue"] is True
        assert board["active"][2]["days_left"] is None
        assert board["counts"] == {"active": 3, "overdue": 1, "unassigned": 3}

    def test_a_finished_task_is_never_overdue(self, app_with_watch):
        env = app_with_watch
        task = create(env, title="Sent men klart", due_date="2020-01-01").json()
        done = env.client.post(
            f"/api/brf/brf-a/tasks/{task['id']}", json={"status": "done"},
            headers=env.admin_a_headers,
        ).json()
        assert done["overdue"] is False
        board = env.client.get("/api/brf/brf-a/tasks", headers=env.admin_a_headers).json()
        assert board["active"] == []
        assert [t["title"] for t in board["done"]] == ["Sent men klart"]

    def test_cancelled_work_stays_visible(self, app_with_watch):
        env = app_with_watch
        task = create(env, title="Onödig").json()
        env.client.post(
            f"/api/brf/brf-a/tasks/{task['id']}",
            json={"status": "cancelled", "note": "Avtalet är redan uppsagt."},
            headers=env.admin_a_headers,
        )
        board = env.client.get("/api/brf/brf-a/tasks", headers=env.admin_a_headers).json()
        assert [t["title"] for t in board["cancelled"]] == ["Onödig"]
        assert board["cancelled"][0]["activity"][-1]["note"] == "Avtalet är redan uppsagt."


class TestPermissionsAndIsolation:
    def test_a_member_may_read_but_not_create_or_change(self, app_with_watch):
        env = app_with_watch
        task = create(env).json()
        assert (
            env.client.get("/api/brf/brf-a/tasks", headers=env.member_a_headers).status_code == 200
        )
        assert create(env, headers=env.member_a_headers).status_code == 403
        assert (
            env.client.post(
                f"/api/brf/brf-a/tasks/{task['id']}",
                json={"status": "done"},
                headers=env.member_a_headers,
            ).status_code
            == 403
        )
        assert (
            env.client.post(
                f"/api/brf/brf-a/tasks/{task['id']}/comment",
                json={"note": "hej"},
                headers=env.member_a_headers,
            ).status_code
            == 403
        )

    def test_an_unauthenticated_request_reaches_nothing(self, app_with_watch):
        env = app_with_watch
        assert env.client.get("/api/brf/brf-a/tasks").status_code == 401
        assert env.client.post("/api/brf/brf-a/tasks", json={"title": "x"}).status_code == 401

    def test_tasks_are_per_tenant(self, app_with_watch):
        env = app_with_watch
        task = create(env).json()
        assert (
            env.client.get("/api/brf/brf-a/tasks", headers=env.admin_b_headers).status_code == 404
        )
        assert env.client.get("/api/brf/brf-b/tasks", headers=env.admin_b_headers).json()["active"] == []
        assert (
            env.client.post(
                f"/api/brf/brf-b/tasks/{task['id']}",
                json={"status": "done"},
                headers=env.admin_b_headers,
            ).status_code
            == 404
        )

    def test_a_watch_from_another_tenant_cannot_be_used_as_an_origin(self, app_with_watch):
        env = app_with_watch
        reply = env.client.post(
            "/api/brf/brf-b/tasks",
            json={"title": "Stjäl bevakningen", "origin_kind": "watch", "origin_ref": env.watch["id"]},
            headers=env.admin_b_headers,
        )
        assert reply.status_code == 404

    def test_deleting_the_tenant_takes_its_tasks(self, app_with_watch, tmp_path):
        env = app_with_watch
        create(env)
        path = tmp_path / "tenants" / "brf-a" / "tasks" / "tasks.json"
        assert path.exists()
        assert env.client.delete("/api/brf/brf-a", headers=env.admin_a_headers).status_code == 200
        assert not path.exists()
