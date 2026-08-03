"""The website workspace: commands, grounding, publication, isolation.

Built on ``two_tenant_app`` so the isolation claims are tested against a second
association that actually exists, rather than against an id nobody registered.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.llm import FakeLLM


@pytest.fixture()
def site(two_tenant_app):
    """One association with a started website, and the helpers to drive it."""
    env = two_tenant_app
    client = env.client
    admin = env.auth_headers("admin-a@a.se", "lösenord-a-admin")
    member = env.auth_headers("member-a@a.se", "lösenord-a-medlem")
    other = env.auth_headers("admin-b@b.se", "lösenord-b-admin")

    def post(path: str, payload=None, *, headers=None, brf="brf-a"):
        return client.post(
            f"/api/brf/{brf}/website{path}", json=payload, headers=headers or admin
        )

    def get(path: str, *, headers=None, brf="brf-a"):
        return client.get(f"/api/brf/{brf}/website{path}", headers=headers or admin)

    def run(operations, summary="", *, headers=None, brf="brf-a"):
        return post(
            "/commands", {"operations": operations, "summary": summary},
            headers=headers, brf=brf,
        )

    started = post("/initialize", {"title": "Startsida"})
    assert started.status_code == 200, started.text
    home_id = started.json()["pages"][0]["id"]

    from types import SimpleNamespace

    return SimpleNamespace(
        env=env, client=client, admin=admin, member=member, other=other,
        post=post, get=get, run=run, home_id=home_id,
    )


def _blocks(site, page_id=None):
    page_id = page_id or site.home_id
    r = site.get(f"/pages/{page_id}")
    assert r.status_code == 200, r.text
    return r.json()["draft"]["content"]


class TestCommandEngine:
    def test_initialize_is_a_deliberate_act_not_a_side_effect_of_reading(self, two_tenant_app):
        """A read never creates a site — the repo has fixed that shape once already."""
        env = two_tenant_app
        admin = env.auth_headers("admin-a@a.se", "lösenord-a-admin")
        first = env.client.get("/api/brf/brf-a/website", headers=admin)
        assert first.status_code == 200
        assert first.json()["pages"] == []
        # Reading it ten times still leaves nothing behind.
        for _ in range(3):
            env.client.get("/api/brf/brf-a/website", headers=admin)
        assert env.client.get("/api/brf/brf-a/website", headers=admin).json()["pages"] == []

    def test_initialize_twice_is_refused(self, site):
        assert site.post("/initialize", {"title": "Igen"}).status_code == 409

    def test_insert_update_move_and_delete(self, site):
        r = site.run(
            [
                {"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                 "props": {"heading": "Välkommen"}},
                {"command": "insert_block", "page_id": site.home_id, "type": "NewsList",
                 "props": {"heading": "Nyheter"}},
            ],
            "La till två block",
        )
        assert r.status_code == 200, r.text
        assert r.json()["transaction"]["operation_count"] == 2

        content = _blocks(site)
        assert [b["type"] for b in content] == ["Hero", "NewsList"]
        hero, news = content[0]["id"], content[1]["id"]

        assert site.run([
            {"command": "update_text", "page_id": site.home_id, "block_id": hero,
             "field": "heading", "value": "Välkommen hem"}
        ]).status_code == 200
        assert _blocks(site)[0]["props"]["heading"] == "Välkommen hem"

        assert site.run([
            {"command": "move_block", "page_id": site.home_id, "block_id": news, "index": 0}
        ]).status_code == 200
        assert [b["type"] for b in _blocks(site)] == ["NewsList", "Hero"]

        assert site.run([
            {"command": "delete_block", "page_id": site.home_id, "block_id": hero}
        ]).status_code == 200
        assert [b["type"] for b in _blocks(site)] == ["NewsList"]

    def test_move_after_named_block_is_how_a_person_describes_it(self, site):
        site.run([
            {"command": "insert_block", "page_id": site.home_id, "type": "Hero", "props": {"heading": "A"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "NewsList", "props": {"heading": "B"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "ContactCard", "props": {"heading": "C"}},
        ])
        ids = [b["id"] for b in _blocks(site)]
        # "flytta kontaktkortet under nyheterna" — it is already there; move the
        # hero instead, which is the non-trivial direction.
        assert site.run([
            {"command": "move_block", "page_id": site.home_id,
             "block_id": ids[0], "after_block_id": ids[2]}
        ]).status_code == 200
        assert [b["props"]["heading"] for b in _blocks(site)] == ["B", "C", "A"]

    def test_unknown_component_is_refused(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id,
                       "type": "ArbitraryHtml", "props": {}}])
        assert r.status_code == 422
        assert "Okänd blocktyp" in r.json()["detail"]

    def test_unknown_field_is_refused(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                       "props": {"heading": "Hej", "onclick": "alert(1)"}}])
        assert r.status_code == 422
        assert "onclick" in r.json()["detail"]

    def test_unknown_command_names_what_is_allowed(self, site):
        r = site.run([{"command": "execute_sql", "page_id": site.home_id}])
        assert r.status_code == 422
        assert "insert_block" in r.json()["detail"]

    def test_a_whole_page_object_is_not_a_write(self, site):
        """There is no command that takes a page and stores it."""
        r = site.run([{"command": "update_block", "page_id": site.home_id,
                       "block_id": "x", "props": {}, "content": []}])
        assert r.status_code == 422

    def test_singleton_block_cannot_be_added_twice(self, site):
        ops = [{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                "props": {"heading": "Ett"}}]
        assert site.run(ops).status_code == 200
        r = site.run(ops)
        assert r.status_code == 422
        assert "bara en gång" in r.json()["detail"]

    def test_a_failing_command_writes_nothing_from_its_batch(self, site):
        """All or nothing: the good command in front of a bad one does not land."""
        before = _blocks(site)
        r = site.run([
            {"command": "insert_block", "page_id": site.home_id, "type": "TextSection",
             "props": {"heading": "Denna ska inte finnas"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "Nonsense", "props": {}},
        ])
        assert r.status_code == 422
        assert _blocks(site) == before

    def test_empty_change_is_refused_rather_than_recorded(self, site):
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                   "props": {"heading": "Samma"}}])
        block = _blocks(site)[0]["id"]
        r = site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                       "field": "heading", "value": "Samma"}])
        assert r.status_code == 422
        assert "Ingenting ändrades" in r.json()["detail"]


class TestContentSafety:
    def test_script_in_rich_text_is_refused(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                       "props": {"heading": "Hej", "body": "<p>ok</p><script>steal()</script>"}}])
        assert r.status_code == 422
        assert "script" in r.json()["detail"]

    def test_event_handler_is_refused_and_named_as_a_script(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                       "props": {"body": "<p onclick=\"x()\">hej</p>"}}])
        assert r.status_code == 422
        assert "händelsehanterare" in r.json()["detail"]

    def test_javascript_url_is_refused(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                       "props": {"body": '<p><a href="javascript:alert(1)">klicka</a></p>'}}])
        assert r.status_code == 422

    def test_ordinary_editor_output_is_stored_verbatim(self, site):
        body = '<h2 style="text-align: center">Rubrik</h2><p><strong>Fet</strong> och <em>kursiv</em>.</p><ul><li>ett</li></ul>'
        assert site.run([{"command": "insert_block", "page_id": site.home_id,
                          "type": "TextSection", "props": {"body": body}}]).status_code == 200
        assert _blocks(site)[0]["props"]["body"] == body

    def test_image_without_alt_text_is_refused(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "ImageWithText",
                       "props": {"image": {"src": "/media/gard.jpg", "alt": ""}}}])
        assert r.status_code == 422
        assert "alt-text" in r.json()["detail"]

    def test_document_field_only_accepts_this_tenants_documents(self, site):
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "DocumentList",
                       "props": {"documents": [{"document_id": "not-a-real-doc", "label": ""}]}}])
        assert r.status_code == 422
        assert "arkiv" in r.json()["detail"]


class TestUndo:
    def _one(self, site, ops, summary="Ändring"):
        r = site.run(ops, summary)
        assert r.status_code == 200, r.text
        return r.json()["transaction"]["id"]

    def test_undo_restores_a_deleted_block_with_its_id_and_place(self, site):
        self._one(site, [
            {"command": "insert_block", "page_id": site.home_id, "type": "Hero", "props": {"heading": "Ett"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "NewsList", "props": {"heading": "Två"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "ContactCard", "props": {"heading": "Tre"}},
        ])
        before = _blocks(site)
        middle = before[1]["id"]
        tx = self._one(site, [{"command": "delete_block", "page_id": site.home_id, "block_id": middle}])
        assert len(_blocks(site)) == 2

        assert site.post(f"/transactions/{tx}/undo").status_code == 200
        after = _blocks(site)
        assert [b["id"] for b in after] == [b["id"] for b in before]
        assert after[1]["props"]["heading"] == "Två"

    def test_undo_of_a_move_puts_it_back(self, site):
        self._one(site, [
            {"command": "insert_block", "page_id": site.home_id, "type": "Hero", "props": {"heading": "A"}},
            {"command": "insert_block", "page_id": site.home_id, "type": "NewsList", "props": {"heading": "B"}},
        ])
        ids = [b["id"] for b in _blocks(site)]
        tx = self._one(site, [{"command": "move_block", "page_id": site.home_id,
                               "block_id": ids[0], "index": 1}])
        assert [b["id"] for b in _blocks(site)] == [ids[1], ids[0]]
        site.post(f"/transactions/{tx}/undo")
        assert [b["id"] for b in _blocks(site)] == ids

    def test_undo_of_a_text_change_restores_only_that_field(self, site):
        self._one(site, [{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                          "props": {"heading": "Original", "preamble": "Ingress"}}])
        block = _blocks(site)[0]["id"]
        tx = self._one(site, [{"command": "update_block", "page_id": site.home_id, "block_id": block,
                               "props": {"heading": "Ändrad"}}])
        self._one(site, [{"command": "update_block", "page_id": site.home_id, "block_id": block,
                          "props": {"preamble": "Ny ingress"}}])
        site.post(f"/transactions/{tx}/undo")
        props = _blocks(site)[0]["props"]
        assert props["heading"] == "Original"
        # The later change to a different field survives the undo of the earlier one.
        assert props["preamble"] == "Ny ingress"

    def test_undo_of_a_deleted_page_brings_back_its_blocks_and_menu_place(self, site):
        r = site.run([{"command": "create_page", "title": "För boende", "slug": "for-boende"}])
        page_id = [p for p in r.json()["workspace"]["pages"] if p["slug"] == "for-boende"][0]["id"]
        self._one(site, [
            {"command": "update_navigation", "action": "add", "page_id": page_id},
            {"command": "insert_block", "page_id": page_id, "type": "Faq",
             "props": {"heading": "Vanliga frågor"}},
        ])
        tx = self._one(site, [{"command": "delete_page", "page_id": page_id}])
        assert site.get(f"/pages/{page_id}").status_code == 404

        assert site.post(f"/transactions/{tx}/undo").status_code == 200
        restored = site.get(f"/pages/{page_id}")
        assert restored.status_code == 200
        assert [b["type"] for b in restored.json()["draft"]["content"]] == ["Faq"]
        nav = site.get("").json()["navigation"]
        assert any(item["page_id"] == page_id for item in nav)

    def test_undo_is_recorded_not_erased(self, site):
        tx = self._one(site, [{"command": "insert_block", "page_id": site.home_id,
                               "type": "Hero", "props": {"heading": "Hej"}}], "La till toppsektion")
        site.post(f"/transactions/{tx}/undo")
        history = site.get("").json()["history"]
        original = next(t for t in history if t["id"] == tx)
        assert original["undone_by"]
        assert original["undoable"] is False
        assert any(t["undoes"] == tx for t in history)

    def test_the_same_change_cannot_be_undone_twice(self, site):
        tx = self._one(site, [{"command": "insert_block", "page_id": site.home_id,
                               "type": "Hero", "props": {"heading": "Hej"}}])
        assert site.post(f"/transactions/{tx}/undo").status_code == 200
        assert site.post(f"/transactions/{tx}/undo").status_code == 409


class TestPublication:
    def _fill(self, site):
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                   "props": {"heading": "Publicerad rubrik"}}])

    def test_publishing_creates_an_immutable_revision(self, site):
        self._fill(site)
        r = site.post(f"/pages/{site.home_id}/publish", {"note": "Första"})
        assert r.status_code == 200, r.text
        revision_id = r.json()["revision"]["id"]
        assert r.json()["revision"]["seq"] == 1

        # Editing the draft afterwards must not touch what was published.
        block = _blocks(site)[0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Ändrad efteråt"}])

        stored = site.get(f"/revisions/{revision_id}").json()
        assert stored["content"][0]["props"]["heading"] == "Publicerad rubrik"
        published = site.get("/published").json()
        assert published["pages"][0]["content"][0]["props"]["heading"] == "Publicerad rubrik"

    def test_draft_changes_are_reported_as_unpublished(self, site):
        self._fill(site)
        site.post(f"/pages/{site.home_id}/publish", {})
        assert site.get(f"/pages/{site.home_id}").json()["has_unpublished_changes"] is False
        block = _blocks(site)[0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Nytt"}])
        assert site.get(f"/pages/{site.home_id}").json()["has_unpublished_changes"] is True
        assert site.get("").json()["counts"]["unpublished_changes"] == 1

    def test_publishing_the_same_thing_twice_is_refused(self, site):
        self._fill(site)
        assert site.post(f"/pages/{site.home_id}/publish", {}).status_code == 200
        assert site.post(f"/pages/{site.home_id}/publish", {}).status_code == 409

    def test_rollback_republishes_an_earlier_revision_without_rewriting_it(self, site):
        self._fill(site)
        first = site.post(f"/pages/{site.home_id}/publish", {}).json()["revision"]["id"]
        block = _blocks(site)[0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Version två"}])
        second = site.post(f"/pages/{site.home_id}/publish", {}).json()["revision"]["id"]
        assert site.get("/published").json()["pages"][0]["content"][0]["props"]["heading"] == "Version två"

        r = site.post(f"/pages/{site.home_id}/rollback", {"revision_id": first})
        assert r.status_code == 200, r.text
        assert site.get("/published").json()["pages"][0]["content"][0]["props"]["heading"] == "Publicerad rubrik"
        # Both revisions still exist and still say what they said.
        assert site.get(f"/revisions/{second}").json()["content"][0]["props"]["heading"] == "Version två"
        # The draft is untouched by a rollback: going back to what the public saw
        # is not the same decision as discarding what somebody has written.
        assert _blocks(site)[0]["props"]["heading"] == "Version två"

    def test_revisions_are_listed_newest_first(self, site):
        self._fill(site)
        site.post(f"/pages/{site.home_id}/publish", {})
        block = _blocks(site)[0]["id"]
        site.run([{"command": "update_text", "page_id": site.home_id, "block_id": block,
                   "field": "heading", "value": "Två"}])
        site.post(f"/pages/{site.home_id}/publish", {})
        listed = site.get(f"/pages/{site.home_id}/revisions").json()
        assert [r["seq"] for r in listed["revisions"]] == [2, 1]

    def test_unpublished_page_is_absent_from_the_public_site(self, site):
        self._fill(site)
        assert site.get("/published").json()["pages"] == []

    def test_publish_window_hides_a_published_page(self, site):
        self._fill(site)
        site.post(f"/pages/{site.home_id}/publish", {})
        assert len(site.get("/published").json()["pages"]) == 1
        site.run([{"command": "set_publish_window", "page_id": site.home_id,
                   "starts": "2099-01-01", "ends": ""}])
        assert site.get("/published").json()["pages"] == []

    def test_unpublishing_keeps_every_revision(self, site):
        self._fill(site)
        revision = site.post(f"/pages/{site.home_id}/publish", {}).json()["revision"]["id"]
        assert site.post(f"/pages/{site.home_id}/unpublish").status_code == 200
        assert site.get("/published").json()["pages"] == []
        assert site.get(f"/revisions/{revision}").status_code == 200


class TestAiPartner:
    def _fake(self, monkeypatch, payload):
        monkeypatch.setattr("app.llm._provider", FakeLLM([payload]))

    def test_one_response_becomes_one_undoable_transaction(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Ny sida för nya boende",
            "message": "Jag la till sidan och en meny-post.",
            "operations": [
                {"command": "create_page", "title": "Nya boende", "slug": "nya-boende"},
            ],
        })
        r = site.post("/ai", {"instruction": "Skapa en sida för nya boende"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["applied"] is True
        assert body["transaction"]["summary"] == "Ny sida för nya boende"
        assert body["transaction"]["actor"] == "ai"
        assert body["transaction"]["actor_label"] == "AI-ändring"

        tx = body["transaction"]["id"]
        assert any(p["slug"] == "nya-boende" for p in body["workspace"]["pages"])
        assert site.post(f"/transactions/{tx}/undo").status_code == 200
        assert not any(
            p["slug"] == "nya-boende" for p in site.get("").json()["pages"]
        )

    def test_the_ai_cannot_invent_a_component(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Bäddar in",
            "operations": [{"command": "insert_block", "page_id": site.home_id,
                            "type": "RawHtmlEmbed", "props": {"html": "<script>x</script>"}}],
        })
        r = site.post("/ai", {"instruction": "Lägg in en html-widget"})
        assert r.status_code == 200, r.text
        assert r.json()["applied"] is False
        assert "Okänd blocktyp" in r.json()["refusal"]
        assert _blocks(site) == []

    def test_the_ai_cannot_write_a_script_into_rich_text(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Lägger till text",
            "operations": [{"command": "insert_block", "page_id": site.home_id,
                            "type": "TextSection",
                            "props": {"body": "<p>Hej</p><script>fetch('//x')</script>"}}],
        })
        r = site.post("/ai", {"instruction": "Skriv en text"})
        assert r.json()["applied"] is False
        assert _blocks(site) == []

    def test_the_ai_cannot_publish(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Publicerar",
            "operations": [{"command": "publish_page", "page_id": site.home_id}],
        })
        r = site.post("/ai", {"instruction": "Publicera sidan"})
        assert r.json()["applied"] is False
        assert site.get("/published").json()["pages"] == []

    def test_an_unsupported_number_is_refused_and_nothing_is_written(self, site, monkeypatch):
        """The grounding invariant, applied to a blank page.

        Nobody asked a question, so there is no answer to verify — which is
        exactly the situation in which a model invents an amount.
        """
        self._fake(monkeypatch, {
            "summary": "Avgiftshöjning",
            "operations": [{
                "command": "insert_block", "page_id": site.home_id, "type": "ImportantNotice",
                "props": {"heading": "Avgiften höjs",
                          "body": "<p>Årsavgiften höjs med 4,5 procent från 1 januari.</p>"},
            }],
        })
        r = site.post("/ai", {"instruction": "Skriv om avgiften"})
        assert r.json()["applied"] is False
        assert "4,5" in r.json()["refusal"]
        assert _blocks(site) == []

    def test_a_number_the_operator_supplied_is_theirs_to_publish(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Vattenavstängning",
            "operations": [{
                "command": "insert_block", "page_id": site.home_id, "type": "ImportantNotice",
                "props": {"heading": "Vattenavstängning",
                          "body": "<p>Vattnet stängs av 12 mars mellan 08 och 15.</p>",
                          "tone": "warning"},
            }],
        })
        r = site.post("/ai", {
            "instruction": "Skriv ett meddelande om att vattnet stängs av 12 mars mellan 08 och 15"
        })
        assert r.json()["applied"] is True, r.json().get("refusal")
        assert _blocks(site)[0]["props"]["heading"] == "Vattenavstängning"

    def test_text_with_no_claim_is_marked_editorial(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Välkomsttext",
            "operations": [{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                            "props": {"heading": "Välkommen till föreningen"}}],
        })
        assert site.post("/ai", {"instruction": "Skriv en välkomstrubrik"}).json()["applied"] is True
        block = _blocks(site)[0]
        # A heading alone cannot carry a factual claim, so it needs no
        # confirmation — see test_website_publication_boundary.py for the prose
        # case, which does.
        assert block["grounding"] == "editorial"
        assert block["grounding_label"] == "AI-formulerad rubrik"

    def test_grounded_content_keeps_the_citations_it_was_derived_from(self, site, monkeypatch):
        """`grounded_from` runs the ordinary answer pipeline and attaches what it verified."""
        from app.llm import FakeLLM as _F

        # The citation must survive real verification, so it quotes the seeded
        # document verbatim and names a chunk that actually exists.
        store = site.env.registry.get("brf-a")
        chunk_id = next(iter(store.chunks))

        # Two calls: the planner, then the answer pipeline that grounds it.
        monkeypatch.setattr("app.llm._provider", _F([
            {
                "summary": "Om stadgarna",
                "operations": [{
                    "command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                    "props": {"heading": "Ur stadgarna",
                              "body": "<p>Föreningen har en hemlig kod ALFA-XYZZY-111 i sina stadgar.</p>"},
                    "grounded_from": "Vilken kod står i stadgarna?",
                }],
            },
            {
                "answer": "Föreningen har en hemlig kod ALFA-XYZZY-111 i sina stadgar.",
                "citations": [{"chunk_id": chunk_id,
                               "quote": "hemlig kod ALFA-XYZZY-111"}],
                "insufficient_data": False,
            },
        ]))
        r = site.post("/ai", {"instruction": "Skriv vad som står i stadgarna"})
        body = r.json()
        assert body["applied"] is True, body.get("refusal")
        block = _blocks(site)[0]
        assert block["grounding"] == "grounded"
        assert block["sources"], "grundad text ska bära sina källor"
        assert block["sources"][0]["document_name"] == "StadgarA.pdf"

        sources = site.get(f"/blocks/{site.home_id}/{block['id']}/sources").json()
        assert sources["quotes"]

    def test_a_refused_grounding_writes_nothing(self, site, monkeypatch):
        from app.llm import FakeLLM as _F

        monkeypatch.setattr("app.llm._provider", _F([
            {
                "summary": "Om garaget",
                "operations": [{
                    "command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                    "props": {"body": "<p>Garaget kostar 900 kronor i månaden.</p>"},
                    "grounded_from": "Vad kostar en garageplats?",
                }],
            },
            {"answer": "Uppgift saknas.", "citations": [], "insufficient_data": True},
        ]))
        r = site.post("/ai", {"instruction": "Skriv om garaget"})
        assert r.json()["applied"] is False
        assert "dokument svarar inte" in r.json()["refusal"]
        assert _blocks(site) == []

    def test_a_model_that_answers_with_nonsense_changes_nothing(self, site, monkeypatch):
        monkeypatch.setattr("app.llm._provider", FakeLLM(["inte json alls"]))
        r = site.post("/ai", {"instruction": "Gör något"})
        assert r.status_code == 200
        assert r.json()["applied"] is False
        assert _blocks(site) == []

    def test_the_editor_context_reaches_the_model(self, site, monkeypatch):
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "TextSection",
                   "props": {"heading": "Om huset", "body": "<p>En lång text.</p>"}}])
        block = _blocks(site)[0]["id"]
        fake = FakeLLM([{"summary": "Kortade texten", "operations": []}])
        monkeypatch.setattr("app.llm._provider", fake)
        site.post("/ai", {
            "instruction": "Korta den markerade texten och gör den tydligare",
            "page_id": site.home_id, "block_id": block, "field": "body",
            "selected_text": "En lång text.",
        })
        prompt = fake.calls[0]["user"]
        assert f"block_id={block}" in prompt
        assert "Markerat fält: body" in prompt
        assert "En lång text." in prompt

    def test_too_many_operations_are_refused_wholesale(self, site, monkeypatch):
        self._fake(monkeypatch, {
            "summary": "Massor",
            "operations": [
                {"command": "insert_block", "page_id": site.home_id, "type": "TextSection", "props": {}}
                for _ in range(30)
            ],
        })
        r = site.post("/ai", {"instruction": "Fyll sidan"})
        assert r.json()["applied"] is False
        assert _blocks(site) == []


class TestAuthorisationAndIsolation:
    def test_a_member_may_read_but_not_write(self, site):
        assert site.get("", headers=site.member).status_code == 200
        r = site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                       "props": {"heading": "Nej"}}], headers=site.member)
        assert r.status_code == 403

    def test_a_member_cannot_publish(self, site):
        assert site.post(f"/pages/{site.home_id}/publish", {}, headers=site.member).status_code == 403

    def test_another_association_gets_404_not_403(self, site):
        """A 403 would confirm the association exists. A 404 does not."""
        assert site.get("", headers=site.other).status_code == 404
        assert site.get(f"/pages/{site.home_id}", headers=site.other).status_code == 404
        r = site.run([{"command": "delete_page", "page_id": site.home_id}], headers=site.other)
        assert r.status_code == 404

    def test_one_associations_page_id_does_not_exist_in_another(self, site):
        """The isolation is structural: brf-b's store simply has no such page."""
        site.client.post("/api/brf/brf-b/website/initialize", json={"title": "B"},
                         headers=site.other)
        r = site.client.get(f"/api/brf/brf-b/website/pages/{site.home_id}", headers=site.other)
        assert r.status_code == 404

    def test_a_revision_of_another_association_is_not_readable(self, site):
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                   "props": {"heading": "Hemligt"}}])
        revision = site.post(f"/pages/{site.home_id}/publish", {}).json()["revision"]["id"]
        site.client.post("/api/brf/brf-b/website/initialize", json={"title": "B"}, headers=site.other)
        r = site.client.get(f"/api/brf/brf-b/website/revisions/{revision}", headers=site.other)
        assert r.status_code == 404

    def test_signed_out_requests_are_refused(self, site):
        assert site.client.get("/api/brf/brf-a/website").status_code == 401

    def test_deleting_the_tenant_removes_the_website(self, site, tmp_path):
        site.run([{"command": "insert_block", "page_id": site.home_id, "type": "Hero",
                   "props": {"heading": "Borta strax"}}])
        site.post(f"/pages/{site.home_id}/publish", {})
        directory = pathlib.Path(site.env.registry._tenant_dir("brf-a")) / "website"
        assert directory.exists()
        site.env.registry.delete("brf-a")
        assert not directory.exists()


class TestVocabularyLock:
    def test_the_lock_matches_the_vocabulary(self):
        """The backend half of the editor/backend contract.

        The React config is checked against this same file by the frontend's own
        test, so a component that exists on one side and not the other fails a
        build rather than a board member's afternoon.
        """
        from app.website.components import vocabulary

        lock = pathlib.Path(__file__).resolve().parents[1] / "app/website/VOCABULARY.lock.json"
        recorded = json.loads(lock.read_text(encoding="utf-8"))
        assert recorded == json.loads(json.dumps(vocabulary(), ensure_ascii=False)), (
            "Komponentordlistan har ändrats utan att VOCABULARY.lock.json spelats in på nytt. "
            "Kör: make website-vocabulary-lock"
        )

    def test_every_component_has_a_swedish_label_and_a_description(self):
        from app.website.components import COMPONENTS

        for name, spec in COMPONENTS.items():
            assert spec.label and spec.description, name
            for field_name, field in spec.fields.items():
                assert field.label, f"{name}.{field_name}"
