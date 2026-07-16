"""Pluggable LLM providers with one strict JSON answer contract.

Provider order: self-hosted OpenAI-compatible endpoint when BRF_LLM_BASE_URL
is set (the pilot's only generation path — vLLM or Ollama serving Gemma 4),
otherwise Anthropic SDK when ANTHROPIC_API_KEY is configured, otherwise the
locally authenticated `claude` CLI. Tests always inject FakeLLM.
Force with BRF_LLM=selfhosted|api|cli|fake.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Protocol

logger = logging.getLogger("brf.llm")

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


class OpenAICompatProvider:
    """Self-hosted OpenAI-compatible chat endpoint (vLLM `vllm serve`,
    Ollama's /v1). The pilot's generation path: document text goes only to
    BRF_LLM_BASE_URL, which must point at infrastructure we control.

    Env contract:
      BRF_LLM_BASE_URL   e.g. http://127.0.0.1:11434/v1  (required)
      BRF_LLM_MODEL      e.g. gemma4:e4b — overrides settings.aiModel
      BRF_LLM_API_KEY    bearer token if the server enforces one (vLLM --api-key)
      BRF_LLM_TIMEOUT_S  request timeout, default 300
    """

    name = "selfhosted"

    def __init__(self, transport=None) -> None:
        import httpx

        base_url = os.environ.get("BRF_LLM_BASE_URL", "").rstrip("/")
        if not base_url:
            raise LLMError("BRF_LLM_BASE_URL saknas — ange den självhostade LLM-serverns adress.")
        self.base_url = base_url
        self.model = os.environ.get("BRF_LLM_MODEL", "")
        self.timeout_s = float(os.environ.get("BRF_LLM_TIMEOUT_S", "300"))
        api_key = os.environ.get("BRF_LLM_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(
            base_url=base_url, headers=headers, timeout=self.timeout_s, transport=transport
        )
        # Ask for JSON mode; degrade gracefully once if the server rejects it.
        self._json_mode = True

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        payload = {
            "model": self.model or model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.post("/chat/completions", json=payload)
        except Exception as exc:
            raise LLMError(
                f"Kunde inte nå LLM-servern ({self.base_url}): {exc.__class__.__name__}"
            ) from exc
        if resp.status_code == 400 and self._json_mode and "response_format" in resp.text:
            logger.warning("LLM-servern avvisade response_format — fortsätter utan JSON-läge")
            self._json_mode = False
            return self.complete(system, user, max_tokens=max_tokens, model=model)
        if resp.status_code != 200:
            logger.error("LLM-servern %s → %d: %s", self.base_url, resp.status_code, resp.text[:300])
            raise LLMError(f"LLM-servern svarade {resp.status_code}.")
        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except Exception as exc:
            raise LLMError(f"Oväntat svar från LLM-servern: {resp.text[:200]!r}") from exc
        if choice.get("finish_reason") == "length":
            raise LLMError(
                f"Svaret trunkerades vid max_tokens={max_tokens} — höj 'Maximal svarslängd' i inställningarna."
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM-servern gav ett tomt svar.")
        return content


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
            # Detail (paths, account info) goes to the server log only.
            logger.error("claude CLI fel (kod %d): %s", proc.returncode, proc.stderr.decode(errors="replace")[:500])
            raise LLMError(f"claude CLI misslyckades (kod {proc.returncode}).")
        try:
            envelope = json.loads(proc.stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude CLI gav ogiltig JSON: {proc.stdout[:200]!r}") from exc
        if envelope.get("is_error"):
            logger.error("claude CLI is_error: subtype=%s result=%s",
                         envelope.get("subtype"), str(envelope.get("result"))[:300])
            raise LLMError("claude CLI rapporterade ett internt fel.")
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
    elif forced == "selfhosted" or (forced == "auto" and os.environ.get("BRF_LLM_BASE_URL")):
        try:
            _provider = OpenAICompatProvider()
        except Exception as exc:
            logger.error("Självhostad LLM kunde inte initieras: %s", exc)
            _provider = NoLLMProvider()
    elif forced == "api" or (forced == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        try:
            _provider = AnthropicProvider()
        except Exception as exc:  # a missing/bad key must not 500 /api/health
            logger.error("Anthropic-klienten kunde inte initieras: %s", exc)
            _provider = NoLLMProvider()
    elif forced in ("auto", "cli") and shutil.which("claude"):
        _provider = ClaudeCLIProvider()
    else:
        _provider = NoLLMProvider()
    return _provider
