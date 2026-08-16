"""Entailment warning after verified citations (not a refusal).

Citation verification proves a quote is verbatim in the document. The
numeric gate checks that numbers in the prose appear in those quotes.
Neither checks whether the answer *follows from* the quotes. BRF-1 R1
is the motivating case: the quote is real, the numbers (none) pass, and
the sentence reverses the source's meaning.

This step runs LettuceDetect (MIT, token classification on
(context, question, answer); RAGTruth example-level F1 79.22 % vs 63.4 %
for GPT-4-turbo) against the accepted quotes only. It never refuses.
False-positive rate on real Swedish cases is measured before the warning
may become a gate.

Published LettuceDetect checkpoints cover English, German, French,
Spanish, Italian, Polish, Chinese, Hungarian — not Swedish. The product
uses the German EuroBERT-210M head on a multilingual encoder, on CPU so
it does not contend with llama-server. If that is too weak on Swedish,
the measurement says so with numbers; the detector is not swapped on
feeling.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re

logger = logging.getLogger("brf.entailment")

DEFAULT_MODEL = "KRLabsOrg/lettucedect-210m-eurobert-de-v1"
DEFAULT_LANG = "de"
DEFAULT_MIN_CONFIDENCE = 0.5
WARNING_TEXT = "Delar av svaret följer inte av de citerade källorna."

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_detector = None


@dataclass(frozen=True)
class ClaimSentence:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class UnsupportedClaim:
    sentence: str
    start: int
    end: int
    confidence: float
    spans: tuple[str, ...]


@dataclass(frozen=True)
class EntailmentResult:
    ok: bool
    skipped: bool
    unsupported: tuple[UnsupportedClaim, ...]
    reason: str = ""


def model_name() -> str:
    return os.environ.get("BRF_ENTAILMENT_MODEL", DEFAULT_MODEL)


def model_lang() -> str:
    return os.environ.get("BRF_ENTAILMENT_LANG", DEFAULT_LANG)


def entailment_enabled() -> bool:
    flag = os.environ.get("BRF_ENTAILMENT", "auto").strip().lower()
    if flag in ("0", "false", "off", "no"):
        return False
    if flag in ("1", "true", "on", "yes"):
        return True
    return entailment_available()


def entailment_available() -> bool:
    """Deps import and weights already cached — do not download on ask()."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        from lettucedetect.models.inference import HallucinationDetector  # noqa: F401
    except ImportError:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(model_name(), "config.json")
        return isinstance(cached, str)
    except Exception:
        return False


def claim_sentences(answer: str) -> list[ClaimSentence]:
    """Split the answer into claim sentences with original character offsets."""
    text = answer.strip()
    if not text:
        return []
    # Work on the stripped view but map back if leading whitespace was removed.
    offset = answer.find(text)
    if offset < 0:
        offset = 0
    parts = _SENTENCE_SPLIT.split(text)
    sentences: list[ClaimSentence] = []
    cursor = 0
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        rel = text.find(piece, cursor)
        if rel < 0:
            rel = cursor
        start = offset + rel
        end = start + len(piece)
        cursor = rel + len(piece)
        sentences.append(ClaimSentence(start=start, end=end, text=piece))
    return sentences


def format_warning(result: EntailmentResult) -> str | None:
    if result.skipped or result.ok or not result.unsupported:
        return None
    return WARNING_TEXT


def check_entailment(
    answer: str,
    quotes: list[str],
    question: str,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> EntailmentResult:
    """Whether each claim sentence follows from the accepted quotes.

    Context is the verified citation quotes, never rejected citations,
    never the rest of the chunk, never the document filename.
    """
    if not entailment_enabled():
        return EntailmentResult(True, True, (), "disabled")
    if not answer.strip():
        return EntailmentResult(True, True, (), "empty_answer")
    support = [q.strip() for q in quotes if q and q.strip()]
    if not support:
        return EntailmentResult(True, True, (), "no_quotes")

    sentences = claim_sentences(answer)
    if not sentences:
        return EntailmentResult(True, True, (), "no_sentences")

    try:
        spans = _predict_spans(support, question, answer, min_confidence)
    except Exception:
        logger.exception("Entailment-kontrollen misslyckades — hoppar över")
        return EntailmentResult(True, True, (), "error")

    flagged: list[UnsupportedClaim] = []
    for sentence in sentences:
        overlapping = [
            span
            for span in spans
            if span["end"] > sentence.start and span["start"] < sentence.end
        ]
        if not overlapping:
            continue
        confidence = max(float(span.get("confidence") or 0.0) for span in overlapping)
        flagged.append(
            UnsupportedClaim(
                sentence=sentence.text,
                start=sentence.start,
                end=sentence.end,
                confidence=confidence,
                spans=tuple(str(span.get("text") or "") for span in overlapping),
            )
        )
    if not flagged:
        return EntailmentResult(True, False, (), "supported")
    logger.info(
        "Entailment-varning: %d av %d påståenden följer inte av citaten",
        len(flagged),
        len(sentences),
    )
    return EntailmentResult(False, False, tuple(flagged), "unsupported")


def _resolve_device() -> str:
    return os.environ.get("BRF_ENTAILMENT_DEVICE", "cpu")


def _load_detector():
    global _detector
    if _detector is not None:
        return _detector
    from lettucedetect.models.inference import HallucinationDetector

    name = model_name()
    lang = model_lang()
    device = _resolve_device()
    logger.info("Laddar LettuceDetect %s lang=%s device=%s", name, lang, device)
    _detector = HallucinationDetector(
        method="transformer",
        model_path=name,
        lang=lang,
        device=device,
        trust_remote_code=True,
    )
    return _detector


def _default_predict_spans(
    quotes: list[str],
    question: str,
    answer: str,
    min_confidence: float,
) -> list[dict]:
    detector = _load_detector()
    predictions = detector.predict(
        context=quotes,
        question=question,
        answer=answer,
        output_format="spans",
        min_confidence=min_confidence,
    )
    return list(predictions or [])


# Scoring seam for tests: monkeypatch this name without loading weights.
_predict_spans = _default_predict_spans
