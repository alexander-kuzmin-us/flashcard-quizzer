"""Domain model for flashcards."""

from __future__ import annotations

from dataclasses import dataclass, field


def normalize_answer(text: str) -> str:
    """Normalise an answer for comparison.

    Comparison is case-insensitive (using ``casefold`` so it also works for
    non-English text) and ignores leading, trailing and repeated internal
    whitespace.

    Args:
        text: Raw answer text.

    Returns:
        The normalised form of ``text``.

    Example:
        >>> normalize_answer("  Domain   Name System ")
        'domain name system'
    """
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class Flashcard:
    """A single flashcard.

    Attributes:
        front: The prompt shown to the user.
        back: The canonical answer.
        alternatives: Other answers that should also be accepted.
    """

    front: str
    back: str
    alternatives: tuple[str, ...] = field(default=())

    def is_correct(self, answer: str) -> bool:
        """Return ``True`` if ``answer`` matches the back or an alternative.

        Args:
            answer: The user's raw input.
        """
        given = normalize_answer(answer)
        if not given:
            return False
        accepted = {normalize_answer(self.back)}
        accepted.update(normalize_answer(alt) for alt in self.alternatives)
        return given in accepted
