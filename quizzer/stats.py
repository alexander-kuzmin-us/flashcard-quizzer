"""Answer results and session statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quizzer.models import Flashcard


@dataclass(frozen=True)
class AnswerResult:
    """The outcome of answering one question.

    Attributes:
        card: The card that was asked.
        given: The user's raw answer.
        correct: Whether the answer was accepted.
    """

    card: Flashcard
    given: str
    correct: bool


@dataclass
class SessionStats:
    """Accumulates results for a single quiz session."""

    results: list[AnswerResult] = field(default_factory=list)

    def record(self, result: AnswerResult) -> None:
        """Add one answer result to the session."""
        self.results.append(result)

    @property
    def total_questions(self) -> int:
        """Number of questions answered (repeats in adaptive mode count)."""
        return len(self.results)

    @property
    def correct_count(self) -> int:
        """Number of correct answers."""
        return sum(1 for result in self.results if result.correct)

    @property
    def incorrect_count(self) -> int:
        """Number of incorrect answers."""
        return self.total_questions - self.correct_count

    @property
    def accuracy(self) -> float:
        """Percentage of correct answers, 0.0 when nothing was answered."""
        if not self.results:
            return 0.0
        return 100.0 * self.correct_count / self.total_questions

    @property
    def missed_terms(self) -> list[str]:
        """Fronts of cards answered incorrectly at least once, first-miss order."""
        seen: dict[str, None] = {}
        for result in self.results:
            if not result.correct:
                seen.setdefault(result.card.front, None)
        return list(seen)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the session."""
        return {
            "total_questions": self.total_questions,
            "correct": self.correct_count,
            "incorrect": self.incorrect_count,
            "accuracy_percent": round(self.accuracy, 1),
            "missed_terms": self.missed_terms,
            "answers": [
                {
                    "front": r.card.front,
                    "expected": r.card.back,
                    "given": r.given,
                    "correct": r.correct,
                }
                for r in self.results
            ],
        }
