"""Unit tests for the eval-only LettuceDetect diagnostic.

Never a refusal and never on the ask path. The real weights are not
loaded here — `_predict_spans` is the injection seam.
"""

from app.entailment import (
    WARNING_TEXT,
    check_entailment,
    claim_sentences,
    format_warning,
)


R1_ANSWER = (
    "Hyresgästen förbinder sig att anvisa de boende en egen plats i garaget "
    "då detta strider mot tecknat Mobilitetsavtal."
)
R1_QUOTE = (
    "anvisa de boende en egen plats i garaget då detta strider mot tecknat Mobilitetsavtal"
)
R1_QUESTION = "Kan en boende få en egen reserverad parkeringsplats?"


def test_claim_sentences_keeps_offsets():
    text = "Första meningen. Andra meningen?"
    sentences = claim_sentences(text)
    assert [s.text for s in sentences] == ["Första meningen.", "Andra meningen?"]
    assert text[sentences[0].start : sentences[0].end] == "Första meningen."
    assert text[sentences[1].start : sentences[1].end] == "Andra meningen?"


def test_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("BRF_ENTAILMENT", raising=False)
    called = []

    def boom(*_a, **_k):
        called.append(True)
        raise AssertionError("detector must not run when disabled")

    monkeypatch.setattr("app.entailment._predict_spans", boom)
    result = check_entailment(R1_ANSWER, [R1_QUOTE], R1_QUESTION)
    assert result.skipped and result.ok
    assert called == []
    assert format_warning(result) is None


def test_r1_reversal_is_flagged_when_spans_overlap(monkeypatch):
    monkeypatch.setenv("BRF_ENTAILMENT", "1")

    def fake_spans(quotes, question, answer, min_confidence):
        assert quotes == [R1_QUOTE]
        assert question == R1_QUESTION
        assert answer == R1_ANSWER
        return [{"start": 0, "end": len(answer), "confidence": 0.91, "text": answer}]

    monkeypatch.setattr("app.entailment._predict_spans", fake_spans)
    result = check_entailment(R1_ANSWER, [R1_QUOTE], R1_QUESTION)
    assert not result.ok and not result.skipped
    assert len(result.unsupported) == 1
    assert result.unsupported[0].sentence == R1_ANSWER
    assert format_warning(result) == WARNING_TEXT


def test_supported_sentence_is_not_flagged(monkeypatch):
    monkeypatch.setenv("BRF_ENTAILMENT", "1")
    monkeypatch.setattr("app.entailment._predict_spans", lambda *_a, **_k: [])
    result = check_entailment(
        "Nej, avtalet har en uppsägningstid på nio månader.",
        ["Avtalet gäller från och med 2022-04-01 och gäller tom 2047-03-31 med en uppsägningstid på nio månader."],
        "Kan vi säga upp parkeringsavtalet med en månads varsel?",
    )
    assert result.ok and not result.skipped
    assert result.unsupported == ()


def test_empty_quotes_skip_without_calling_detector(monkeypatch):
    monkeypatch.setenv("BRF_ENTAILMENT", "1")

    def boom(*_a, **_k):
        raise AssertionError("no quotes means nothing to entail against")

    monkeypatch.setattr("app.entailment._predict_spans", boom)
    result = check_entailment("Ett påstående.", [], "Fråga?")
    assert result.skipped and result.reason == "no_quotes"


def test_detector_error_skips_instead_of_raising(monkeypatch):
    monkeypatch.setenv("BRF_ENTAILMENT", "1")

    def boom(*_a, **_k):
        raise RuntimeError("cuda exploded")

    monkeypatch.setattr("app.entailment._predict_spans", boom)
    result = check_entailment(R1_ANSWER, [R1_QUOTE], R1_QUESTION)
    assert result.skipped and result.ok
    assert format_warning(result) is None
