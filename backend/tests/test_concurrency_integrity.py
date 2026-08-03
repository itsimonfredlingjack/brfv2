"""State integrity when two people press things at the same moment.

FastAPI runs sync endpoints in a threadpool, so "at the same moment" is the
ordinary case on a desktop installation with three board members on it, not an
exotic one. Every test here was written against a *reproduced* failure — each
one failed on the code as it stood before the repair, and the docstring says
what it produced.

Nothing here hopes threads will collide. Every race is released by a
``threading.Barrier``, so all N threads are inside the critical section before
any of them proceeds, and the ones that matter run ``REPEATS`` times because a
convergence property proved once is a coincidence.

What is *not* claimed anywhere in this file: safety across processes. The
guarantees below are about one process's cached per-tenant stores, which is the
architecture this backend documents (see :mod:`app.integrations.store`). Where a
derived id would also hold across processes, the test says so; where only a lock
holds, it does not pretend otherwise.
"""

from __future__ import annotations

import threading
import uuid
from datetime import date

import pytest

# Sixteen is the number the original report used for the store-instance race,
# and eight is what it used for the write races. Kept identical so a failure
# here is comparable with what was observed.
WIDE = 16
NARROW = 8
REPEATS = 12


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def race(n: int, body):
    """Run ``body(i)`` in ``n`` threads released simultaneously.

    Returns ``(results, errors)`` — errors are captured rather than raised, so a
    test can assert on *how many* callers were refused as well as on what landed
    on disk. A refusal and a silent overwrite look identical from the outside
    unless the test looks at both.
    """
    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list = [None] * n

    def run(i: int) -> None:
        barrier.wait()
        try:
            results[i] = body(i)
        except BaseException as exc:  # noqa: BLE001 - the point is to collect them
            errors[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def message(*, subject: str, body: str, message_id: str = "<m1@exempel.se>") -> bytes:
    """One minimal, real `.eml` — the same shape ``test_intake_queue`` builds."""
    return "\r\n".join(
        [
            "From: Anna Lind <anna@snosvangen.example>",
            "To: Styrelsen <styrelsen@gjutformen12.example>",
            f"Subject: {subject}",
            "Date: Tue, 03 Feb 2026 08:14:00 +0100",
            f"Message-ID: {message_id}",
            'Content-Type: text/plain; charset="utf-8"',
            "MIME-Version: 1.0",
            "",
            body,
        ]
    ).encode("utf-8")


@pytest.fixture()
def tenant(tmp_path):
    """One tenant, no corpus. Fast, because these tests are about locks."""
    from types import SimpleNamespace

    from app.auth import AuthStore
    from app.registry import TenantRegistry

    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    registry.create("Brf A", "synthetic", "brf-a")
    store = registry.get("brf-a")
    assert store is not None
    return SimpleNamespace(root=tmp_path, auth=auth, registry=registry, store=store)


@pytest.fixture()
def api(tmp_path):
    """Two tenants over real HTTP, so route composition is what is tested.

    Deliberately not :func:`two_tenant_app`: these tests need no documents, and
    the races run often enough that indexing two PDFs per test would dominate.
    """
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.auth import AuthStore
    from app.main import SESSION_COOKIE, create_app
    from app.registry import TenantRegistry

    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    app = create_app(registry=registry, auth=auth, data_root=tmp_path)
    client = TestClient(app)
    registry.create("Brf A", "synthetic", "brf-a")
    registry.create("Brf B", "synthetic", "brf-b")

    def user(email: str, brf: str, role: str) -> dict:
        uid = auth.create_user(email, "lösenord-som-räcker", email)
        auth.add_membership(uid, brf, role)
        reply = client.post(
            "/api/auth/login", json={"email": email, "password": "lösenord-som-räcker"}
        )
        assert reply.status_code == 200, reply.text
        session = reply.cookies.get(SESSION_COOKIE)
        client.cookies.clear()
        return {"Cookie": f"{SESSION_COOKIE}={session}"}

    return SimpleNamespace(
        client=client,
        registry=registry,
        auth=auth,
        a=user("admin-a@a.se", "brf-a", "admin"),
        b=user("admin-b@b.se", "brf-b", "admin"),
        member_a=user("member-a@a.se", "brf-a", "member"),
    )


# ---------------------------------------------------------------------------
# One cached domain store per tenant
# ---------------------------------------------------------------------------


class TestExactlyOneStoreInstance:
    """Reproduced: sixteen concurrent first accesses to ``Store.integrations``
    returned between five and fifteen distinct objects, each with its own
    ``threading.RLock`` over the same JSON files. Every mutation downstream was
    locking something and no two were locking the same thing — worse than no
    lock, because the code reads as if it were safe."""

    @pytest.mark.parametrize("attr", ["integrations", "tasks", "watches"])
    def test_concurrent_first_access_yields_one_instance(self, tenant, attr):
        store = tenant.store
        for _ in range(REPEATS):
            store._integrations = None
            store._tasks = None
            store._watches = None
            seen, errors = race(WIDE, lambda _i: id(getattr(store, attr)))
            assert not any(errors), [e for e in errors if e]
            assert len(set(seen)) == 1, (
                f"{attr}: {len(set(seen))} olika instanser av {WIDE} samtidiga "
                "förstahandsåtkomster"
            )

    def test_credentials_are_one_instance_too(self, tenant):
        """The same check-then-set, one level down: two ``CredentialStore``
        objects would mean a token refresh and a disconnect writing one
        ``connections.json`` under two different locks."""
        for _ in range(REPEATS):
            tenant.store._integrations = None
            integrations = tenant.store.integrations
            integrations._credentials = None
            seen, errors = race(WIDE, lambda _i: id(integrations.credentials))
            assert not any(errors), [e for e in errors if e]
            assert len(set(seen)) == 1

    def test_the_instance_is_the_one_the_registry_hands_out(self, tenant):
        """Convergence is not enough on its own: the winner must also be what
        every later request gets, or two of them would still diverge."""
        store = tenant.store
        store._tasks = None
        seen, _ = race(WIDE, lambda _i: id(store.tasks))
        assert set(seen) == {id(tenant.registry.get("brf-a").tasks)}


# ---------------------------------------------------------------------------
# Append-only human history
# ---------------------------------------------------------------------------


class TestTaskHistory:
    """Reproduced: eight concurrent comments on one task left two on disk. Each
    request read the task before the store lock, appended one event, and wrote
    back a complete replacement — every write passed the old "is it at least as
    long" check, and the last one to land was the only comment that survived."""

    def _task(self, api) -> str:
        reply = api.client.post(
            "/api/brf/brf-a/tasks", json={"title": "Byt fläktmotor"}, headers=api.a
        )
        assert reply.status_code == 200, reply.text
        return reply.json()["id"]

    def _activity(self, api, task_id: str) -> list[dict]:
        board = api.client.get("/api/brf/brf-a/tasks", headers=api.a).json()
        rows = board["active"] + board["done"] + board["cancelled"]
        return next(t for t in rows if t["id"] == task_id)["activity"]

    def test_all_concurrent_comments_survive_exactly_once(self, api):
        for attempt in range(REPEATS):
            task_id = self._task(api)
            notes = [f"kommentar-{attempt}-{i}" for i in range(NARROW)]
            codes, errors = race(
                NARROW,
                lambda i: api.client.post(
                    f"/api/brf/brf-a/tasks/{task_id}/comment",
                    json={"note": notes[i]},
                    headers=api.a,
                ).status_code,
            )
            assert not any(errors), [e for e in errors if e]
            assert codes == [200] * NARROW
            written = [e["note"] for e in self._activity(api, task_id)]
            for note in notes:
                assert written.count(note) == 1, f"{note} skrevs {written.count(note)} gånger"

    def test_concurrent_edits_each_leave_their_own_event(self, api):
        """Not only comments: eight different field changes at once must produce
        eight events, because each is somebody saying they did something."""
        for _ in range(REPEATS):
            task_id = self._task(api)
            codes, errors = race(
                NARROW,
                lambda i: api.client.post(
                    f"/api/brf/brf-a/tasks/{task_id}",
                    json={"responsible": f"Person {i}"},
                    headers=api.a,
                ).status_code,
            )
            assert not any(errors), [e for e in errors if e]
            assert codes == [200] * NARROW
            assigned = [e for e in self._activity(api, task_id) if e["kind"] == "assigned"]
            assert len(assigned) == NARROW

    def test_a_stale_complete_object_is_refused_not_absorbed(self, tenant):
        """The backstop under the mechanism. ``mutate_task`` makes a stale write
        impossible from a route; this proves that if one arrives anyway it is
        rejected rather than quietly overwriting the history it does not have."""
        from app.tasks.models import Task, TaskEvent, TaskOrigin
        from app.tasks.store import TaskStoreError

        store = tenant.store
        task = store.tasks.add_task(
            Task(
                id="t1",
                tenant_id="brf-a",
                title="Uppgift",
                origin=TaskOrigin(kind="manual"),
                created_by="u",
                created_at="2026-08-02T00:00:00Z",
            )
        )

        def commented(note: str, event_id: str) -> Task:
            return task.model_copy(
                update={
                    "activity": [
                        *task.activity,
                        TaskEvent(
                            id=event_id, at="2026-08-02T00:00:01Z", by="u", kind="noted", note=note
                        ),
                    ]
                }
            )

        store.tasks.update_task(commented("först", "e1"))
        with pytest.raises(TaskStoreError, match="append-only"):
            # Same length, different content — exactly what the old length check
            # let through, and exactly how seven of eight comments vanished.
            store.tasks.update_task(commented("sedan", "e2"))
        assert [e.note for e in store.tasks.get_task("t1").activity] == ["först"]


class TestSourceEventHistory:
    def test_decision_history_is_append_only(self, tenant):
        """The same prefix rule guards the queue's decision history, so a stale
        event object cannot drop a filed settlement on its way past."""
        from app.integrations.intake import import_eml
        from app.integrations.models import DecisionRecord, Resolution
        from app.integrations.store import IntegrationError

        store = tenant.store
        event = import_eml(
            store=store,
            integrations=store.integrations,
            raw=message(subject="Anbud", body="Vi godkanner offerten."),
            filename="m.eml",
            imported_by="u",
        )
        record = DecisionRecord(
            resolution=Resolution(decided_by="anna"), review_status="approved"
        )
        stored = store.integrations.mutate_source_event(
            event.id, lambda e: e.model_copy(update={"decision_history": [record]})
        )
        assert len(stored.decision_history) == 1
        with pytest.raises(IntegrationError, match="append-only"):
            store.integrations.update_source_event(
                stored.model_copy(update={"decision_history": []})
            )


# ---------------------------------------------------------------------------
# Duplicate imports
# ---------------------------------------------------------------------------


class TestDuplicateImport:
    """Reproduced: eight concurrent imports of the exact same MIME message
    stored seven or eight separate events. The content-hash check ran before the
    locked append and each event got a random id, so every importer read "new"
    before any of them had written."""

    def test_identical_concurrent_imports_produce_one_event(self, tenant):
        from app.integrations.intake import DuplicateSourceEvent, import_eml

        store = tenant.store
        for attempt in range(REPEATS):
            raw = message(
                subject=f"Anbud {attempt}",
                body="Vi godkanner offerten pa 148 000 kr.",
                message_id=f"<m{attempt}@exempel.se>",
            )

            def importer(_i, raw=raw):
                try:
                    return import_eml(
                        store=store,
                        integrations=store.integrations,
                        raw=raw,
                        filename="m.eml",
                        imported_by="u",
                    ).id
                except DuplicateSourceEvent as exc:
                    return exc.existing.id

            ids, errors = race(NARROW, importer)
            assert not any(errors), [e for e in errors if e]
            # Every caller is told about the *same* event, whether it created it
            # or was refused — a refusal that named a different id would send the
            # operator to the wrong card.
            assert len(set(ids)) == 1
            events = [e for e in store.integrations.list_source_events()]
            assert len([e for e in events if e.subject == f"Anbud {attempt}"]) == 1

    def test_the_id_is_derived_from_the_message(self, tenant):
        """Convergence that does not depend on the lock, and therefore survives
        the process boundary the lock does not cross."""
        from app.integrations.intake import source_event_id_for

        raw = message(subject="Anbud", body="text")
        import hashlib

        digest = hashlib.sha256(raw).hexdigest()
        assert source_event_id_for("brf-a", digest) == source_event_id_for("brf-a", digest)
        assert source_event_id_for("brf-a", digest) != source_event_id_for("brf-b", digest)

    def test_a_refused_duplicate_leaves_no_orphan_document(self, tenant):
        """The rollback still holds now that the duplicate check moved inside
        the lock: a refused import must not leave its attachments behind."""
        from app.integrations.intake import DuplicateSourceEvent, import_eml

        store = tenant.store
        raw = message(subject="Anbud", body="text")
        import_eml(
            store=store,
            integrations=store.integrations,
            raw=raw,
            filename="m.eml",
            imported_by="u",
        )
        before = set(store.documents)
        with pytest.raises(DuplicateSourceEvent):
            import_eml(
                store=store,
                integrations=store.integrations,
                raw=raw,
                filename="m.eml",
                imported_by="u",
            )
        assert set(store.documents) == before


# ---------------------------------------------------------------------------
# Recurring watches
# ---------------------------------------------------------------------------


class TestWatchSuccessor:
    """Reproduced: eight concurrent completions of one yearly obligation created
    eight successors — eight identical besiktningar on next year's board, seven
    of which nobody could account for. The route read, updated, added and
    updated again as four separate store calls with a ``uuid4`` in the middle."""

    def _recurring(self, api) -> str:
        from app.watches.models import Watch

        store = api.registry.get("brf-a")
        watch = store.watches.add_watch(
            Watch(
                id=uuid.uuid4().hex[:12],
                tenant_id="brf-a",
                kind="inspection",
                status="approved",
                title="Besiktning 2026-03-01",
                due_date="2026-03-01",
                derived_due_date="2026-03-01",
                derivation="test",
                recurrence="yearly",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        return watch.id

    def test_concurrent_completion_produces_at_most_one_successor(self, api):
        for _ in range(REPEATS):
            watch_id = self._recurring(api)
            before = {w["id"] for w in _all_watches(api)}
            codes, errors = race(
                NARROW,
                lambda _i: api.client.post(
                    f"/api/brf/brf-a/watches/{watch_id}/decision",
                    json={"status": "done"},
                    headers=api.a,
                ).status_code,
            )
            assert not any(errors), [e for e in errors if e]
            assert codes == [200] * NARROW
            after = [w for w in _all_watches(api) if w["id"] not in before]
            assert len(after) <= 1, f"{len(after)} efterföljare skapades"
            assert len(after) == 1, "den återkommande bevakningen fick ingen efterföljare alls"
            done = next(w for w in _all_watches(api) if w["id"] == watch_id)
            assert done["succeeded_by"] == after[0]["id"]

    def test_a_retried_completion_reuses_the_successor(self, api):
        """Not only simultaneous: an operator who presses again a minute later,
        having never seen the first response, must not get a second one."""
        watch_id = self._recurring(api)
        first = api.client.post(
            f"/api/brf/brf-a/watches/{watch_id}/decision",
            json={"status": "done"},
            headers=api.a,
        ).json()
        second = api.client.post(
            f"/api/brf/brf-a/watches/{watch_id}/decision",
            json={"status": "done"},
            headers=api.a,
        ).json()
        assert second["successor"]["id"] == first["successor"]["id"]
        assert len(_all_watches(api)) == 2

    def test_a_one_off_watch_gets_no_successor(self, api):
        """The repair must not have turned every completion into a recurrence."""
        from app.watches.models import Watch

        store = api.registry.get("brf-a")
        watch = store.watches.add_watch(
            Watch(
                id="single",
                tenant_id="brf-a",
                kind="expiry",
                status="approved",
                title="Avtalet upphör 2026-06-30",
                due_date="2026-06-30",
                derived_due_date="2026-06-30",
                derivation="test",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        reply = api.client.post(
            f"/api/brf/brf-a/watches/{watch.id}/decision",
            json={"status": "done"},
            headers=api.a,
        ).json()
        assert reply["successor"] is None
        assert len(_all_watches(api)) == 1


def _all_watches(api) -> list[dict]:
    board = api.client.get("/api/brf/brf-a/watches", headers=api.a).json()
    rows = list(board["proposed"]) + list(board["settled"])
    for bucket in board["buckets"].values():
        rows.extend(bucket)
    return rows


# ---------------------------------------------------------------------------
# Resolving a queue item: four domains, one button
# ---------------------------------------------------------------------------


class TestResolutionIsRetrySafe:
    """Reproduced: a fault after ``resolve_source_event`` created its task but
    before it updated the source event left the task committed and the message
    unresolved. Retrying — the only thing an operator can reasonably do —
    created a second task."""

    def _event(self, tenant, subject="Föreläggande"):
        from app.integrations.intake import import_eml

        return import_eml(
            store=tenant.store,
            integrations=tenant.store.integrations,
            raw=message(subject=subject, body="Ni har tio dagar pa er att svara."),
            filename="m.eml",
            imported_by="u",
        )

    def _resolve(self, tenant, event_id, **kw):
        from app.integrations.resolve import resolve_source_event

        return resolve_source_event(
            store=tenant.store,
            event_id=event_id,
            user_id="anna",
            kinds=kw.pop("kinds", ["create_task"]),
            note=kw.pop("note", "Vi måste svara"),
            task=kw.pop("task", {"title": "Svara på föreläggandet"}),
            today=date(2026, 8, 2),
            **kw,
        )

    @pytest.mark.parametrize(
        "stage", ["after_task", "after_watch", "before_settle"]
    )
    def test_a_fault_at_any_stage_is_safe_to_retry(self, tenant, monkeypatch, stage):
        """Fault injection after each meaningful stage of the multi-domain act.

        In every case the retry must converge: one task, one watch, one settled
        card. It converges because every id is derived from what it is for, so
        the second attempt asks for the row the first one already made.
        """
        from app.integrations import resolve as resolve_mod

        event = self._event(tenant)
        kinds = ["create_task", "monitor"]
        watch_spec = {"due_date": "2026-09-01", "kind": "stated_deadline"}

        boom = RuntimeError("simulerat fel mitt i")
        if stage == "after_task":
            real = resolve_mod._create_watch

            def explode(*a, **k):
                raise boom

            monkeypatch.setattr(resolve_mod, "_create_watch", explode)
        elif stage == "after_watch":
            real_mutate = tenant.store.integrations.mutate_source_event

            def explode(event_id, apply):
                raise boom

            monkeypatch.setattr(
                tenant.store.integrations, "mutate_source_event", explode
            )
        else:
            real_mutate = tenant.store.integrations.mutate_source_event

            def explode(event_id, apply):
                raise boom

            monkeypatch.setattr(
                tenant.store.integrations, "mutate_source_event", explode
            )

        with pytest.raises(RuntimeError):
            self._resolve(tenant, event.id, kinds=kinds, watch=watch_spec)

        monkeypatch.undo()

        # The operator retries the identical request.
        settled = self._resolve(tenant, event.id, kinds=kinds, watch=watch_spec)

        assert settled.resolution is not None
        assert len(tenant.store.tasks.list_tasks()) == 1
        assert len(tenant.store.watches.list_watches()) == 1
        assert len([o for o in settled.resolution.outcomes if o.kind == "create_task"]) == 1
        assert len([o for o in settled.resolution.outcomes if o.kind == "monitor"]) == 1
        _ = real if stage == "after_task" else real_mutate  # keep the reference honest

    def test_an_identical_replay_of_a_settled_item_does_nothing(self, tenant):
        """The idempotency key. Two clicks on one button are one decision, and
        the second must return what the first did rather than re-running it."""
        event = self._event(tenant)
        first = self._resolve(tenant, event.id)
        second = self._resolve(tenant, event.id)
        assert second.resolution.key == first.resolution.key
        assert second.resolution.decided_at == first.resolution.decided_at
        assert len(tenant.store.tasks.list_tasks()) == 1

    def test_concurrent_identical_resolutions_produce_one_of_everything(self, tenant):
        for attempt in range(REPEATS):
            event = self._event(tenant, subject=f"Föreläggande {attempt}")
            before_tasks = len(tenant.store.tasks.list_tasks())
            _, errors = race(
                NARROW, lambda _i: self._resolve(tenant, event.id).resolution.key
            )
            assert not any(errors), [e for e in errors if e]
            assert len(tenant.store.tasks.list_tasks()) == before_tasks + 1

    def test_a_genuinely_different_decision_is_still_allowed_through(self, tenant):
        """Idempotency must not become "one task per message, forever". A
        different title is a different piece of work and gets its own task."""
        event = self._event(tenant)
        self._resolve(tenant, event.id, task={"title": "Svara på föreläggandet"})
        from app.integrations.resolve import reopen_source_event

        reopen_source_event(store=tenant.store, event_id=event.id, user_id="anna")
        self._resolve(tenant, event.id, task={"title": "Beställ juridisk hjälp"})
        titles = sorted(t.title for t in tenant.store.tasks.list_tasks())
        assert titles == ["Beställ juridisk hjälp", "Svara på föreläggandet"]


class TestOutputIdentityFollowsTheWholeDecision:
    """Reproduced: the identity of what a resolution created was narrower than
    the decision that created it.

    A message settled into a task called "Utred", assigned to Anna, due 1
    September. Reopened, and settled into a task called "Utred", assigned to Bo,
    due 1 October. Only Anna's task existed afterwards, and the second
    settlement pointed at it — the board had recorded a decision the system had
    silently declined to carry out. The task id was derived from the tenant, the
    message and the title, so everything else a reviewer had chosen was
    invisible to it. Watches had the same shape of hole: kind and date only, so
    the title, who is responsible, the reminder and the note all fell outside.

    The identity is now derived from ``resolution_key`` — the whole normalized
    command — plus which output of it this is."""

    def _event(self, tenant, subject="Föreläggande", mid="<oid@x.se>"):
        from app.integrations.intake import import_eml

        return import_eml(
            store=tenant.store,
            integrations=tenant.store.integrations,
            raw=message(subject=subject, body="Ni har tio dagar pa er.", message_id=mid),
            filename="m.eml",
            imported_by="u",
        )

    def _settle(self, tenant, event_id, **kw):
        """Settle, and return the ref_id of the outcome asked about.

        Every call after the first reopens first, because a settled card does
        not accept a second, different decision — that is the other half of this
        repair and it is asserted in :class:`TestASettledItemIsNotOverwritten`.
        Here the reopen is scaffolding: what is under test is whether the two
        decisions produce one row or two.
        """
        from app.integrations.resolve import reopen_source_event, resolve_source_event

        kind = kw.pop("kind", "create_task")
        if tenant.store.integrations.get_source_event(event_id).resolution is not None:
            reopen_source_event(store=tenant.store, event_id=event_id, user_id="anna")
        settled = resolve_source_event(
            store=tenant.store,
            event_id=event_id,
            user_id="anna",
            kinds=[kind],
            note=kw.pop("note", "Vi måste svara"),
            today=date(2026, 8, 2),
            **kw,
        )
        return next(o.ref_id for o in settled.resolution.outcomes if o.kind == kind)

    # ---------- tasks ----------

    def test_a_changed_responsible_person_is_a_different_task(self, tenant):
        event = self._event(tenant)
        first = self._settle(tenant, event.id, task={"title": "Utred", "responsible": "Anna"})
        second = self._settle(tenant, event.id, task={"title": "Utred", "responsible": "Bo"})

        assert first != second, (
            "samma rubrik men en annan ansvarig är ett annat beslut och får inte "
            "tyst peka på den förra uppgiften"
        )
        by_id = {t.id: t for t in tenant.store.tasks.list_tasks()}
        assert len(by_id) == 2
        assert by_id[first].responsible == "Anna"
        assert by_id[second].responsible == "Bo", (
            "den andra uppgiften ska bära det andra beslutets ansvarige, inte det förstas"
        )

    def test_a_changed_due_date_is_a_different_task(self, tenant):
        event = self._event(tenant, mid="<oid2@x.se>")
        first = self._settle(
            tenant, event.id, task={"title": "Utred", "due_date": "2026-09-01"}
        )
        second = self._settle(
            tenant, event.id, task={"title": "Utred", "due_date": "2026-10-01"}
        )

        assert first != second
        by_id = {t.id: t for t in tenant.store.tasks.list_tasks()}
        assert by_id[first].due_date == "2026-09-01"
        assert by_id[second].due_date == "2026-10-01"

    def test_a_changed_description_is_a_different_task(self, tenant):
        event = self._event(tenant, mid="<oid3@x.se>")
        first = self._settle(
            tenant, event.id, task={"title": "Utred", "description": "Ring förvaltaren."}
        )
        second = self._settle(
            tenant, event.id, task={"title": "Utred", "description": "Begär juridisk hjälp."}
        )

        assert first != second
        by_id = {t.id: t for t in tenant.store.tasks.list_tasks()}
        assert by_id[first].description == "Ring förvaltaren."
        assert by_id[second].description == "Begär juridisk hjälp."

    # ---------- watches ----------

    def test_a_changed_watch_field_is_a_different_watch(self, tenant):
        """Same kind, same date — everything the old id was keyed on — and a
        different title, responsible and reminder."""
        event = self._event(tenant, mid="<oid4@x.se>")
        spec = {"due_date": "2026-09-30", "kind": "expected_reply"}
        first = self._settle(
            tenant,
            event.id,
            kind="monitor",
            watch={**spec, "title": "Vänta svar från Anna", "responsible": "Anna",
                   "remind_lead_days": 7},
        )
        second = self._settle(
            tenant,
            event.id,
            kind="monitor",
            watch={**spec, "title": "Vänta svar från Bo", "responsible": "Bo",
                   "remind_lead_days": 30},
        )

        assert first != second
        by_id = {w.id: w for w in tenant.store.watches.list_watches()}
        assert len(by_id) == 2
        assert (by_id[first].responsible, by_id[first].remind_lead_days) == ("Anna", 7)
        assert (by_id[second].responsible, by_id[second].remind_lead_days) == ("Bo", 30)

    # ---------- and the direction that must NOT change ----------

    def test_an_identical_retry_still_produces_exactly_one_output(self, tenant):
        """The repair must not have turned every retry into a duplicate.

        Repeated because this is the property a fault-injected retry depends on:
        the same command, whatever else has happened, converges on one row."""
        from app.integrations.resolve import resolve_source_event

        for attempt in range(REPEATS):
            event = self._event(tenant, subject=f"F {attempt}", mid=f"<oid-r{attempt}@x.se>")
            spec = {"title": "Utred", "responsible": "Anna", "due_date": "2026-09-01"}
            watch_spec = {"due_date": "2026-09-30", "kind": "expected_reply",
                          "title": "Vänta", "responsible": "Anna"}
            before_tasks = len(tenant.store.tasks.list_tasks())
            before_watches = len(tenant.store.watches.list_watches())

            refs = set()
            for _ in range(4):
                settled = resolve_source_event(
                    store=tenant.store,
                    event_id=event.id,
                    user_id="anna",
                    kinds=["create_task", "monitor"],
                    note="Vi måste svara",
                    task=spec,
                    watch=watch_spec,
                    today=date(2026, 8, 2),
                )
                refs.add(tuple(sorted(o.ref_id for o in settled.resolution.outcomes)))

            assert len(refs) == 1, f"omtaget pekade på olika rader: {refs}"
            assert len(tenant.store.tasks.list_tasks()) == before_tasks + 1
            assert len(tenant.store.watches.list_watches()) == before_watches + 1

    def test_whitespace_is_not_a_new_decision(self, tenant):
        """The old id stripped the title before hashing it. The key must be at
        least as canonical, or the repair would have traded one duplicate for
        another: a retyped trailing space would make a second task."""
        event = self._event(tenant, mid="<oid5@x.se>")
        first = self._settle(tenant, event.id, task={"title": "Utred", "responsible": "Anna"})
        from app.integrations.resolve import resolve_source_event

        settled = resolve_source_event(
            store=tenant.store,
            event_id=event.id,
            user_id="anna",
            kinds=["create_task"],
            note="Vi måste svara",
            task={"title": "  Utred  ", "responsible": "Anna ", "description": ""},
            today=date(2026, 8, 2),
        )
        second = next(
            o.ref_id for o in settled.resolution.outcomes if o.kind == "create_task"
        )
        assert first == second
        assert len(tenant.store.tasks.list_tasks()) == 1

    def test_concurrent_identical_settlements_converge_on_one_row(self, tenant):
        """The barrier version of the same property, repeated."""
        for attempt in range(REPEATS):
            event = self._event(tenant, subject=f"S {attempt}", mid=f"<oid-c{attempt}@x.se>")
            before = len(tenant.store.tasks.list_tasks())

            from app.integrations.resolve import resolve_source_event

            def one(_i, event_id=event.id):
                settled = resolve_source_event(
                    store=tenant.store,
                    event_id=event_id,
                    user_id="anna",
                    kinds=["create_task"],
                    note="Vi måste svara",
                    task={"title": "Utred", "responsible": "Anna"},
                    today=date(2026, 8, 2),
                )
                return next(
                    o.ref_id for o in settled.resolution.outcomes if o.kind == "create_task"
                )

            refs, errors = race(NARROW, one)
            assert not any(errors), [e for e in errors if e]
            assert len(set(r for r in refs if r)) == 1
            assert len(tenant.store.tasks.list_tasks()) == before + 1


class TestASettledItemIsNotOverwritten:
    """Reproduced: settling an item that was already settled replaced the
    decision on it, and filed nothing.

    ``reopen`` had been repaired to keep the decision it undoes, and the coarse
    ``/decision`` route with it — but the ordinary settle button still went
    straight past both. Two board members reviewing the same queue on a Sunday
    evening was enough: the second one's click erased the first one's decision,
    its stated reason, its decider and the list of what it produced, with
    nothing anywhere saying it had happened.

    Changing a settlement is a real thing a board does. It has an operation, and
    that operation keeps the record."""

    def _event(self, tenant, mid="<ovw@x.se>"):
        from app.integrations.intake import import_eml

        return import_eml(
            store=tenant.store,
            integrations=tenant.store.integrations,
            raw=message(subject="Föreläggande", body="Svara inom tio dagar.", message_id=mid),
            filename="m.eml",
            imported_by="u",
        )

    def test_an_identical_replay_returns_the_existing_resolution(self, tenant):
        from app.integrations.resolve import resolve_source_event

        event = self._event(tenant)
        first = resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="anna",
            kinds=["create_task"], note="Vi måste svara",
            task={"title": "Svara"}, today=date(2026, 8, 2),
        )
        second = resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="anna",
            kinds=["create_task"], note="Vi måste svara",
            task={"title": "Svara"}, today=date(2026, 8, 2),
        )
        assert second.resolution.key == first.resolution.key
        assert second.resolution.decided_at == first.resolution.decided_at
        assert second.decision_history == []
        assert len(tenant.store.tasks.list_tasks()) == 1

    def test_a_different_resolution_is_refused_and_changes_nothing(self, tenant):
        from app.integrations.resolve import ResolutionConflict, resolve_source_event

        event = self._event(tenant, mid="<ovw2@x.se>")
        first = resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="anna",
            kinds=["create_task"], note="Vi måste svara",
            task={"title": "Svara"}, today=date(2026, 8, 2),
        )
        before = tenant.store.integrations.get_source_event(event.id)

        with pytest.raises(ResolutionConflict):
            resolve_source_event(
                store=tenant.store, event_id=event.id, user_id="björn",
                kinds=["not_relevant"], note="Fel förening",
                today=date(2026, 8, 2),
            )

        after = tenant.store.integrations.get_source_event(event.id)
        assert after.model_dump(mode="json") == before.model_dump(mode="json"), (
            "en vägran får inte ha skrivit någonting"
        )
        assert after.resolution.decided_by == "anna"
        assert after.resolution.key == first.resolution.key
        assert after.decision_history == []
        assert len(tenant.store.tasks.list_tasks()) == 1

    def test_the_route_answers_409_not_a_silent_overwrite(self, api):
        from app.integrations.intake import import_eml
        from app.integrations.resolve import resolve_source_event

        store = api.registry.get("brf-a")
        event = import_eml(
            store=store,
            integrations=store.integrations,
            raw=message(subject="Föreläggande", body="Svara inom tio dagar."),
            filename="m.eml",
            imported_by="u",
        )
        resolve_source_event(
            store=store, event_id=event.id, user_id="anna",
            kinds=["already_handled"], note="Klart", today=date(2026, 8, 2),
        )
        url = f"/api/brf/brf-a/integrations/source-events/{event.id}/resolve"

        conflict = api.client.post(
            url, json={"outcomes": ["not_relevant"], "note": "Fel förening"}, headers=api.a
        )
        assert conflict.status_code == 409, conflict.text
        assert "Öppna posten igen" in conflict.json()["detail"]

        # The identical request is not a conflict — it is the same decision.
        replay = api.client.post(
            url, json={"outcomes": ["already_handled"], "note": "Klart"}, headers=api.a
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["resolution"]["decided_by"] == "anna"

    def test_reopening_files_the_previous_decision(self, tenant):
        from app.integrations.resolve import reopen_source_event, resolve_source_event

        event = self._event(tenant, mid="<ovw3@x.se>")
        resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="anna",
            kinds=["create_task"], note="Vi måste svara",
            task={"title": "Svara"}, today=date(2026, 8, 2),
        )
        reopened = reopen_source_event(
            store=tenant.store, event_id=event.id, user_id="björn", note="Fel person"
        )
        assert reopened.resolution is None and reopened.review_status == "open"
        assert len(reopened.decision_history) == 1
        assert reopened.decision_history[0].resolution.decided_by == "anna"
        assert reopened.decision_history[0].superseded_by == "björn"

    def test_a_different_resolution_after_reopening_keeps_both_attributable(self, tenant):
        """The whole point of refusing the overwrite: the second decision is
        allowed, and the first one is still there to be read."""
        from app.integrations.resolve import reopen_source_event, resolve_source_event

        event = self._event(tenant, mid="<ovw4@x.se>")
        resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="anna",
            kinds=["create_task"], note="Vi måste svara",
            task={"title": "Svara"}, today=date(2026, 8, 2),
        )
        reopen_source_event(
            store=tenant.store, event_id=event.id, user_id="björn", note="Fel person"
        )
        second = resolve_source_event(
            store=tenant.store, event_id=event.id, user_id="björn",
            kinds=["create_task"], note="Bo tar det",
            task={"title": "Svara", "responsible": "Bo"}, today=date(2026, 8, 2),
        )

        # The decision that stands.
        assert second.resolution.decided_by == "björn"
        assert second.resolution.note == "Bo tar det"
        # The decision that was superseded, still named and still explained.
        assert len(second.decision_history) == 1
        filed = second.decision_history[0]
        assert filed.resolution.decided_by == "anna"
        assert filed.resolution.note == "Vi måste svara"
        assert filed.superseded_by == "björn"
        assert filed.note == "Fel person"
        # And two tasks, because two people decided two different things — the
        # second is not a silent alias for the first.
        tasks = {t.id: t for t in tenant.store.tasks.list_tasks()}
        assert len(tasks) == 2
        new_id = next(o.ref_id for o in second.resolution.outcomes if o.kind == "create_task")
        old_id = next(o.ref_id for o in filed.resolution.outcomes if o.kind == "create_task")
        assert new_id != old_id
        assert tasks[new_id].responsible == "Bo"
        assert tasks[old_id].responsible == ""

    def test_concurrent_different_settlements_leave_exactly_one_winner(self, tenant):
        """Eight people, eight different decisions, one card.

        Exactly one may be recorded; the other seven must be refused rather than
        overwrite it in turn. Repeated, because which thread wins is genuinely
        undetermined and the invariant is about the count, not the winner."""
        from app.integrations.resolve import ResolutionConflict, resolve_source_event

        for attempt in range(REPEATS):
            event = self._event(tenant, mid=f"<ovw-race{attempt}@x.se>")

            def one(i, event_id=event.id):
                try:
                    settled = resolve_source_event(
                        store=tenant.store,
                        event_id=event_id,
                        user_id=f"u{i}",
                        kinds=["create_task"],
                        note=f"beslut {i}",
                        task={"title": f"Uppgift {i}"},
                        today=date(2026, 8, 2),
                    )
                    return ("settled", settled.resolution.decided_by)
                except ResolutionConflict:
                    return ("refused", None)

            results, errors = race(NARROW, one)
            assert not any(errors), [e for e in errors if e]
            settled = [r for r in results if r and r[0] == "settled"]
            assert len(settled) == 1, f"{len(settled)} beslut skrevs på ett och samma kort"

            final = tenant.store.integrations.get_source_event(event.id)
            assert final.resolution.decided_by == settled[0][1]
            assert final.decision_history == []
            # And exactly one task: the seven refusals wrote nothing at all.
            origin = [
                t for t in tenant.store.tasks.list_tasks()
                if t.origin.kind == "source_event" and t.origin.ref_id == event.id
            ]
            assert len(origin) == 1


class TestCrossReferenceFailureDoesNotHideTheWrite:
    """Creating a task from an invoice case writes into two domains: the task
    store, then a pointer on the case's timeline. The second used to be able to
    turn a committed task into a 500 — and the only thing an operator can do
    with a 500 is press the button again, which would have given the
    association two identical tasks."""

    def test_a_failing_case_note_still_returns_the_created_task(self, api, monkeypatch):
        from app.integrations.models import InvoiceSnapshot
        from app.invoices import cases as case_ops

        store = api.registry.get("brf-a")
        snapshot = store.integrations.upsert_invoice(
            InvoiceSnapshot(
                id="inv-1",
                tenant_id="brf-a",
                adapter="fixture",
                external_ref="F-1",
                supplier_name="Snösvängen AB",
                invoice_number="1001",
                invoice_date="2026-02-01",
                total_amount="12500.00",
                currency="SEK",
                retrieved_at="2026-02-01T08:00:00+00:00",
                source_dataset="test",
                content_sha256="a" * 64,
            )
        )
        case = case_ops.project_one(
            store, case_ops.case_id_for("brf-a", case_ops.case_key_for(snapshot)[0])
        )
        assert case is not None

        def explode(*a, **k):
            raise RuntimeError("fakturaärendet gick inte att skriva")

        monkeypatch.setattr(case_ops, "note_task", explode)

        reply = api.client.post(
            "/api/brf/brf-a/tasks",
            json={
                "title": "Begär kreditfaktura",
                "origin_kind": "invoice_case",
                "origin_ref": case.id,
            },
            headers=api.a,
        )
        assert reply.status_code == 200, reply.text
        assert [t.title for t in store.tasks.list_tasks()] == ["Begär kreditfaktura"]

        # And the operator, seeing success, does not press again — but if they
        # did, the manual route's ordinary semantics apply and that is a second
        # deliberate task, not a duplicate of a failure.
        monkeypatch.undo()
        assert len(store.tasks.list_tasks()) == 1


class TestReopenKeepsTheDecision:
    """Reproduced: reopening a settled queue item set ``resolution`` to ``None``
    and nulled the decider and the date. Nothing anywhere then said the
    association had ever settled it, who did, why, or what it produced — while
    the task it produced was still in Uppgifter with an origin pointing back at
    a card that denied making it."""

    def test_the_settlement_is_filed_not_deleted(self, tenant):
        from app.integrations.intake import import_eml
        from app.integrations.resolve import reopen_source_event, resolve_source_event

        event = import_eml(
            store=tenant.store,
            integrations=tenant.store.integrations,
            raw=message(subject="Föreläggande", body="Svara inom tio dagar."),
            filename="m.eml",
            imported_by="u",
        )
        resolve_source_event(
            store=tenant.store,
            event_id=event.id,
            user_id="anna",
            kinds=["create_task"],
            note="Vi måste svara",
            task={"title": "Svara"},
            today=date(2026, 8, 2),
        )
        reopened = reopen_source_event(
            store=tenant.store, event_id=event.id, user_id="björn", note="Fel person"
        )

        # The queue reads exactly as it did before.
        assert reopened.resolution is None
        assert reopened.review_status == "open"
        assert reopened.decided_by is None

        # And the record survives, in the domain model that already existed.
        assert len(reopened.decision_history) == 1
        filed = reopened.decision_history[0]
        assert filed.resolution.decided_by == "anna"
        assert filed.resolution.note == "Vi måste svara"
        assert filed.review_status == "approved"
        assert filed.superseded_by == "björn"
        assert filed.note == "Fel person"
        assert [o.kind for o in filed.resolution.outcomes] == ["create_task"]
        # What it produced is untouched, as it always was.
        assert len(tenant.store.tasks.list_tasks()) == 1

    def test_repeated_settle_and_reopen_accumulates(self, tenant):
        from app.integrations.intake import import_eml
        from app.integrations.resolve import reopen_source_event, resolve_source_event

        event = import_eml(
            store=tenant.store,
            integrations=tenant.store.integrations,
            raw=message(subject="Fråga", body="Vad gäller?"),
            filename="m.eml",
            imported_by="u",
        )
        for i in range(3):
            resolve_source_event(
                store=tenant.store,
                event_id=event.id,
                user_id="anna",
                kinds=["already_handled"],
                note=f"omgång {i}",
                today=date(2026, 8, 2),
            )
            reopen_source_event(store=tenant.store, event_id=event.id, user_id="björn")
        final = tenant.store.integrations.get_source_event(event.id)
        assert [d.resolution.note for d in final.decision_history] == [
            "omgång 0",
            "omgång 1",
            "omgång 2",
        ]

    def test_the_coarse_decision_route_files_it_too(self, api):
        """``POST .../decision`` with ``open`` is a reopen by another name, and
        was the one path that still erased the settlement."""
        from app.integrations.intake import import_eml
        from app.integrations.resolve import resolve_source_event

        store = api.registry.get("brf-a")
        event = import_eml(
            store=store,
            integrations=store.integrations,
            raw=message(subject="Föreläggande", body="Svara inom tio dagar."),
            filename="m.eml",
            imported_by="u",
        )
        resolve_source_event(
            store=store,
            event_id=event.id,
            user_id="anna",
            kinds=["already_handled"],
            note="Klart",
            today=date(2026, 8, 2),
        )
        reply = api.client.post(
            f"/api/brf/brf-a/integrations/source-events/{event.id}/decision",
            json={"status": "open"},
            headers=api.a,
        )
        assert reply.status_code == 200, reply.text
        body = reply.json()
        assert body["resolution"] is None
        assert len(body["decision_history"]) == 1
        assert body["decision_history"][0]["resolution"]["decided_by"] == "anna"


# ---------------------------------------------------------------------------
# Mailbox checkpoints
# ---------------------------------------------------------------------------


class StubMailbox:
    """A mailbox whose fetch can be paused mid-flight, so two fetches genuinely
    overlap rather than merely being started close together."""

    def __init__(self, rows, *, pause: threading.Event | None = None):
        self.rows = rows
        self.pause = pause

    def list_messages(self, *, limit, only_with_attachments, since):
        from app.integrations.graph_mail import MailboxMessage

        out = [
            MailboxMessage(
                id=r["id"],
                subject=r["id"],
                from_address="anna@exempel.se",
                from_display="Anna",
                received_at=r["at"],
                has_attachments=False,
                internet_message_id=f"<{r['id']}@exempel.se>",
                preview="",
            )
            for r in self.rows
            if not since or r["at"] >= since
        ]
        return out[:limit]

    def get_message_mime(self, message_id: str) -> bytes:
        if self.pause is not None:
            self.pause.wait(timeout=10)
        row = next(r for r in self.rows if r["id"] == message_id)
        if row.get("unreadable"):
            raise RuntimeError("brevlådan vägrade")
        return message(
            subject=message_id, body=f"kropp {message_id}", message_id=f"<{message_id}@exempel.se>"
        )


class TestCheckpointsAreMonotonic:
    def test_an_overlapping_slower_fetch_cannot_push_the_mark_back(self, tenant):
        """Controlled schedule rather than a hopeful sleep: the slow fetch is
        held inside ``get_message_mime`` until the fast one has finished and
        written the later mark, then released so it writes the earlier one last.
        Last-writer-wins used to leave the earlier mark, and the queue
        re-presented a fortnight of settled material."""
        from app.integrations.mailbox import fetch_new

        store = tenant.store
        gate = threading.Event()
        slow = StubMailbox([{"id": "old", "at": "2026-05-01T00:00:00Z"}], pause=gate)
        fast = StubMailbox([{"id": "new", "at": "2026-06-01T00:00:00Z"}])

        done = threading.Event()

        def run_slow():
            fetch_new(
                store=store, adapter=slow, provider="p", folder="f", user_id="u"
            )
            done.set()

        thread = threading.Thread(target=run_slow)
        thread.start()
        fetch_new(store=store, adapter=fast, provider="p", folder="f", user_id="u")
        assert (
            store.integrations.get_mailbox_checkpoint("p", "f").high_water_mark
            == "2026-06-01T00:00:00Z"
        )
        gate.set()
        thread.join(timeout=15)
        assert done.is_set(), "den långsamma hämtningen blev aldrig klar"

        final = store.integrations.get_mailbox_checkpoint("p", "f")
        assert final.high_water_mark == "2026-06-01T00:00:00Z"

    def test_many_concurrent_writes_leave_the_latest_mark(self, tenant):
        from app.integrations.models import MailboxCheckpoint

        store = tenant.store
        marks = [f"2026-0{i + 1}-01T00:00:00Z" for i in range(NARROW)]
        for _ in range(REPEATS):
            _, errors = race(
                NARROW,
                lambda i: store.integrations.put_mailbox_checkpoint(
                    MailboxCheckpoint(provider="p", folder="f", high_water_mark=marks[i])
                ),
            )
            assert not any(errors), [e for e in errors if e]
            assert (
                store.integrations.get_mailbox_checkpoint("p", "f").high_water_mark
                == max(marks)
            )

    def test_an_unreadable_message_is_still_offered_again(self, tenant):
        """The other half of the guarantee, and the one a naive "only ever move
        forward" rule would have destroyed: a message that could not be read
        must come back, even though newer messages moved the mark past it."""
        from app.integrations.mailbox import fetch_new

        store = tenant.store
        rows = [
            {"id": "broken", "at": "2026-05-01T00:00:00Z", "unreadable": True},
            {"id": "fine", "at": "2026-06-01T00:00:00Z"},
        ]
        adapter = StubMailbox(rows)
        first = fetch_new(store=store, adapter=adapter, provider="p", folder="f", user_id="u")
        assert [s.code for s in first.skipped] == ["unreadable"]
        checkpoint = store.integrations.get_mailbox_checkpoint("p", "f")
        # The mark moved to the newest message that was taken in...
        assert checkpoint.high_water_mark == "2026-06-01T00:00:00Z"
        # ...and the debt says the broken one is still owed.
        assert checkpoint.retry_from == "2026-05-01T00:00:00Z"
        assert checkpoint.fetch_from() == "2026-05-01T00:00:00Z"

        # It reads again, is taken in this time, and the debt clears.
        rows[0]["unreadable"] = False
        second = fetch_new(store=store, adapter=adapter, provider="p", folder="f", user_id="u")
        assert len(second.imported) == 1
        assert second.imported[0].subject == "broken"
        after = store.integrations.get_mailbox_checkpoint("p", "f")
        assert after.retry_from == ""
        assert after.high_water_mark == "2026-06-01T00:00:00Z"

    def test_a_failed_fetch_does_not_move_the_mark(self, tenant):
        from app.integrations.mailbox import fetch_new, note_fetch_failure

        store = tenant.store
        fetch_new(
            store=store,
            adapter=StubMailbox([{"id": "a", "at": "2026-06-01T00:00:00Z"}]),
            provider="p",
            folder="f",
            user_id="u",
        )
        note_fetch_failure(store=store, provider="p", folder="f", error="ingen anslutning")
        checkpoint = store.integrations.get_mailbox_checkpoint("p", "f")
        assert checkpoint.high_water_mark == "2026-06-01T00:00:00Z"
        assert checkpoint.last_error == "ingen anslutning"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class TestTokenRefreshHappensOnce:
    """Both providers *rotate* refresh tokens: redeeming one retires it. Two
    live calls whose access token expires in the same minute — an invoice read
    and a mailbox fetch, the pair an operator triggers together — each saw an
    expired token and each redeemed the refresh token. The second presented one
    the authority had already retired, failed, and marked a working connection
    ``expired``."""

    def _manager(self, tenant, transport):
        from app.integrations.connections import ConnectionManager
        from app.integrations.credentials import Connection, Secrets
        from app.integrations.oauth import PendingLogins

        credentials = tenant.store.integrations.credentials
        credentials.put_connection(
            Connection(
                provider="fortnox",
                tenant_id="brf-a",
                status="connected",
                client_id="klient",
                redirect_uri="https://example.test/callback",
            )
        )
        credentials.write_secrets(
            "fortnox",
            Secrets(
                access_token="gammal",
                refresh_token="refresh-1",
                client_secret="hemlig",
                access_expires_epoch=0.0,  # expired
            ),
        )
        return ConnectionManager(credentials, pending=PendingLogins(), transport=transport)

    def test_concurrent_live_calls_refresh_the_token_once(self, tenant):
        from tests.test_integrations_live import StubTransport

        redeemed: list[str] = []
        lock = threading.Lock()

        def token_endpoint(request):
            presented = request["body"].get("refresh_token", [""])[0]
            with lock:
                redeemed.append(presented)
                if presented != "refresh-1":
                    # What the authority actually does with a retired token.
                    return {"error": "invalid_grant"}
            return {
                "access_token": "ny",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
                "scope": "invoice",
            }

        transport = StubTransport()
        transport.route("POST", "/oauth-v1/token", token_endpoint)
        manager = self._manager(tenant, transport)

        tokens, errors = race(NARROW, lambda _i: manager.access_token("fortnox"))
        assert not any(errors), [e for e in errors if e]
        assert set(tokens) == {"ny"}, tokens
        assert redeemed == ["refresh-1"], (
            f"refresh-token löstes in {len(redeemed)} gånger: {redeemed}"
        )


# ---------------------------------------------------------------------------
# The invariants none of this was allowed to move
# ---------------------------------------------------------------------------


class TestIsolationSurvives:
    def test_concurrent_work_in_two_tenants_never_crosses(self, api):
        """The repairs added shared code paths between domains. This is the
        check that they did not add a shared *collection*."""
        for _ in range(REPEATS):
            payloads = [("brf-a", api.a), ("brf-b", api.b)]
            _, errors = race(
                NARROW,
                lambda i: api.client.post(
                    f"/api/brf/{payloads[i % 2][0]}/tasks",
                    json={"title": f"Uppgift {payloads[i % 2][0]} {i}"},
                    headers=payloads[i % 2][1],
                ).status_code,
            )
            assert not any(errors), [e for e in errors if e]

        a_titles = [
            t["title"]
            for t in api.client.get("/api/brf/brf-a/tasks", headers=api.a).json()["active"]
        ]
        b_titles = [
            t["title"]
            for t in api.client.get("/api/brf/brf-b/tasks", headers=api.b).json()["active"]
        ]
        assert a_titles and b_titles
        assert all("brf-a" in t for t in a_titles)
        assert all("brf-b" in t for t in b_titles)

    def test_another_tenants_resources_are_404_not_403(self, api):
        """404 never became 403 while these routes were being rewritten — a 403
        confirms existence and a 404 does not."""
        made = api.client.post(
            "/api/brf/brf-a/tasks", json={"title": "Hemlig uppgift"}, headers=api.a
        )
        assert made.status_code == 200, made.text
        task_id = made.json()["id"]

        for method, url, body in [
            ("get", "/api/brf/brf-a/tasks", None),
            ("post", f"/api/brf/brf-a/tasks/{task_id}/comment", {"note": "hej"}),
            ("post", f"/api/brf/brf-a/tasks/{task_id}", {"note": "hej"}),
            ("get", "/api/brf/brf-a/watches", None),
            ("get", "/api/brf/brf-a/integrations/intake", None),
        ]:
            reply = getattr(api.client, method)(
                url, headers=api.b, **({"json": body} if body else {})
            )
            assert reply.status_code == 404, f"{method} {url} -> {reply.status_code}"

    def test_an_unknown_id_inside_ones_own_tenant_is_404(self, api):
        for url, body in [
            ("/api/brf/brf-a/tasks/finns-inte/comment", {"note": "hej"}),
            ("/api/brf/brf-a/watches/finns-inte/decision", {"status": "approved"}),
            ("/api/brf/brf-a/integrations/source-events/finns-inte/reopen", None),
            (
                "/api/brf/brf-a/integrations/findings/finns-inte/decision",
                {"status": "approved"},
            ),
        ]:
            reply = api.client.post(url, headers=api.a, **({"json": body} if body else {}))
            assert reply.status_code == 404, f"{url} -> {reply.status_code} {reply.text}"

    def test_a_member_still_cannot_write(self, api):
        """The mutators moved; the authorisation did not."""
        made = api.client.post(
            "/api/brf/brf-a/tasks", json={"title": "Uppgift"}, headers=api.a
        ).json()
        reply = api.client.post(
            f"/api/brf/brf-a/tasks/{made['id']}/comment",
            json={"note": "hej"},
            headers=api.member_a,
        )
        assert reply.status_code == 403


class TestLockOrderingHoldsUnderMixedLoad:
    """The repairs introduced nested locks that were not nested before —
    ``import_eml`` and ``resolve`` now hold ``integrations.lock`` across
    ``Store.add_document`` and across task and watch writes. That is safe only
    because the order is always the same: a domain store's lock before
    ``Store.lock``, never after. This is the test that would hang if somebody
    later inverted it."""

    def test_every_write_path_at_once_completes(self, api):
        from app.integrations.intake import DuplicateSourceEvent, import_eml
        from app.integrations.resolve import resolve_source_event
        from app.watches.models import Watch

        store = api.registry.get("brf-a")
        task_id = api.client.post(
            "/api/brf/brf-a/tasks", json={"title": "Uppgift"}, headers=api.a
        ).json()["id"]
        store.watches.add_watch(
            Watch(
                id="w-mixed",
                tenant_id="brf-a",
                kind="inspection",
                status="approved",
                title="Besiktning 2026-03-01",
                due_date="2026-03-01",
                derived_due_date="2026-03-01",
                derivation="test",
                recurrence="yearly",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        seeded = import_eml(
            store=store,
            integrations=store.integrations,
            raw=message(subject="Seed", body="text", message_id="<seed@x.se>"),
            filename="seed.eml",
            imported_by="u",
        )

        def work(i: int):
            which = i % 6
            if which == 0:
                return api.client.post(
                    f"/api/brf/brf-a/tasks/{task_id}/comment",
                    json={"note": f"n{i}"},
                    headers=api.a,
                ).status_code
            if which == 1:
                return api.client.post(
                    "/api/brf/brf-a/watches/w-mixed/decision",
                    json={"status": "done"},
                    headers=api.a,
                ).status_code
            if which == 2:
                try:
                    return import_eml(
                        store=store,
                        integrations=store.integrations,
                        raw=message(
                            subject=f"Nytt {i}", body="text", message_id=f"<m{i}@x.se>"
                        ),
                        filename=f"m{i}.eml",
                        imported_by="u",
                    ).id
                except DuplicateSourceEvent:
                    return "dup"
            if which == 3:
                return resolve_source_event(
                    store=store,
                    event_id=seeded.id,
                    user_id="anna",
                    kinds=["already_handled"],
                    note="klart",
                    today=date(2026, 8, 2),
                ).id
            if which == 4:
                return api.client.get(
                    "/api/brf/brf-a/integrations/intake", headers=api.a
                ).status_code
            return api.client.post(
                f"/api/brf/brf-a/integrations/source-events/{seeded.id}/triage",
                headers=api.a,
            ).status_code

        # A deadlock here is a hang, not an exception, so the assertion that
        # matters is that every thread finished at all.
        barrier = threading.Barrier(WIDE)
        done = [False] * WIDE
        errors: list = [None] * WIDE

        def run(i: int) -> None:
            barrier.wait()
            try:
                work(i)
            except BaseException as exc:  # noqa: BLE001
                errors[i] = exc
            finally:
                done[i] = True

        threads = [threading.Thread(target=run, args=(i,), daemon=True) for i in range(WIDE)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert all(done), (
            "minst en tråd blev aldrig klar — trolig låsordningsinversion: "
            f"{[i for i, d in enumerate(done) if not d]}"
        )
        assert not any(errors), [e for e in errors if e]


class TestReadsDoNotWrite:
    def test_reading_the_queue_and_the_boards_creates_no_records(self, api):
        """A read that writes is how a "just looking" GET ends up owning data.
        The invoice workspace was repaired for this once; these are its
        neighbours."""
        store = api.registry.get("brf-a")
        for url in (
            "/api/brf/brf-a/tasks",
            "/api/brf/brf-a/watches",
            "/api/brf/brf-a/integrations/intake",
            "/api/brf/brf-a/integrations/source-events",
            "/api/brf/brf-a/integrations/findings",
            "/api/brf/brf-a/invoices",
        ):
            assert api.client.get(url, headers=api.a).status_code == 200, url

        assert store.tasks.list_tasks() == []
        assert store.watches.list_watches() == []
        assert store.integrations.list_source_events() == []
        assert store.integrations.list_findings() == []
        assert store.integrations.list_invoice_cases() == []
        assert store.integrations.list_analysis_runs() == []

    def test_reads_are_stable_under_concurrent_readers(self, api):
        _, errors = race(
            WIDE,
            lambda _i: api.client.get(
                "/api/brf/brf-a/integrations/intake", headers=api.a
            ).status_code,
        )
        assert not any(errors), [e for e in errors if e]
        assert api.registry.get("brf-a").integrations.list_source_events() == []
