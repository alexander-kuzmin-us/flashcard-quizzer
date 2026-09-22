"""Load and validate flashcard decks from JSON files.

Two JSON layouts are supported:

* Array format::

    [{"front": "DNS", "back": "Domain Name System"}, ...]

* Object format::

    {"cards": [{"front": "DNS", "back": "Domain Name System"}, ...]}

Each card needs non-empty string ``front`` and ``back`` fields and may
optionally carry an ``alternatives`` list of other accepted answers.
Unknown extra keys are ignored so decks can hold notes or tags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quizzer.models import Flashcard
from utils.file_handler import DEFAULT_MAX_BYTES, FileReadError, read_json_file

REQUIRED_FIELDS: tuple[str, ...] = ("front", "back")


class FlashcardLoadError(Exception):
    """Raised when a deck cannot be loaded. The message is user-friendly."""


def load_flashcards(
    path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES
) -> list[Flashcard]:
    """Load and validate a flashcard deck.

    Args:
        path: Path to the JSON deck.
        max_bytes: Maximum accepted file size in bytes.

    Returns:
        The validated flashcards, in file order.

    Raises:
        FlashcardLoadError: If the file is missing, unreadable, malformed,
            or contains invalid cards.
    """
    try:
        raw = read_json_file(path, max_bytes=max_bytes)
    except FileReadError as exc:
        raise FlashcardLoadError(str(exc)) from None
    return parse_flashcards(raw, source=str(path))


def parse_flashcards(raw: Any, source: str = "<data>") -> list[Flashcard]:
    """Validate already-decoded JSON and convert it to flashcards.

    Args:
        raw: Decoded JSON (list of cards, or a dict with a ``cards`` key).
        source: Name used in error messages.

    Returns:
        The validated flashcards.

    Raises:
        FlashcardLoadError: If the structure or any card is invalid.
    """
    entries = _extract_card_list(raw, source)
    if not entries:
        raise FlashcardLoadError(f"'{source}' does not contain any flashcards.")

    cards: list[Flashcard] = []
    seen_fronts: dict[str, int] = {}
    for index, entry in enumerate(entries, start=1):
        card = _parse_card(entry, index, source)
        key = card.front.casefold()
        if key in seen_fronts:
            raise FlashcardLoadError(
                f"Card #{index} in '{source}' repeats the front '{card.front}' "
                f"already used by card #{seen_fronts[key]}. Fronts must be unique."
            )
        seen_fronts[key] = index
        cards.append(card)
    return cards


def _extract_card_list(raw: Any, source: str) -> list[Any]:
    """Return the list of card entries from either supported layout."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "cards" not in raw:
            raise FlashcardLoadError(
                f"'{source}' is a JSON object but has no \"cards\" key. "
                'Expected {"cards": [...]} or a top-level list of cards.'
            )
        cards = raw["cards"]
        if not isinstance(cards, list):
            raise FlashcardLoadError(
                f"The \"cards\" value in '{source}' must be a list, "
                f"not {_json_type(cards)}."
            )
        return cards
    raise FlashcardLoadError(
        f"'{source}' must contain a list of cards or an object with a "
        f'"cards" list, not {_json_type(raw)}.'
    )


def _parse_card(entry: Any, index: int, source: str) -> Flashcard:
    """Validate a single card entry and build a ``Flashcard``."""
    where = f"Card #{index} in '{source}'"
    if not isinstance(entry, dict):
        raise FlashcardLoadError(f"{where} must be an object, not {_json_type(entry)}.")

    missing = [name for name in REQUIRED_FIELDS if name not in entry]
    if missing:
        fields = ", ".join(f'"{name}"' for name in missing)
        raise FlashcardLoadError(f"{where} is missing required field(s): {fields}.")

    values: dict[str, str] = {}
    for name in REQUIRED_FIELDS:
        value = entry[name]
        if not isinstance(value, str):
            raise FlashcardLoadError(
                f'{where}: "{name}" must be text, not {_json_type(value)}.'
            )
        if not value.strip():
            raise FlashcardLoadError(f'{where}: "{name}" must not be empty.')
        values[name] = value.strip()

    alternatives = _parse_alternatives(entry.get("alternatives", []), where)
    return Flashcard(values["front"], values["back"], alternatives)


def _parse_alternatives(value: Any, where: str) -> tuple[str, ...]:
    """Validate the optional ``alternatives`` list."""
    if not isinstance(value, list):
        raise FlashcardLoadError(
            f'{where}: "alternatives" must be a list of text values.'
        )
    result: list[str] = []
    for alt in value:
        if not isinstance(alt, str) or not alt.strip():
            raise FlashcardLoadError(
                f'{where}: every entry in "alternatives" must be non-empty text.'
            )
        result.append(alt.strip())
    return tuple(result)


def _json_type(value: Any) -> str:
    """Describe a decoded JSON value using JSON vocabulary."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__  # pragma: no cover - json never yields others
