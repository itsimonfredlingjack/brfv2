"""Hosted (third-party) generation providers — the optional half of app.llm.

Everything in this module talks to a model somebody else runs: Anthropic's API
and the locally authenticated `claude` CLI. They are the dev/eval default and
stay fully supported for the web product; nothing here is deprecated.

They live in their own module for one structural reason. The Fedora desktop
delivery must have no code path to a third-party model at all, and "no code
path" has to be a property of the *payload*, not a policy the running program
applies to itself. ops/build-runtime.sh therefore does not copy this file into
the packaged runtime. With the file absent, app.llm's plug-in lookup finds
nothing to register: there is no hosted implementation to import, no key that
selects one, and no provider identifier that can be reported. The exclusion is
verifiable by listing the package, not by reading the branch that would have
chosen it.

Consequently app.llm must never import this module unconditionally, and no
module that ships in the desktop bundle may import it at all — see
ops/forbidden_providers.json, which encodes that rule, and
ops/inspect_payload.py, which enforces it against the built artifact.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

from .llm import ANSWER_SCHEMA, HostedProvider, LLMError

logger = logging.getLogger("brf.llm.hosted")


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
            # Truncated JSON must not be parsed as a complete answer. max_tokens
            # here is the whole envelope budget (answer + citation JSON,
            # answer.py's _CITATION_HEADROOM_TOKENS already added on top of
            # the user's "Maximal svarslängd") — don't blame that setting.
            raise LLMError(
                f"Svaret trunkerades vid den totala svarsbudgeten (max_tokens={max_tokens}, "
                "inkluderar utrymme för källhänvisningar)."
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

        # The CLI has no output-token cap flag; honor the envelope budget
        # (max_tokens, already includes citation headroom) as a soft
        # instruction so it is not silently ignored.
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
        # No finish_reason surfaces here, so truncation is undetectable — out of scope for punch-list #5.
        return result


def _claude_cli_available() -> bool:
    return shutil.which("claude") is not None


# The registration surface app.llm reads. Order is the historical provider
# order: API key first, then the locally authenticated CLI.
#
# `forced` and `auto` are separate on purpose and reproduce the previous
# behaviour exactly: BRF_LLM=api builds the Anthropic client even without a key
# (and degrades to `none` when the SDK rejects it), while BRF_LLM=cli only
# selects the CLI if the binary is actually on PATH.
HOSTED_PROVIDERS: tuple[HostedProvider, ...] = (
    HostedProvider(
        key="api",
        provider_name=AnthropicProvider.name,
        hint="sätt ANTHROPIC_API_KEY",
        forced=lambda: True,
        auto=lambda: bool(os.environ.get("ANTHROPIC_API_KEY")),
        build=AnthropicProvider,
    ),
    HostedProvider(
        key="cli",
        provider_name=ClaudeCLIProvider.name,
        hint="installera claude CLI",
        forced=_claude_cli_available,
        auto=_claude_cli_available,
        build=ClaudeCLIProvider,
    ),
)
