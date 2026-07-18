import json
import os

import httpx
import pytest

import app.llm as llm_mod
from app.llm import ANSWER_SCHEMA, FakeLLM, LLMError, LLMFormatError, OpenAICompatProvider, parse_llm_json


class TestParseLLMJson:
    # Model-facing shape: "quote" (string) or "quotes" (list of strings).
    # Internal normalized shape: always {"chunk_id", "quotes": [...]}.
    GOOD = {"answer": "Svar.", "citations": [{"chunk_id": "d:p1:0-9", "quote": "ordagrant"}], "insufficient_data": False}
    NORM = {"answer": "Svar.", "citations": [{"chunk_id": "d:p1:0-9", "quotes": ["ordagrant"]}], "insufficient_data": False}

    def test_clean_json(self):
        assert parse_llm_json(json.dumps(self.GOOD)) == self.NORM

    def test_fenced_json(self):
        raw = "```json\n" + json.dumps(self.GOOD) + "\n```"
        assert parse_llm_json(raw) == self.NORM

    def test_prose_wrapped_json(self):
        raw = "Här är svaret:\n" + json.dumps(self.GOOD) + "\nHoppas det hjälper!"
        assert parse_llm_json(raw) == self.NORM

    def test_no_json_raises(self):
        with pytest.raises(LLMFormatError):
            parse_llm_json("Jag kan tyvärr inte svara på det.")

    def test_broken_json_raises(self):
        with pytest.raises(LLMFormatError):
            parse_llm_json('{"answer": "x", "citations": [')

    def test_malformed_citation_items_dropped(self):
        obj = {"answer": "x", "citations": [{"chunk_id": "a", "quote": "b"}, {"chunk_id": 5}, "junk"], "insufficient_data": False}
        parsed = parse_llm_json(json.dumps(obj))
        assert parsed["citations"] == [{"chunk_id": "a", "quotes": ["b"]}]

    def test_missing_fields_defaulted(self):
        parsed = parse_llm_json('{"answer": "bara svar"}')
        assert parsed == {"answer": "bara svar", "citations": [], "insufficient_data": False}

    def test_quotes_list_parsed(self):
        obj = {"answer": "x", "citations": [{"chunk_id": "K1", "quotes": ["frag ett", "frag två"]}]}
        parsed = parse_llm_json(json.dumps(obj))
        assert parsed["citations"] == [{"chunk_id": "K1", "quotes": ["frag ett", "frag två"]}]

    def test_quotes_wins_over_quote_when_both_present(self):
        obj = {"answer": "x", "citations": [{"chunk_id": "K1", "quote": "gammal", "quotes": ["a", "b"]}]}
        assert parse_llm_json(json.dumps(obj))["citations"] == [{"chunk_id": "K1", "quotes": ["a", "b"]}]

    def test_quotes_with_non_string_element_dropped(self):
        # Structurally malformed — same class as today's dropped items.
        obj = {"answer": "x", "citations": [{"chunk_id": "K1", "quotes": ["a", 5]}, {"chunk_id": "K2", "quotes": []}]}
        assert parse_llm_json(json.dumps(obj))["citations"] == []


def _validate_citation_item(item: dict, schema: dict) -> bool:
    """Minimal structural validator for ANSWER_SCHEMA's citation-item shape
    (Task 6 — jsonschema is not a project dependency; per the task brief,
    this asserts the schema dict's structure directly rather than adding
    one). Covers exactly the keywords this one schema fragment uses:
    properties/required/additionalProperties, array minItems/maxItems, and a
    two-branch oneOf keyed on "required" — not a general JSON Schema engine.
    """
    props = schema["properties"]
    if not isinstance(item, dict):
        return False
    if schema.get("additionalProperties") is False and not set(item) <= set(props):
        return False
    for req in schema.get("required", []):
        if req not in item:
            return False
    if "quote" in item and not isinstance(item["quote"], str):
        return False
    if "quotes" in item:
        q = item["quotes"]
        qschema = props["quotes"]
        if not (isinstance(q, list) and all(isinstance(x, str) for x in q)):
            return False
        if not (qschema["minItems"] <= len(q) <= qschema["maxItems"]):
            return False
    one_of = schema.get("oneOf") or []
    if one_of:
        matches = sum(1 for sub in one_of if all(k in item for k in sub.get("required", [])))
        if matches != 1:
            return False
    return True


class TestAnswerSchemaCitationItem:
    """Task 6: ANSWER_SCHEMA's citation item was extended (additive only) to
    accept "quote": str (unchanged) OR "quotes": array[str] (2..4), so a
    capable model on the Anthropic structured-output path can emit the
    multi-span fragment-fact form. AnthropicProvider is the only consumer of
    this schema."""

    ITEM_SCHEMA = ANSWER_SCHEMA["properties"]["citations"]["items"]

    def test_schema_declares_both_quote_and_quotes_properties(self):
        props = self.ITEM_SCHEMA["properties"]
        assert props["quote"] == {"type": "string"}
        assert props["quotes"]["type"] == "array"
        assert props["quotes"]["minItems"] == 2
        assert props["quotes"]["maxItems"] == 4

    def test_schema_requires_only_chunk_id_unconditionally(self):
        assert self.ITEM_SCHEMA["required"] == ["chunk_id"]

    def test_schema_still_forbids_additional_properties(self):
        assert self.ITEM_SCHEMA["additionalProperties"] is False

    def test_schema_one_of_enforces_exactly_one_of_quote_or_quotes(self):
        one_of = self.ITEM_SCHEMA["oneOf"]
        assert {"required": ["quote"]} in one_of
        assert {"required": ["quotes"]} in one_of
        assert len(one_of) == 2

    def test_fixed_single_span_payload_validates(self):
        item = {"chunk_id": "K1", "quote": "ett ordagrant citat"}
        assert _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_fixed_multi_span_payload_validates(self):
        item = {"chunk_id": "K1", "quotes": ["Organisationsnummer", "769600-1234"]}
        assert _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_four_span_payload_at_the_upper_bound_validates(self):
        item = {"chunk_id": "K1", "quotes": ["a", "b", "c", "d"]}
        assert _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_single_element_quotes_array_is_invalid(self):
        item = {"chunk_id": "K1", "quotes": ["bara ett fragment"]}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_five_element_quotes_array_is_invalid(self):
        item = {"chunk_id": "K1", "quotes": ["a", "b", "c", "d", "e"]}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_both_quote_and_quotes_present_is_invalid(self):
        item = {"chunk_id": "K1", "quote": "x", "quotes": ["a", "b"]}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_neither_quote_nor_quotes_present_is_invalid(self):
        item = {"chunk_id": "K1"}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_missing_chunk_id_is_invalid(self):
        item = {"quote": "x"}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)

    def test_unexpected_extra_property_is_invalid(self):
        item = {"chunk_id": "K1", "quote": "x", "confidence": 0.9}
        assert not _validate_citation_item(item, self.ITEM_SCHEMA)


class TestFakeLLM:
    def test_scripted_responses_and_call_capture(self):
        fake = FakeLLM([{"answer": "a", "citations": [], "insufficient_data": False}])
        out = fake.complete("sys", "user", max_tokens=100, model="m")
        assert json.loads(out)["answer"] == "a"
        assert fake.calls[0]["system"] == "sys"
        with pytest.raises(LLMError):
            fake.complete("sys", "user", max_tokens=100, model="m")


def _ok_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


class TestOpenAICompatProvider:
    def _provider(self, handler, monkeypatch, env_model="gemma4:e4b") -> OpenAICompatProvider:
        monkeypatch.setenv("BRF_LLM_BASE_URL", "http://selfhost.local/v1")
        monkeypatch.setenv("BRF_LLM_MODEL", env_model)
        return OpenAICompatProvider(transport=httpx.MockTransport(handler))

    def test_happy_path_and_request_shape(self, monkeypatch):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_ok_payload('{"answer": "ok"}'))

        p = self._provider(handler, monkeypatch)
        out = p.complete("systemkontrakt", "fråga", max_tokens=500, model="settings-model")
        assert out == '{"answer": "ok"}'
        assert seen["path"] == "/v1/chat/completions"
        body = seen["body"]
        assert body["model"] == "gemma4:e4b"  # env model wins over settings
        assert body["temperature"] == 0
        assert body["max_tokens"] == 500
        assert body["response_format"] == {"type": "json_object"}
        # Thinking-capable models must not spend the budget in a hidden
        # reasoning channel (empty content on grounding prompts).
        assert body["reasoning_effort"] == "none"
        assert body["messages"][0] == {"role": "system", "content": "systemkontrakt"}

    def test_settings_model_used_when_env_model_empty(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["model"] == "settings-model"
            return httpx.Response(200, json=_ok_payload("x"))

        p = self._provider(handler, monkeypatch, env_model="")
        assert p.complete("s", "u", max_tokens=10, model="settings-model") == "x"

    def test_response_format_rejection_degrades_once(self, monkeypatch):
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            bodies.append(body)
            if "response_format" in body:
                return httpx.Response(400, text="unsupported parameter: response_format")
            return httpx.Response(200, json=_ok_payload("utan json-läge"))

        p = self._provider(handler, monkeypatch)
        assert p.complete("s", "u", max_tokens=10, model="m") == "utan json-läge"
        assert len(bodies) == 2 and "response_format" not in bodies[1]
        assert p._json_mode is False  # sticky — no second 400 round-trip next call

    def test_reasoning_effort_rejection_degrades_once(self, monkeypatch):
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            bodies.append(body)
            if "reasoning_effort" in body:
                return httpx.Response(400, text="unsupported parameter: reasoning_effort")
            return httpx.Response(200, json=_ok_payload("utan reasoning-fält"))

        p = self._provider(handler, monkeypatch)
        assert p.complete("s", "u", max_tokens=10, model="m") == "utan reasoning-fält"
        assert len(bodies) == 2 and "reasoning_effort" not in bodies[1]
        assert p._reasoning_off is False  # sticky — no second 400 round-trip next call

    def test_empty_content_at_length_names_reasoning_channel(self, monkeypatch):
        # The real-world failure: thinking model burns the budget invisibly.
        # The error must NOT tell the user to raise maxResponseLength.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
            )

        p = self._provider(handler, monkeypatch)
        with pytest.raises(LLMError, match="resonemangskanal"):
            p.complete("s", "u", max_tokens=10, model="m")

    def test_finish_reason_length_raises(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": '{"trunk'}, "finish_reason": "length"}]}
            )

        p = self._provider(handler, monkeypatch)
        with pytest.raises(LLMError, match="trunkerades"):
            p.complete("s", "u", max_tokens=10, model="m")

    def test_server_error_message_has_no_body_detail(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="secret internal traceback /srv/keys")

        p = self._provider(handler, monkeypatch)
        with pytest.raises(LLMError) as exc:
            p.complete("s", "u", max_tokens=10, model="m")
        assert "500" in str(exc.value) and "secret" not in str(exc.value)

    def test_connection_error_wrapped(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        p = self._provider(handler, monkeypatch)
        with pytest.raises(LLMError, match="Kunde inte nå"):
            p.complete("s", "u", max_tokens=10, model="m")

    def test_missing_base_url_raises(self, monkeypatch):
        monkeypatch.delenv("BRF_LLM_BASE_URL", raising=False)
        with pytest.raises(LLMError, match="BRF_LLM_BASE_URL"):
            OpenAICompatProvider()


class TestPickProviderSelfhosted:
    @pytest.fixture(autouse=True)
    def _reset_provider_cache(self):
        llm_mod._provider = None
        yield
        llm_mod._provider = None

    def test_auto_prefers_selfhosted_when_base_url_set(self, monkeypatch):
        monkeypatch.setenv("BRF_LLM", "auto")
        monkeypatch.setenv("BRF_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-finns-men-ska-inte-väljas")
        assert llm_mod.pick_provider().name == "selfhosted"

    def test_forced_selfhosted_without_base_url_degrades_to_none(self, monkeypatch):
        monkeypatch.setenv("BRF_LLM", "selfhosted")
        monkeypatch.delenv("BRF_LLM_BASE_URL", raising=False)
        assert llm_mod.pick_provider().name == "none"


@pytest.mark.llm
def test_real_provider_smoke():
    """RUN_LLM_TESTS=1 BRF_LLM=auto — verifies the configured real provider
    honors the JSON contract end to end."""
    os.environ.pop("BRF_LLM", None)
    import app.llm as llm_mod

    llm_mod._provider = None
    provider = llm_mod.pick_provider()
    assert provider.name in ("anthropic-api", "claude-cli")
    raw = provider.complete(
        "Du svarar ENDAST med ett JSON-objekt: {\"answer\": string, \"citations\": [], \"insufficient_data\": boolean}.",
        "Svara med answer=\"ok\" och insufficient_data=false.",
        max_tokens=200,
        model="claude-opus-4-8",
    )
    parsed = parse_llm_json(raw)
    assert parsed["answer"]
