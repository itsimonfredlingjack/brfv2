"""Eval diagnostic: local model as answer-question judge.

Not a product surface and not a gate. `ask()` does not import this module.
One call, three outcomes, no refusal. The prompt is not tuned against
the 22 hand-labelled BRF-1 answers — that set is the only honest label
set we have. See `docs/evidence/brf1-answer-judge.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .llm import extract_json_object

Verdict = Literal["besvarar", "besvarar_inte", "motsager_citatet", "okant"]

OUTCOMES = ("besvarar", "besvarar_inte", "motsager_citatet")

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
    raw = provider.complete(system, user, max_tokens=64, model=model)
    return parse_verdict(raw)
