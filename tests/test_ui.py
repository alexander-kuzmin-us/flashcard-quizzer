"""Tests for console rendering and the interactive session loop."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable

import pytest

from quizzer.models import Flashcard
from quizzer.progress import CardRecord
from quizzer.quiz_engine import ModeConfig, QuizEngine, SequentialMode
from quizzer.session import run_quiz
from quizzer.stats import AnswerResult, SessionStats
from quizzer.ui import Color, ConsoleUI, render_table, supports_color
from tests.conftest import ScriptedInput

Scripted = Callable[[Iterable[str | BaseException]], ScriptedInput]


class FakeTTY(io.StringIO):
    """StringIO that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


def make_ui(
    answers: Iterable[str | BaseException] = (), color: bool = False
) -> tuple[ConsoleUI, io.StringIO, io.StringIO, ScriptedInput]:
    out, err = io.StringIO(), io.StringIO()
    fake = ScriptedInput(answers)
    return ConsoleUI(fake, out, err, use_color=color), out, err, fake


# ------------------------------------------------------------------ helpers
def test_render_table_aligns_columns() -> None:
    table = render_table(["A", "Long header"], [["xyz", "1"]])
    lines = table.splitlines()
    assert len({len(line) for line in lines}) == 1
    assert "| xyz | 1           |" in lines


def test_render_table_rejects_ragged_rows() -> None:
    with pytest.raises(ValueError):
        render_table(["A", "B"], [["only one"]])


def test_supports_color_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert supports_color(FakeTTY()) is True
    assert supports_color(FakeTTY(), disabled=True) is False
    assert supports_color(io.StringIO()) is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color(FakeTTY()) is False


# ---------------------------------------------------------------- feedback
def test_feedback_colors_green_and_red() -> None:
    ui, out, _, _ = make_ui(color=True)
    card = Flashcard("DNS", "Domain Name System")
    ui.show_feedback(AnswerResult(card, "domain name system", True))
    ui.show_feedback(AnswerResult(card, "nope", False))
    text = out.getvalue()
    assert f"{Color.GREEN}{Color.BOLD}  Correct!{Color.RESET}" in text
    assert f"{Color.RED}{Color.BOLD}  Incorrect.{Color.RESET}" in text
    assert "The answer is: Domain Name System" in text


def test_no_ansi_codes_when_color_disabled() -> None:
    ui, out, err, _ = make_ui(color=False)
    ui.show_feedback(AnswerResult(Flashcard("a", "b"), "b", True))
    ui.error("bad")
    ui.warn("careful")
    assert "\033[" not in out.getvalue() + err.getvalue()
    assert "Error: bad" in err.getvalue()
    assert "Warning: careful" in err.getvalue()


def test_ask_shows_front_and_returns_input() -> None:
    ui, out, _, fake = make_ui(["my answer"])
    assert ui.ask(Flashcard("DNS", "x"), 2, 5) == "my answer"
    assert "Question 2 (5 remaining)" in out.getvalue()
    assert "DNS" in out.getvalue()
    assert fake.prompts == ["  Your answer: "]


# ----------------------------------------------------------------- summary
def test_summary_table_contains_required_fields() -> None:
    ui, out, _, _ = make_ui()
    stats = SessionStats()
    stats.record(AnswerResult(Flashcard("DNS", "Domain Name System"), "x", False))
    stats.record(AnswerResult(Flashcard("SSH", "Secure Shell"), "secure shell", True))
    ui.show_summary(stats)
    text = out.getvalue()
    assert "| Total Questions | 2     |" in text
    assert "| Accuracy %      | 50.0% |" in text
    assert "Missed terms:" in text
    assert "| DNS  | Domain Name System |" in text
    assert "ended early" not in text


def test_summary_perfect_score_and_early_exit_notice() -> None:
    ui, out, _, _ = make_ui()
    stats = SessionStats()
    stats.record(AnswerResult(Flashcard("a", "b"), "b", True))
    ui.show_summary(stats, reason="exit")
    assert "Quiz ended early." in out.getvalue()
    assert "Perfect score" in out.getvalue()


def test_summary_with_no_answers() -> None:
    ui, out, _, _ = make_ui()
    ui.show_summary(SessionStats(), reason="interrupted")
    assert "No questions were answered." in out.getvalue()
    assert "| Accuracy %      | 0.0%  |" in out.getvalue()


def test_lifetime_stats_sorted_by_misses() -> None:
    ui, out, _, _ = make_ui()
    cards = [Flashcard("A", "1"), Flashcard("B", "2"), Flashcard("C", "3")]
    records = {"A": CardRecord(2, 2), "B": CardRecord(3, 0)}
    ui.show_lifetime_stats("deck.json", cards, records)
    lines = [line for line in out.getvalue().splitlines() if line.startswith("| ")]
    assert [line.split("|")[1].strip() for line in lines[1:]] == ["B", "A", "C"]
    assert "| C    | 0        | 0       | 0      | -        |" in out.getvalue()
    assert "No history yet" not in out.getvalue()


def test_lifetime_stats_without_history() -> None:
    ui, out, _, _ = make_ui()
    ui.show_lifetime_stats("deck.json", [Flashcard("A", "1")], {})
    assert "No history yet" in out.getvalue()


# ------------------------------------------------------------ session loop
def engine_for(cards: list[Flashcard]) -> QuizEngine:
    return QuizEngine(SequentialMode(cards, ModeConfig()))


def test_run_quiz_completes(sample_cards: list[Flashcard]) -> None:
    ui, _, _, _ = make_ui(["domain name system", "wrong", "SECURE SHELL"])
    outcome = run_quiz(engine_for(sample_cards), ui)
    assert outcome.completed
    assert outcome.stats.correct_count == 2
    assert outcome.stats.missed_terms == ["TLS"]


@pytest.mark.parametrize("command", ["exit", "EXIT", "  quit "])
def test_run_quiz_exit_command(sample_cards: list[Flashcard], command: str) -> None:
    ui, _, _, _ = make_ui(["domain name system", command])
    outcome = run_quiz(engine_for(sample_cards), ui)
    assert outcome.reason == "exit"
    assert not outcome.completed
    assert outcome.stats.total_questions == 1


def test_exit_is_accepted_as_answer_when_it_is_correct() -> None:
    cards = [
        Flashcard("Built-in that ends the interpreter", "exit"),
        Flashcard("b", "c"),
    ]
    ui, _, _, _ = make_ui(["exit", "c"])
    outcome = run_quiz(engine_for(cards), ui)
    assert outcome.completed
    assert outcome.stats.correct_count == 2


def test_run_quiz_ctrl_c(sample_cards: list[Flashcard]) -> None:
    ui, _, _, _ = make_ui(["domain name system", KeyboardInterrupt()])
    outcome = run_quiz(engine_for(sample_cards), ui)
    assert outcome.reason == "interrupted"
    assert outcome.stats.total_questions == 1


def test_run_quiz_end_of_input(sample_cards: list[Flashcard]) -> None:
    ui, _, _, _ = make_ui(["domain name system"])
    outcome = run_quiz(engine_for(sample_cards), ui)
    assert outcome.reason == "eof"
