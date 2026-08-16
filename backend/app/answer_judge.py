"""Local model as answer-question judge, after verified citations.

One call, three outcomes. Split on the BRF-1 measurement
(`docs/evidence/brf1-answer-judge.md`):

- ``motsager_citatet`` refuses — R1's class, zero false alarms on 22 answers.
- ``besvarar_inte`` shows the answer with a visible incomplete mark — R8's
  class; do not refuse on it until the label set is larger than 22.
- ``besvarar`` (and unparseable) leaves the answer unchanged.

Never run this without accepted citation quotes. The judge reads refusal
prose as an answer; three of five retrieval refusals were labelled
``besvarar``. It also does not see the document, so wrong-document answers
(R3b, R7b) pass. Document-selection remains a separate control.

The prompt is not tuned against the 22 hand-labelled answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .llm import extract_json_object
from .schemas import AskResponse, CitationOut

Verdict = Literal["besvarar", "besvarar_inte", "motsager_citatet", "okant"]

OUTCOMES = ("besvarar", "besvarar_inte", "motsager_citatet")

INCOMPLETE_MARK = "Svaret kan vara ofullständigt."
JUDGE_MAX_TOKENS = 64
CONTRADICTION_REFUSAL = "Svaret motsäger den citerade källan. Då visar jag det inte."

SYSTEM = (
    "Du är en domare. Du svarar inte på frågan. Du skriver inte om svaret. "
    "Avgör en sak: besvarar SVARET FRÅGAN, givet de accepterade citaten? "
    "Tre utfall, exakt ett: "
    "besvarar — svaret besvarar frågan och strider inte mot citaten; "
    "besvarar_inte — svaret besvarar inte frågan; "
    "motsager_citatet — svaret motsäger det som citaten säger. "
    'Svara med JSON {"utfall": "besvarar"} eller '
    '{"utfall": "besvarar_inte"} eller '
    '{"utfall": "motsager_citatet"}.'
)

_CANON = {
    "besvarar": "besvarar",
    "besvarar_inte": "besvarar_inte",
    "besvarar inte": "besvarar_inte",
    "besvararinte": "besvarar_inte",
    "motsager_citatet": "motsager_citatet",
    "motsäger_citatet": "motsager_citatet",
    "motsager citatet": "motsager_citatet",
    "motsäger citatet": "motsager_citatet",
    "motsagercitatet": "motsager_citatet",
}


@dataclass(frozen=True)
class JudgeResult:
    outcome: Verdict
    raw: str
    reason: str = ""


def is_judge_system(system: str) -> bool:
    return system.startswith("Du är en domare.")


def accepted_quotes(citations: list[CitationOut] | list) -> list[str]:
    out: list[str] = []
    for citation in citations:
        quotes = getattr(citation, "quotes", None) or []
        for quote in quotes:
            if isinstance(quote, str) and quote.strip():
                out.append(quote.strip())
    return out


def should_judge(resp: AskResponse) -> bool:
    """False on refusals and on answers with no accepted citation quotes."""
    if resp.refusal:
        return False
    return bool(accepted_quotes(resp.citations))


def judge_prompt(question: str, quotes: list[str], answer: str) -> tuple[str, str]:
    lines = ["FRÅGA:", question.strip(), "", "ACCEPTERADE CITAT:"]
    cleaned = [q.strip() for q in quotes if q and q.strip()]
    if cleaned:
        for i, quote in enumerate(cleaned, 1):
            lines.append(f"{i}. {quote}")
    else:
        lines.append("(inga)")
    lines.extend(["", "SVAR:", answer.strip()])
    return SYSTEM, "\n".join(lines)


def parse_verdict(raw: str) -> JudgeResult:
    try:
        obj = extract_json_object(raw)
    except Exception:
        return JudgeResult("okant", raw, "no_json")
    value = obj.get("utfall") if isinstance(obj, dict) else None
    if not isinstance(value, str):
        return JudgeResult("okant", raw, "missing_utfall")
    key = value.strip().casefold()
    outcome = _CANON.get(key)
    if outcome is None:
        return JudgeResult("okant", raw, "unknown_utfall")
    return JudgeResult(outcome, raw, "ok")


def judge_answer(provider, question: str, quotes: list[str], answer: str, *, model: str) -> JudgeResult:
    system, user = judge_prompt(question, quotes, answer)
    raw = provider.complete(system, user, max_tokens=JUDGE_MAX_TOKENS, model=model)
    return parse_verdict(raw)
