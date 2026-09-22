"""Tests for the Flashcard model and answer normalisation."""

from __future__ import annotations

import pytest

from quizzer.models import Flashcard, normalize_answer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DNS", "dns"),
        ("  Domain   Name\tSystem  ", "domain name system"),
        ("", ""),
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),  # casefold, not just lower()
    ],
)
def test_normalize_answer(raw: str, expected: str) -> None:
    assert normalize_answer(raw) == expected


def test_is_correct_is_case_insensitive() -> None:
    card = Flashcard("DNS", "Domain Name System")
    assert card.is_correct("domain name system")
    assert card.is_correct("DOMAIN NAME SYSTEM")
    assert card.is_correct("  Domain  Name System ")


def test_is_correct_rejects_wrong_and_blank_answers() -> None:
    card = Flashcard("DNS", "Domain Name System")
    assert not card.is_correct("Domain Name Server")
    assert not card.is_correct("")
    assert not card.is_correct("   ")


def test_is_correct_accepts_alternatives() -> None:
    card = Flashcard("dict", "dict", alternatives=("dictionary",))
    assert card.is_correct("Dictionary")
    assert card.is_correct("DICT")
    assert not card.is_correct("list")


def test_flashcard_is_immutable_and_hashable() -> None:
    card = Flashcard("a", "b")
    with pytest.raises(AttributeError):
        card.front = "c"  # type: ignore[misc]
    assert {card: 1}[Flashcard("a", "b")] == 1
