"""Parser and wiring for the eval-only answer judge. Not a gate."""

import inspect

from app.answer_judge import judge_prompt, parse_verdict
from app.llm import FakeLLM


def test_parse_verdict_three_outcomes():
    assert parse_verdict('{"utfall": "besvarar"}').outcome == "besvarar"
    assert parse_verdict('{"utfall": "besvarar_inte"}').outcome == "besvarar_inte"
    assert parse_verdict('{"utfall": "motsager_citatet"}').outcome == "motsager_citatet"


def test_parse_verdict_unknown_on_garbage():
    result = parse_verdict("inte json")
    assert result.outcome == "okant"
    assert result.reason == "no_json"


def test_prompt_is_question_quotes_answer_only():
    system, user = judge_prompt(
        "Kan vi säga upp avtalet?",
        ["Uppsägningstid på nio månader."],
        "Nej, nio månader.",
    )
    assert "besvarar_inte" in system
    assert "motsager_citatet" in system
    assert user.startswith("FRÅGA:")
    assert "ACCEPTERADE CITAT:" in user
    assert "SVAR:" in user
    assert "Nej, nio månader." in user


def test_judge_answer_is_one_complete_call():
    from app.answer_judge import judge_answer

    fake = FakeLLM(['{"utfall": "besvarar_inte"}'])
    result = judge_answer(
        fake,
        "Kan en boende få en egen reserverad parkeringsplats?",
        ["anvisa de boende en egen plats i garaget då detta strider mot tecknat Mobilitetsavtal"],
        "Hyresgästen förbinder sig att anvisa de boende en egen plats i garaget.",
        model="test",
    )
    assert result.outcome == "besvarar_inte"
    assert len(fake.calls) == 1


def test_ask_does_not_import_answer_judge():
    import app.answer as answer_mod

    src = inspect.getsource(answer_mod)
    assert "answer_judge" not in src
    assert "judge_answer" not in src
