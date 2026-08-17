"""Pluggable LLM providers with one strict JSON answer contract.

This module implements the providers that run entirely on infrastructure the
deployment controls: the self-hosted OpenAI-compatible endpoint (the pilot's
and the desktop product's only generation path — vLLM or Ollama serving
Gemma 4) plus the local test/acceptance providers. Tests always inject FakeLLM.

Providers that talk to a third party live in the optional plug-in module
:mod:`app.llm_hosted` and are discovered at selection time. When that module is
absent — which is how the Fedora desktop delivery is packaged; see
ops/build-runtime.sh — there is nothing to import, nothing to register and no
key that selects a hosted implementation. Nothing in this module names one, so
the packaged code carries no hosted provider identifier either.

Provider order: self-hosted endpoint when BRF_LLM_BASE_URL is set, otherwise
the hosted plug-ins in their declared order, otherwise none.
Force with BRF_LLM=selfhosted|fake|scripted, or with the key of a hosted
plug-in when one is installed.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Protocol

logger = logging.getLogger("brf.llm")

ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    # Common case: one contiguous verbatim quote.
                    "quote": {"type": "string"},
                    # Fragment-fact case (multi-span citation contract): 2-4
                    # short verbatim spans from the SAME chunk (table cell,
                    # heading, letterhead) — each verified independently and
                    # accepted only all-or-nothing (citations.resolve_citation,
                    # citations.MAX_SPANS=4).
                    "quotes": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
                },
                "required": ["chunk_id"],
                "additionalProperties": False,
                # Exactly one of "quote"/"quotes" per citation — matches the
                # model-facing contract (GROUNDING_CONTRACT, answer.py) and
                # parse_llm_json's leniency (llm.py:81-85), which also picks
                # "quotes" over "quote" if a malformed response somehow
                # carried both.
                "oneOf": [{"required": ["quote"]}, {"required": ["quotes"]}],
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


def extract_json_object(raw: str) -> dict:
    """The JSON object in possibly-noisy model output, with nothing dropped.

    Split out of :func:`parse_llm_json` when a second contract appeared: the
    website's AI partner answers with editing *commands*, not with the answer
    envelope, and it needs the same tolerance for fenced blocks and chatter
    around the JSON without the answer-shaped normalization that follows it.
    Two copies of this loop would have been two things to fix the next time a
    model starts wrapping its output differently.
    """
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
    return obj


def parse_llm_json(raw: str) -> dict:
    """Parse the answer contract out of possibly-noisy model output."""
    obj = extract_json_object(raw)

    citations = []
    for item in obj.get("citations") or []:
        if not (isinstance(item, dict) and isinstance(item.get("chunk_id"), str)):
            continue
        # Two model-facing forms: "quote" (one contiguous span, the common
        # case) or "quotes" (a SET of short spans for fragment-facts). Both
        # normalize to a span list; every span is verified independently and
        # the citation is all-or-nothing downstream.
        quotes = item.get("quotes")
        if isinstance(quotes, list) and quotes and all(isinstance(q, str) for q in quotes):
            citations.append({"chunk_id": item["chunk_id"], "quotes": list(quotes)})
        elif isinstance(item.get("quote"), str):
            citations.append({"chunk_id": item["chunk_id"], "quotes": [item["quote"]]})
    return {
        "answer": obj.get("answer") if isinstance(obj.get("answer"), str) else "",
        "citations": citations,
        "insufficient_data": bool(obj.get("insufficient_data", False)),
    }


@dataclass(frozen=True)
class HostedProvider:
    """Registration record for one third-party generation provider.

    The plug-in module owns the whole record — the selection key, the reported
    provider name, the auto-detection rule and the constructor. This module
    only iterates over what it is given, so removing the plug-in removes the
    provider entirely rather than leaving a dangling branch behind.
    """

    key: str
    """Value of BRF_LLM that selects this provider."""

    provider_name: str
    """The ``name`` the constructed provider reports."""

    hint: str
    """What an operator would have to do to make it selectable."""

    forced: Callable[[], bool]
    """May BRF_LLM=<key> select it right now?"""

    auto: Callable[[], bool]
    """Should BRF_LLM=auto select it right now?"""

    build: Callable[[], "LLMProvider"]


def hosted_providers() -> tuple[HostedProvider, ...]:
    """The installed hosted plug-ins, or an empty tuple when none ships.

    A missing plug-in module is the packaged desktop case and is not an error.
    Any *other* import failure is a real defect in an installed plug-in and is
    allowed to propagate rather than being silently downgraded to "no hosted
    providers".
    """

    module_name = f"{__package__}.llm_hosted"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        return ()
    return tuple(module.HOSTED_PROVIDERS)


class OpenAICompatProvider:
    """Self-hosted OpenAI-compatible chat endpoint (vLLM `vllm serve`,
    Ollama's /v1). The pilot's generation path: document text goes only to
    BRF_LLM_BASE_URL, which must point at infrastructure we control.

    Env contract:
      BRF_LLM_BASE_URL   e.g. http://127.0.0.1:8000/v1 via agenntserver/tunnel (required)
      BRF_LLM_MODEL      e.g. gemma4:e12b — overrides settings.aiModel
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
        # Thinking-capable models (e.g. gemma4 on Ollama) burn the whole token
        # budget in a hidden reasoning channel and return empty content on
        # grounding prompts — ask for no reasoning; degrade once if rejected.
        self._reasoning_off = True
        # llama.cpp prefix-KV hint; degrade once if the server 400s on it.
        self._cache_prompt = True

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
        if self._reasoning_off:
            payload["reasoning_effort"] = "none"
        if self._cache_prompt:
            payload["cache_prompt"] = True
        try:
            resp = self._client.post("/chat/completions", json=payload)
        except Exception as exc:
            raise LLMError(
                f"Kunde inte nå LLM-servern ({self.base_url}): {exc.__class__.__name__}"
            ) from exc
        if resp.status_code == 400 and self._reasoning_off and "reasoning" in resp.text:
            logger.warning("LLM-servern avvisade reasoning_effort — fortsätter utan")
            self._reasoning_off = False
            return self.complete(system, user, max_tokens=max_tokens, model=model)
        if resp.status_code == 400 and self._json_mode and "response_format" in resp.text:
            logger.warning("LLM-servern avvisade response_format — fortsätter utan JSON-läge")
            self._json_mode = False
            return self.complete(system, user, max_tokens=max_tokens, model=model)
        if resp.status_code == 400 and self._cache_prompt and "cache_prompt" in resp.text:
            logger.warning("LLM-servern avvisade cache_prompt — fortsätter utan")
            self._cache_prompt = False
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
        timings = data.get("timings")
        if isinstance(timings, dict):
            logger.info(
                "llama.cpp timings prompt_n=%s prompt_ms=%s cache_n=%s",
                timings.get("prompt_n"),
                timings.get("prompt_ms"),
                timings.get("cache_n"),
            )
        if choice.get("finish_reason") == "length":
            if not (isinstance(content, str) and content.strip()):
                # The budget went to a hidden reasoning channel, not the answer —
                # raising maxResponseLength will not help; the model/serving
                # config must disable thinking.
                raise LLMError(
                    "Modellen förbrukade hela svarsbudgeten i en dold resonemangskanal "
                    "och gav inget synligt svar — kontrollera att 'thinking' är avstängt "
                    "för modellen (reasoning_effort/think)."
                )
            # max_tokens here is the whole envelope budget (answer + citation
            # JSON) — the user's "Maximal svarslängd" already has headroom
            # added on top, so don't point back at that setting.
            raise LLMError(
                f"Svaret trunkerades vid den totala svarsbudgeten (max_tokens={max_tokens}, "
                "inkluderar utrymme för källhänvisningar)."
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM-servern gav ett tomt svar.")
        return content


def _is_judge_system(system: str) -> bool:
    return system.startswith("Du är en domare.")


def _is_refusal_help_system(system: str) -> bool:
    return system.startswith("Du säger vilken sorts handling") or system.startswith(
        "Du matchar en handlingssort"
    )


def _is_kind_payload(response: dict | str) -> bool:
    if isinstance(response, dict):
        return "kind" in response and "insufficient_data" not in response
    return False


def _is_match_payload(response: dict | str) -> bool:
    if isinstance(response, dict):
        return "matches" in response and "insufficient_data" not in response
    return False


def _is_judge_payload(response: dict | str) -> bool:
    if isinstance(response, dict):
        return "utfall" in response
    return isinstance(response, str) and '"utfall"' in response


class FakeLLM:
    """Scripted provider for tests."""

    name = "fake"

    def __init__(self, responses: list[dict | str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def non_judge_calls(self) -> list[dict]:
        return [
            c
            for c in self.calls
            if not _is_judge_system(c["system"]) and not _is_refusal_help_system(c["system"])
        ]

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens, "model": model})
        if _is_judge_system(system):
            if self._responses and _is_judge_payload(self._responses[0]):
                r = self._responses.pop(0)
                return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
            return json.dumps({"utfall": "besvarar"}, ensure_ascii=False)
        if system.startswith("Du säger vilken sorts handling"):
            if self._responses and _is_kind_payload(self._responses[0]):
                r = self._responses.pop(0)
                return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
            return json.dumps({"kind": ""}, ensure_ascii=False)
        if system.startswith("Du matchar en handlingssort"):
            if self._responses and _is_match_payload(self._responses[0]):
                r = self._responses.pop(0)
                return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
            return json.dumps({"matches": []}, ensure_ascii=False)
        if not self._responses:
            raise LLMError("FakeLLM har inga fler svar.")
        r = self._responses.pop(0)
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


class DeterministicTestLLM:
    """Deterministic local acceptance provider.

    This provider is deliberately reported as ``fake`` and has no model
    identity. It is only selected explicitly with ``BRF_LLM=scripted``. The
    implementation reads the real retrieval excerpts rendered by answer.py,
    picks the sentence with the strongest question-term overlap, and cites
    that sentence through the normal alias contract. It therefore makes
    generation repeatable without bypassing retrieval, citation resolution,
    persistence, tenant scoping, or any of the answer safety gates.
    """

    name = "fake"
    model = ""

    _STOPWORDS = {
        "att", "det", "den", "detta", "en", "ett", "finns", "för", "från",
        "har", "hur", "i", "med", "och", "om", "på", "ska", "som", "till",
        "vad", "var", "vilka", "vilken", "är",
    }

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[0-9A-Za-zÅÄÖåäö-]+", text.lower())
            if len(token) > 2 and token not in cls._STOPWORDS
        }

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        delay_ms = int(os.environ.get("BRF_SCRIPTED_LLM_DELAY_MS", "0") or 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if _is_judge_system(system):
            return json.dumps({"utfall": "besvarar"}, ensure_ascii=False)
        if system.startswith("Du säger vilken sorts handling"):
            return json.dumps({"kind": ""}, ensure_ascii=False)
        if system.startswith("Du matchar en handlingssort"):
            return json.dumps({"matches": []}, ensure_ascii=False)

        question_match = re.search(r"^FRÅGA:\s*(.*?)\n\nUTDRAG:", user, re.DOTALL)
        if not question_match:
            question_match = re.search(r"\n\nFRÅGA:\s*(.*?)\Z", user, re.DOTALL)
        question = question_match.group(1).strip() if question_match else ""
        question_terms = self._terms(question)
        excerpts = re.findall(
            r"\[(K\d+)\] \([^\n]*\)\n(.*?)(?=\n---\n|\n\nFRÅGA:|\Z)",
            user,
            re.DOTALL,
        )

        best: tuple[int, str, str] | None = None
        for alias, excerpt in excerpts:
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", excerpt.strip()):
                sentence = sentence.strip()
                if not sentence:
                    continue
                score = len(question_terms & self._terms(sentence))
                candidate = (score, alias, sentence)
                if best is None or candidate[0] > best[0]:
                    best = candidate

        if best is None or best[0] < 2:
            return json.dumps(
                {
                    "answer": "Dokumenten innehåller inte tillräcklig information för att besvara frågan.",
                    "citations": [],
                    "insufficient_data": True,
                },
                ensure_ascii=False,
            )

        _, alias, sentence = best
        words = sentence.split()
        quote = sentence if len(words) <= 40 else " ".join(words[:40])
        return json.dumps(
            {
                "answer": quote,
                "citations": [{"chunk_id": alias, "quote": quote}],
                "insufficient_data": False,
            },
            ensure_ascii=False,
        )


class NoLLMProvider:
    name = "none"

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        # The remedies are read off the providers this installation actually
        # has, so a delivery that ships no hosted plug-in does not tell its
        # operator to configure one that is not there.
        remedies = ["ange den självhostade modelltjänstens adress (BRF_LLM_BASE_URL)"]
        remedies += [provider.hint for provider in hosted_providers()]
        raise LLMError(f"Ingen LLM-leverantör är konfigurerad ({' eller '.join(remedies)}).")


_provider: LLMProvider | None = None


def reset_provider_cache() -> None:
    """Drop the memoized provider so the next pick re-reads the environment.

    Only the desktop application needs this: its model runtime is configured
    in-app at runtime rather than through the environment the process started
    with, so the cache has to be invalidated when that configuration changes.
    """

    global _provider
    _provider = None


def pick_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider
    forced = os.environ.get("BRF_LLM", "auto")
    if forced == "scripted":
        _provider = DeterministicTestLLM()
    elif forced == "fake":
        _provider = FakeLLM([])
    elif forced == "selfhosted" or (forced == "auto" and os.environ.get("BRF_LLM_BASE_URL")):
        try:
            _provider = OpenAICompatProvider()
        except Exception as exc:
            logger.error("Självhostad LLM kunde inte initieras: %s", exc)
            _provider = NoLLMProvider()
    else:
        # Hosted plug-ins, in the order the plug-in module declares them. An
        # installation without the plug-in iterates over nothing and falls
        # straight through to `none` — there is no key it could have matched.
        for hosted in hosted_providers():
            if not ((forced == hosted.key and hosted.forced()) or (forced == "auto" and hosted.auto())):
                continue
            try:
                _provider = hosted.build()
            except Exception as exc:  # a missing/bad credential must not 500 /api/health
                logger.error("Leverantören %s kunde inte initieras: %s", hosted.provider_name, exc)
                _provider = NoLLMProvider()
            break
        else:
            _provider = NoLLMProvider()
    return _provider
