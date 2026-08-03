"""The publication boundary, tested as a boundary rather than asserted as one.

Every test here failed before the fixes they guard. They are separated from
``test_website.py`` because they all check the same single claim from different
sides — *nothing changes what a visitor sees until a human publishes* — and that
claim turned out to be true only of a page's blocks, while its address, its
menu entry, its visibility window, the site's name and the page's very existence
all reached the public instantly, several of them at a model's request.
"""

from __future__ import annotations

import pytest

from app.llm import FakeLLM


@pytest.fixture()
def site(two_tenant_app):
    env = two_tenant_app
    client = env.client
    admin = env.auth_headers("admin-a@a.se", "lösenord-a-admin")

    def post(path: str, payload=None, *, headers=None):
        return client.post(f"/api/brf/brf-a/website{path}", json=payload, headers=headers or admin)

    def get(path: str, *, headers=None):
        return client.get(f"/api/brf/brf-a/website{path}", headers=headers or admin)

    def run(operations, summary="", *, headers=None):
        return post("/commands", {"operations": operations, "summary": summary}, headers=headers)

    started = post("/initialize", {"title": "Startsida"})
    assert started.status_code == 200, started.text
    home_id = started.json()["pages"][0]["id"]

    from types import SimpleNamespace

    return SimpleNamespace(env=env, client=client, admin=admin, post=post, get=get, run=run, home_id=home_id)


def _publish_home(site, heading="Publicerad rubrik"):
    site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
               "props": {"heading": heading}}])
    r = site.post(f"/pages/{site.home_id}/publish", {})
    assert r.status_code == 200, r.text
    return r.json()["revision"]["id"]


def _second_page(site, title="För boende", slug="for-boende"):
    r = site.run([{"command": "create_page", "title": title, "slug": slug}])
    assert r.status_code == 200, r.text
    page_id = [p for p in r.json()["workspace"]["pages"] if p["slug"] == slug][0]["id"]
    site.run([{"command": "update_navigation", "action": "add", "page_id": page_id}])
    site.run([{"command": "insert_block", "page_id": page_id, "type": "TextSection",
               "props": {"heading": "Om huset"}}])
    assert site.post(f"/pages/{page_id}/publish", {}).status_code == 200
    return page_id


def _public(site) -> dict:
    r = site.get("/published")
    assert r.status_code == 200, r.text
    return r.json()


class TestTheDraftCannotReachThePublic:
    def test_renaming_a_page_does_not_move_the_published_address(self, site):
        _publish_home(site)
        assert _public(site)["pages"][0]["slug"] == "start"

        site.run([{"command": "rename_page", "page_id": site.home_id,
                   "title": "Startsidan", "slug": "hem"}])

        # The draft has moved; the published page has not.
        assert _public(site)["pages"][0]["slug"] == "start"
        assert site.get(f"/pages/{site.home_id}").json()["slug"] == "hem"

        site.post(f"/pages/{site.home_id}/publish", {})
        assert _public(site)["pages"][0]["slug"] == "hem"

    def test_the_menu_the_public_sees_is_the_published_one(self, site):
        _publish_home(site)
        page_id = _second_page(site)
        assert [n["page_id"] for n in _public(site)["navigation"]] == [site.home_id, page_id]

        site.run([{"command": "update_navigation", "action": "remove", "page_id": page_id}])
        assert [n["page_id"] for n in _public(site)["navigation"]] == [site.home_id, page_id]

        # It takes a publication to change what a visitor's menu says.
        site.post(f"/pages/{site.home_id}/publish", {})
        assert [n["page_id"] for n in _public(site)["navigation"]] == [site.home_id]

    def test_the_site_name_the_public_sees_is_the_published_one(self, site):
        _publish_home(site)
        published_name = _public(site)["settings"]["name"]

        site.run([{"command": "update_settings", "field": "name", "value": "Ändrat i utkastet"}])
        assert _public(site)["settings"]["name"] == published_name

        site.post(f"/pages/{site.home_id}/publish", {})
        assert _public(site)["settings"]["name"] == "Ändrat i utkastet"

    def test_a_published_page_cannot_be_deleted_out_from_under_the_public(self, site):
        _publish_home(site)
        page_id = _second_page(site)
        assert len(_public(site)["pages"]) == 2

        r = site.run([{"command": "delete_page", "page_id": page_id}])
        assert r.status_code == 422
        assert "avpublicera" in r.json()["detail"].lower()
        assert len(_public(site)["pages"]) == 2

        # Unpublishing is the human act that makes deletion possible.
        assert site.post(f"/pages/{page_id}/unpublish").status_code == 200
        assert site.run([{"command": "delete_page", "page_id": page_id}]).status_code == 200


class TestWhatTheModelCannotReach:
    def _fake(self, monkeypatch, payload):
        monkeypatch.setattr("app.llm._provider", FakeLLM([payload]))

    def test_the_ai_cannot_hide_a_published_page_with_a_publish_window(self, site, monkeypatch):
        _publish_home(site)
        self._fake(monkeypatch, {
            "summary": "Döljer sidan",
            "operations": [{"command": "set_publish_window", "page_id": site.home_id,
                            "starts": "2099-01-01", "ends": ""}],
        })
        r = site.post("/ai", {"instruction": "Dölj startsidan"})
        assert r.json()["applied"] is False
        assert len(_public(site)["pages"]) == 1

    def test_the_ai_cannot_delete_a_published_page(self, site, monkeypatch):
        _publish_home(site)
        page_id = _second_page(site)
        self._fake(monkeypatch, {
            "summary": "Tar bort sidan",
            "operations": [{"command": "delete_page", "page_id": page_id}],
        })
        assert site.post("/ai", {"instruction": "Ta bort sidan"}).json()["applied"] is False
        assert len(_public(site)["pages"]) == 2

    def test_the_ai_may_still_rearrange_the_draft_menu(self, site, monkeypatch):
        """The boundary is publication, not usefulness — the draft is still its workspace."""
        _publish_home(site)
        page_id = _second_page(site)
        self._fake(monkeypatch, {
            "summary": "Flyttar menyposten",
            "operations": [{"command": "update_navigation", "action": "move",
                            "page_id": page_id, "after_page_id": None}],
        })
        r = site.post("/ai", {"instruction": "Lägg För boende först i menyn"})
        assert r.json()["applied"] is True, r.json().get("refusal")
        # Changed in the draft…
        assert [n["page_id"] for n in r.json()["workspace"]["navigation"]] == [page_id, site.home_id]
        # …and not for the public until somebody publishes.
        assert [n["page_id"] for n in _public(site)["navigation"]] == [site.home_id, page_id]


class TestPublishingIsOneLockedStep:
    def test_publishing_cuts_the_draft_as_it_is_on_disk(self, site):
        """The revision is built inside the lock, not from a copy read before it.

        The route used to read the site, build a revision from that draft, and
        only then take the lock — so an edit that landed in between was
        published without ever having been seen, and the operator got a version
        that did not match the canvas they pressed the button on.
        """
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                   "props": {"heading": "Först"}}])
        block = site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Sedan"}])

        revision = site.post(f"/pages/{site.home_id}/publish", {}).json()["revision"]["id"]
        stored = site.get(f"/revisions/{revision}").json()
        assert stored["content"][0]["props"]["heading"] == "Sedan"

    def test_concurrent_publishes_do_not_race_for_a_sequence_number(self, site):
        from concurrent.futures import ThreadPoolExecutor

        _publish_home(site)
        # Eight publish attempts against one page: exactly one has something new
        # to publish, and the rest must be refused rather than mint a duplicate
        # revision number or overwrite a recorded version.
        block = site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Ny text"}])

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [f.result() for f in [
                pool.submit(site.post, f"/pages/{site.home_id}/publish", {}) for _ in range(8)
            ]]
        assert sum(1 for r in results if r.status_code == 200) == 1
        assert all(r.status_code in (200, 409) for r in results), [r.status_code for r in results]

        listed = site.get(f"/pages/{site.home_id}/revisions").json()["revisions"]
        assert [r["seq"] for r in listed] == [2, 1]


class TestHistoryIsAppendOnlyInFact:
    def test_undoing_does_not_rewrite_the_transaction_it_undoes(self, site):
        """`undone_by` is derived at read time, not written back over history.

        Marking the original was a second write that edited a record already on
        disk — in a log this repo calls append-only, and which the append-only
        check could not catch because it compares ids and the id had not changed.
        """
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                       "props": {"heading": "Hej"}}], "La till toppsektion")
        tx = r.json()["transaction"]["id"]

        store = site.env.registry.get("brf-a")
        before = [t.model_dump(mode="json") for t in store.website.site().history]

        assert site.post(f"/transactions/{tx}/undo").status_code == 200

        after = [t.model_dump(mode="json") for t in store.website.site().history]
        # Every stored entry that existed before is byte-for-byte what it was.
        assert after[: len(before)] == before
        assert len(after) == len(before) + 1

        # And the workspace still reports the original as undone.
        history = site.get("").json()["history"]
        original = next(t for t in history if t["id"] == tx)
        assert original["undone_by"]
        assert original["undoable"] is False
        assert any(t["undoes"] == tx for t in history)

    def test_an_undone_change_still_cannot_be_undone_twice(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                       "props": {"heading": "Hej"}}])
        tx = r.json()["transaction"]["id"]
        assert site.post(f"/transactions/{tx}/undo").status_code == 200
        assert site.post(f"/transactions/{tx}/undo").status_code == 409


class TestFabricatedProseCannotBePublished:
    """The hole the numeric gate does not cover, closed at the publication boundary.

    `check_numeric_grounding` catches an invented amount because a number either
    appears in a verified quote or it does not. It cannot catch "Grillning är
    förbjuden i föreningen" — no digit, entirely made up, and it used to be
    labelled `editorial` and published like anything else.

    The product does not pretend to detect that semantically. It marks the text,
    keeps it in the draft, and refuses to publish the page until a person adopts
    it — the same engine-proposes/human-decides asymmetry the rest of the
    product runs on.
    """

    def _fake(self, monkeypatch, payload):
        monkeypatch.setattr("app.llm._provider", FakeLLM([payload]))

    def _write_prose(self, site, monkeypatch, body="<p>Grillning är förbjuden i föreningen.</p>"):
        self._fake(monkeypatch, {
            "summary": "Skrev om reglerna",
            "operations": [{"command": "insert_block", "page_id": site.home_id,
                            "type": "TextSection",
                            "props": {"heading": "Regler", "body": body}}],
        })
        r = site.post("/ai", {"instruction": "Skriv om reglerna"})
        assert r.json()["applied"] is True, r.json().get("refusal")
        return site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]

    def test_ai_prose_without_a_source_is_marked_unverified(self, site, monkeypatch):
        block = self._write_prose(site, monkeypatch)
        assert block["grounding"] == "unverified"
        assert "bekräftas" in block["grounding_label"]

    def test_a_page_with_unverified_prose_will_not_publish(self, site, monkeypatch):
        self._write_prose(site, monkeypatch)
        r = site.post(f"/pages/{site.home_id}/publish", {})
        assert r.status_code == 409
        assert "bekräftas" in r.json()["detail"]
        assert _public(site)["pages"] == []

    def test_confirming_the_text_is_what_lets_it_be_published(self, site, monkeypatch):
        block = self._write_prose(site, monkeypatch)
        assert site.run([{"command": "confirm_block", "page_id": site.home_id,
                          "block_id": block["id"]}]).status_code == 200

        after = site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]
        assert after["grounding"] == "authored"
        assert site.post(f"/pages/{site.home_id}/publish", {}).status_code == 200
        assert len(_public(site)["pages"]) == 1

    def test_rewriting_the_text_is_also_adoption(self, site, monkeypatch):
        block = self._write_prose(site, monkeypatch)
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block["id"],
                   "field": "body", "value": "<p>Grillning är tillåten på gården.</p>"}])
        after = site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]
        assert after["grounding"] == "authored"
        assert site.post(f"/pages/{site.home_id}/publish", {}).status_code == 200

    def test_the_ai_cannot_confirm_its_own_text(self, site, monkeypatch):
        block = self._write_prose(site, monkeypatch)
        self._fake(monkeypatch, {
            "summary": "Bekräftar",
            "operations": [{"command": "confirm_block", "page_id": site.home_id,
                            "block_id": block["id"]}],
        })
        r = site.post("/ai", {"instruction": "Bekräfta texten"})
        assert r.json()["applied"] is False
        assert site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]["grounding"] == "unverified"

    def test_an_ai_written_heading_alone_needs_no_confirmation(self, site, monkeypatch):
        """Proportionate: a label cannot carry a claim, so it does not hold up a page."""
        self._fake(monkeypatch, {
            "summary": "Rubrik",
            "operations": [{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                            "props": {"heading": "Välkommen till föreningen"}}],
        })
        assert site.post("/ai", {"instruction": "Skriv en välkomstrubrik"}).json()["applied"] is True
        block = site.get(f"/pages/{site.home_id}").json()["draft"]["content"][0]
        assert block["grounding"] == "editorial"
        assert site.post(f"/pages/{site.home_id}/publish", {}).status_code == 200

    def test_the_workspace_counts_what_is_waiting_for_a_person(self, site, monkeypatch):
        self._write_prose(site, monkeypatch)
        workspace = site.get("").json()
        assert workspace["counts"]["needs_review"] == 1
        assert workspace["pages"][0]["needs_review"] == 1
