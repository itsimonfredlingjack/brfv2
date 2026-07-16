"""Pluggable LLM providers with one strict JSON answer contract.

Provider order: Anthropic SDK when ANTHROPIC_API_KEY (or an SDK-resolvable
credential) is configured, otherwise the locally authenticated `claude` CLI.
Tests always inject FakeLLM. Force with BRF_LLM=api|cli|fake.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Protocol

ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
        "insufficient_data": {"type": "boolean"},
    },
    "required": ["answer", "citations", "insufficient_data"],
    "additionalProperties": False,
}


class LLMError(RuntimeError):
    pass


class LLMFormatError(LLMError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str: ...


def parse_llm_json(raw: str) -> dict:
    """Parse the answer contract out of possibly-noisy model output."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end <= start:
        raise LLMFormatError(f"Inget JSON-objekt i modellsvaret: {raw[:200]!r}")
    try:
        obj = json.loads(s[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMFormatError(f"Ogiltig JSON i modellsvaret: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMFormatError("Modellsvaret är inte ett JSON-objekt.")

    citations = []
    for item in obj.get("citations") or []:
        if isinstance(item, dict) and isinstance(item.get("chunk_id"), str) and isinstance(item.get("quote"), str):
            citations.append({"chunk_id": item["chunk_id"], "quote": item["quote"]})
    return {
        "answer": obj.get("answer") if isinstance(obj.get("answer"), str) else "",
        "citations": citations,
        "insufficient_data": bool(obj.get("insufficient_data", False)),
    }


class AnthropicProvider:
    name = "anthropic-api"

    def __init__(self) -> None:
        from anthropic import Anthropic

        self.client = Anthropic()

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        )
        if resp.stop_reason == "refusal":
            raise LLMError("Modellen avböjde att svara (refusal).")
        if resp.stop_reason == "max_tokens":
            # Truncated JSON must not be parsed as a complete answer.
            raise LLMError(
                f"Svaret trunkerades vid max_tokens={max_tokens} — höj 'Maximal svarslängd' i inställningarna."
            )
        return "".join(block.text for block in resp.content if block.type == "text")


class ClaudeCLIProvider:
    """Generation via the locally authenticated Claude Code CLI (`claude -p`).

    Lets the demo run on this machine's existing login without an API key.
    """

    name = "claude-cli"
    timeout_s = 300

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        import tempfile

        # The CLI has no output-token cap flag; honor maxResponseLength as a
        # soft instruction so the setting is not silently ignored.
        system = f"{system}\n\nHåll hela svaret under cirka {max_tokens} tokens."
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
            "--max-turns",
            "1",
            # Replace the coding-assistant persona with our grounding contract
            # and drop repo/tool context — this is pure text generation.
            "--system-prompt",
            system,
            "--exclude-dynamic-system-prompt-sections",
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=user.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout_s,
                check=False,
                cwd=tempfile.gettempdir(),  # neutral cwd: no repo pickup
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"claude CLI timeout efter {self.timeout_s}s") from exc
        if proc.returncode != 0:
            raise LLMError(f"claude CLI fel ({proc.returncode}): {proc.stderr.decode()[:300]}")
        try:
            envelope = json.loads(proc.stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude CLI gav ogiltig JSON: {proc.stdout[:200]!r}") from exc
        result = envelope.get("result")
        if not isinstance(result, str):
            raise LLMError(f"claude CLI-svar saknar 'result': {str(envelope)[:200]}")
        return result


class FakeLLM:
    """Scripted provider for tests."""

    name = "fake"

    def __init__(self, responses: list[dict | str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens, "model": model})
        if not self._responses:
            raise LLMError("FakeLLM har inga fler svar.")
        r = self._responses.pop(0)
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


class NoLLMProvider:
    name = "none"

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        raise LLMError("Ingen LLM-leverantör är konfigurerad (sätt ANTHROPIC_API_KEY eller installera claude CLI).")


_provider: LLMProvider | None = None


def pick_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider
    forced = os.environ.get("BRF_LLM", "auto")
    if forced == "fake":
        _provider = FakeLLM([])
    elif forced == "api" or (forced == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        _provider = AnthropicProvider()
    elif forced in ("auto", "cli") and shutil.which("claude"):
        _provider = ClaudeCLIProvider()
    else:
        _provider = NoLLMProvider()
    return _provider
