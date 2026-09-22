"""Shared pytest fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest

from quizzer.models import Flashcard

DeckWriter = Callable[[Any], Path]


@pytest.fixture
def sample_cards() -> list[Flashcard]:
    """Three simple cards: A, B, C."""
    return [
        Flashcard("DNS", "Domain Name System"),
        Flashcard("TLS", "Transport Layer Security"),
        Flashcard("SSH", "Secure Shell"),
    ]


@pytest.fixture
def write_deck(tmp_path: Path) -> DeckWriter:
    """Return a helper that writes JSON (or raw text) to a temp deck file."""
    counter = iter(range(1000))

    def _write(content: Any) -> Path:
        path = tmp_path / f"deck_{next(counter)}.json"
        text = content if isinstance(content, str) else json.dumps(content)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


class ScriptedInput:
    """Fake ``input()`` that replays answers and records prompts.

    Items may be strings (returned) or exception instances (raised), which
    lets tests simulate Ctrl+C (``KeyboardInterrupt``) and Ctrl+D
    (``EOFError``).
    """

    def __init__(self, answers: Iterable[str | BaseException]) -> None:
        self._answers: Iterator[str | BaseException] = iter(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        try:
            item = next(self._answers)
        except StopIteration:
            raise EOFError from None
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def scripted() -> Callable[[Iterable[str | BaseException]], ScriptedInput]:
    """Factory fixture for ``ScriptedInput``."""
    return ScriptedInput
