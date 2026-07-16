import json
import os

import httpx
import pytest

import app.llm as llm_mod
from app.llm import FakeLLM, LLMError, LLMFormatError, OpenAICompatProvider, parse_llm_json


class TestParseLLMJson:
    GOOD = {"answer": "Svar.", "citations": [{"chunk_id": "d:p1:0-9", "quote": "ordagrant"}], "insufficient_data": False}

    def test_clean_json(self):
        assert parse_llm_json(json.dumps(self.GOOD)) == self.GOOD

    def test_fenced_json(self):
        raw = "```json\n" + json.dumps(self.GOOD) + "\n```"
        assert parse_llm_json(raw) == self.GOOD

    def test_prose_wrapped_json(self):
        raw = "Här är svaret:\n" + json.dumps(self.GOOD) + "\nHoppas det hjälper!"
        assert parse_llm_json(raw) == self.GOOD

    def test_no_json_raises(self):
        with pytest.raises(LLMFormatError):
            parse_llm_json("Jag kan tyvärr inte svara på det.")

    def test_broken_json_raises(self):
        with pytest.raises(LLMFormatError):
            parse_llm_json('{"answer": "x", "citations": [')

    def test_malformed_citation_items_dropped(self):
        obj = {"answer": "x", "citations": [{"chunk_id": "a", "quote": "b"}, {"chunk_id": 5}, "junk"], "insufficient_data": False}
        parsed = parse_llm_json(json.dumps(obj))
        assert parsed["citations"] == [{"chunk_id": "a", "quote": "b"}]

    def test_missing_fields_defaulted(self):
        parsed = parse_llm_json('{"answer": "bara svar"}')
        assert parsed == {"answer": "bara svar", "citations": [], "insufficient_data": False}


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
