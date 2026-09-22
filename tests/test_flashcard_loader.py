"""Data loader tests (required scenarios plus edge cases)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quizzer.data_loader import FlashcardLoadError, load_flashcards, parse_flashcards
from quizzer.models import Flashcard
from tests.conftest import DeckWriter

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------- required tests
def test_load_valid_flashcards_array(write_deck: DeckWriter) -> None:
    path = write_deck(
        [
            {"front": "DNS", "back": "Domain Name System"},
            {"front": "SSH", "back": "Secure Shell"},
        ]
    )
    cards = load_flashcards(path)
    assert cards == [
        Flashcard("DNS", "Domain Name System"),
        Flashcard("SSH", "Secure Shell"),
    ]


def test_load_invalid_json(write_deck: DeckWriter) -> None:
    path = write_deck('[{"front": "DNS", "back": "Domain Name System"')
    with pytest.raises(FlashcardLoadError, match="not valid JSON"):
        load_flashcards(path)


def test_load_missing_required_field(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "DNS"}])
    with pytest.raises(FlashcardLoadError, match=r'Card #1 .* missing .*"back"'):
        load_flashcards(path)


# ------------------------------------------------------------- format coverage
def test_load_valid_flashcards_object_format(write_deck: DeckWriter) -> None:
    path = write_deck({"name": "Net", "cards": [{"front": "TLS", "back": "Transport"}]})
    assert load_flashcards(path) == [Flashcard("TLS", "Transport")]


def test_load_strips_whitespace_and_ignores_extra_keys(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "  DNS ", "back": " Domain ", "tags": ["net"]}])
    assert load_flashcards(path) == [Flashcard("DNS", "Domain")]


def test_load_alternatives(write_deck: DeckWriter) -> None:
    path = write_deck(
        [{"front": "dict", "back": "dict", "alternatives": ["dictionary"]}]
    )
    card = load_flashcards(path)[0]
    assert card.alternatives == ("dictionary",)


@pytest.mark.parametrize("deck", ["glossary.json", "python_basics.json"])
def test_bundled_sample_decks_are_valid(deck: str) -> None:
    cards = load_flashcards(REPO_ROOT / "data" / deck)
    assert len(cards) >= 10


# ------------------------------------------------------------------ error paths
def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FlashcardLoadError, match="File not found"):
        load_flashcards(tmp_path / "does_not_exist.json")


def test_load_missing_front_and_back(write_deck: DeckWriter) -> None:
    path = write_deck([{"question": "x"}])
    with pytest.raises(FlashcardLoadError, match='"front", "back"'):
        load_flashcards(path)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "does not contain any flashcards"),
        ({"cards": []}, "does not contain any flashcards"),
        ({"deck": []}, 'no "cards" key'),
        ({"cards": {"front": "a"}}, "must be a list, not an object"),
        ("just text", "not text"),
        (42, "not a number"),
        (None, "not null"),
        (["not a card"], "must be an object, not text"),
        ([{"front": 1, "back": "x"}], '"front" must be text, not a number'),
        ([{"front": "a", "back": None}], '"back" must be text, not null'),
        ([{"front": "a", "back": True}], "not a boolean"),
        ([{"front": "a", "back": []}], "not a list"),
        ([{"front": "   ", "back": "x"}], '"front" must not be empty'),
        ([{"front": "a", "back": "x", "alternatives": "y"}], "must be a list"),
        ([{"front": "a", "back": "x", "alternatives": [""]}], "non-empty text"),
        ([{"front": "a", "back": "x", "alternatives": [3]}], "non-empty text"),
    ],
)
def test_parse_rejects_invalid_structures(raw: object, message: str) -> None:
    with pytest.raises(FlashcardLoadError, match=message):
        parse_flashcards(raw, source="deck.json")


def test_parse_rejects_duplicate_fronts_case_insensitively() -> None:
    raw = [{"front": "DNS", "back": "a"}, {"front": "dns", "back": "b"}]
    with pytest.raises(FlashcardLoadError, match="Card #2 .* card #1"):
        parse_flashcards(raw)


def test_error_message_names_the_offending_card(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "a", "back": "b"}, {"front": "c", "back": "d"}, {}])
    with pytest.raises(FlashcardLoadError, match="Card #3"):
        load_flashcards(path)
