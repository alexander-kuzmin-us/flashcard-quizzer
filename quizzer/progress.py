"""Persist per-card history between sessions.

Adaptive mode needs to know which cards the user "previously got wrong".
``ProgressStore`` keeps a small JSON file per deck with attempt, correct
and miss counts for each card, keyed by the card front.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

from quizzer.stats import AnswerResult
from utils.file_handler import FileHandler

logger = logging.getLogger(__name__)

DEFAULT_PROGRESS_DIR = Path.home() / ".flashcard_quizzer"


@dataclass
class CardRecord:
    """Lifetime statistics for one card."""

    attempts: int = 0
    correct: int = 0

    @property
    def misses(self) -> int:
        """Number of incorrect answers."""
        return self.attempts - self.correct

    @property
    def accuracy(self) -> float:
        """Percentage correct, 0.0 if never attempted."""
        return 100.0 * self.correct / self.attempts if self.attempts else 0.0


def progress_filename(deck_path: str | Path) -> str:
    """Build a safe, collision-resistant progress filename for a deck.

    The deck's stem is reduced to ``[A-Za-z0-9_-]`` (so no path traversal
    or odd characters reach the filesystem) and suffixed with a short hash
    of the resolved path, so two ``cards.json`` files in different folders
    get separate histories.

    Args:
        deck_path: Path to the flashcard deck.
    """
    resolved = Path(deck_path).expanduser().resolve()
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", resolved.stem)[:40] or "deck"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}.json"


def _is_count(value: Any) -> TypeGuard[int]:
    """Return ``True`` for non-negative ints (``bool`` is rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class ProgressStore:
    """Load, update and save per-card history for one deck."""

    def __init__(self, deck_path: str | Path, progress_dir: str | Path) -> None:
        """Create a store for ``deck_path`` inside ``progress_dir``.

        Args:
            deck_path: Path to the deck this history belongs to.
            progress_dir: Directory for progress files (created if needed).
        """
        self._handler = FileHandler(progress_dir)
        self._filename = progress_filename(deck_path)
        self.records: dict[str, CardRecord] = {}

    @property
    def path(self) -> Path:
        """Full path of the progress file."""
        return self._handler.data_dir / self._filename

    def load(self) -> list[str]:
        """Load history from disk, tolerating a missing or corrupt file.

        A corrupt progress file must never stop someone from studying, so
        problems are reported as warnings and the history starts fresh.

        Returns:
            Warning messages suitable for showing to the user (may be empty).
        """
        self.records = {}
        try:
            raw = self._handler.load_data(self._filename)
        except RuntimeError as exc:
            logger.warning("Ignoring unreadable progress file: %s", exc)
            return [f"Progress file could not be read and was ignored ({exc})."]

        cards = raw.get("cards", {}) if isinstance(raw, dict) else None
        if not isinstance(cards, dict):
            return ["Progress file has an unexpected format and was ignored."]

        warnings: list[str] = []
        for front, entry in cards.items():
            record = self._parse_record(entry)
            if record is None:
                warnings.append(f"Skipped invalid progress entry for '{front}'.")
                continue
            self.records[str(front)] = record
        return warnings

    @staticmethod
    def _parse_record(entry: Any) -> CardRecord | None:
        """Validate one stored record."""
        if not isinstance(entry, dict):
            return None
        attempts, correct = entry.get("attempts"), entry.get("correct")
        if not _is_count(attempts) or not _is_count(correct):
            return None
        if correct > attempts:
            return None
        return CardRecord(attempts, correct)

    def update(self, results: list[AnswerResult]) -> None:
        """Fold a session's answers into the lifetime records."""
        for result in results:
            record = self.records.setdefault(result.card.front, CardRecord())
            record.attempts += 1
            if result.correct:
                record.correct += 1

    def save(self) -> None:
        """Write the history to disk atomically.

        Raises:
            RuntimeError: If the file cannot be written.
        """
        payload = {
            "version": 1,
            "cards": {
                front: {"attempts": rec.attempts, "correct": rec.correct}
                for front, rec in sorted(self.records.items())
            },
        }
        self._handler.save_data(self._filename, payload)

    def reset(self) -> None:
        """Delete all stored history for this deck."""
        self.records = {}
        self._handler.delete_file(self._filename)

    def miss_counts(self) -> dict[str, int]:
        """Return historical misses per card front (input for adaptive mode)."""
        return {front: rec.misses for front, rec in self.records.items()}
