import json
import os

import pytest

from app.llm import FakeLLM, LLMError, LLMFormatError, parse_llm_json


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
