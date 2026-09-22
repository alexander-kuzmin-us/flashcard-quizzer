"""Tests for SessionStats."""

from __future__ import annotations

from quizzer.models import Flashcard
from quizzer.stats import AnswerResult, SessionStats

A = Flashcard("A", "1")
B = Flashcard("B", "2")


def test_empty_session_has_zero_accuracy() -> None:
    stats = SessionStats()
    assert stats.total_questions == 0
    assert stats.accuracy == 0.0
    assert stats.missed_terms == []


def test_accuracy_and_counts() -> None:
    stats = SessionStats()
    for card, ok in [(A, True), (B, False), (B, True), (A, True)]:
        stats.record(AnswerResult(card, "x", ok))
    assert stats.total_questions == 4
    assert stats.correct_count == 3
    assert stats.incorrect_count == 1
    assert stats.accuracy == 75.0


def test_missed_terms_are_unique_and_in_first_miss_order() -> None:
    stats = SessionStats()
    for card, ok in [(B, False), (A, False), (B, False)]:
        stats.record(AnswerResult(card, "x", ok))
    assert stats.missed_terms == ["B", "A"]


def test_to_dict_is_json_ready() -> None:
    stats = SessionStats()
    stats.record(AnswerResult(A, "one", False))
    stats.record(AnswerResult(B, "2", True))
    data = stats.to_dict()
    assert data["accuracy_percent"] == 50.0
    assert data["missed_terms"] == ["A"]
    assert data["answers"][0] == {
        "front": "A",
        "expected": "1",
        "given": "one",
        "correct": False,
    }
