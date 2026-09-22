"""Quiz engine: card-selection strategies, a mode factory, and the engine.

Design patterns
---------------
* **Strategy**: ``QuizMode`` is the abstract strategy for "which card comes
  next". ``SequentialMode``, ``RandomMode`` and ``AdaptiveMode`` are
  interchangeable concrete strategies. ``QuizEngine`` is the context; it
  only talks to the ``QuizMode`` interface.
* **Factory**: ``QuizModeFactory`` maps a mode name (from the CLI) to a
  strategy class, so callers never instantiate modes directly. New modes
  (for example spaced repetition) are added with ``QuizModeFactory.register``
  and no other code changes.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from quizzer.models import Flashcard
from quizzer.stats import AnswerResult, SessionStats


@dataclass(frozen=True)
class ModeConfig:
    """Options shared by all quiz modes.

    Attributes:
        seed: Seed for any randomness, for reproducible sessions and tests.
        history: Past miss counts keyed by card front (adaptive mode).
        max_attempts: Maximum times adaptive mode asks the same card in one
            session. Prevents an endless loop on a card the user cannot get.
        requeue_gap: Base number of other cards adaptive mode shows before
            repeating a missed card. The gap grows with each miss of the
            same card (gap, 2*gap, 3*gap...) so several missed cards cannot
            lock the user in a loop and starve the rest of the deck.
    """

    seed: int | None = None
    history: Mapping[str, int] = field(default_factory=dict)
    max_attempts: int = 3
    requeue_gap: int = 2

    def __post_init__(self) -> None:
        """Validate numeric options."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.requeue_gap < 0:
            raise ValueError("requeue_gap must not be negative")


class QuizMode(ABC):
    """Abstract strategy that decides the order in which cards are asked."""

    #: Name used on the command line; set by each concrete mode.
    name: ClassVar[str] = ""
    #: One-line description shown in ``--help``.
    description: ClassVar[str] = ""

    def __init__(self, cards: Sequence[Flashcard], config: ModeConfig) -> None:
        """Store the deck and configuration.

        Args:
            cards: The deck to quiz on. Must not be empty.
            config: Shared mode options.

        Raises:
            ValueError: If ``cards`` is empty.
        """
        if not cards:
            raise ValueError("A quiz needs at least one card.")
        self._cards: list[Flashcard] = list(cards)
        self._config = config

    @abstractmethod
    def next_card(self) -> Flashcard | None:
        """Return the next card to ask, or ``None`` when the quiz is over."""

    @property
    @abstractmethod
    def remaining(self) -> int:
        """Number of questions currently queued (may grow in adaptive mode)."""

    def record_result(self, card: Flashcard, correct: bool) -> None:
        """Receive feedback about an answer. Default: ignore it.

        Args:
            card: The card that was answered.
            correct: Whether the answer was right.
        """


class SequentialMode(QuizMode):
    """Ask every card once, in file order (1 to N)."""

    name = "sequential"
    description = "every card once, in file order"

    def __init__(self, cards: Sequence[Flashcard], config: ModeConfig) -> None:
        """See ``QuizMode.__init__``."""
        super().__init__(cards, config)
        self._index = 0

    def next_card(self) -> Flashcard | None:
        """Return the next card in file order."""
        if self._index >= len(self._cards):
            return None
        card = self._cards[self._index]
        self._index += 1
        return card

    @property
    def remaining(self) -> int:
        """Cards not yet asked."""
        return len(self._cards) - self._index


class RandomMode(QuizMode):
    """Ask every card once, in shuffled order."""

    name = "random"
    description = "every card once, shuffled"

    def __init__(self, cards: Sequence[Flashcard], config: ModeConfig) -> None:
        """Shuffle a copy of the deck (the caller's list is never mutated)."""
        super().__init__(cards, config)
        self._order = list(self._cards)
        # Shuffling flashcards is not security-sensitive and must be seedable
        # for reproducible sessions, so the stdlib PRNG is the right tool.
        random.Random(config.seed).shuffle(self._order)  # nosec B311
        self._index = 0

    def next_card(self) -> Flashcard | None:
        """Return the next card in shuffled order."""
        if self._index >= len(self._order):
            return None
        card = self._order[self._index]
        self._index += 1
        return card

    @property
    def remaining(self) -> int:
        """Cards not yet asked."""
        return len(self._order) - self._index


class AdaptiveMode(QuizMode):
    """Prioritise cards the user gets wrong.

    Two mechanisms:

    1. **Across sessions**: cards with more historical misses are asked
       first (ties are shuffled so the order still varies).
    2. **Within a session**: a missed card is re-inserted into the queue and
       asked again, until it is answered correctly or has been asked
       ``max_attempts`` times. The n-th miss of a card puts it
       ``n * requeue_gap`` positions ahead, so repeats come back quickly at
       first and then spread out (a lightweight spaced-repetition effect).
    """

    name = "adaptive"
    description = "missed cards first, and missed cards come back"

    def __init__(self, cards: Sequence[Flashcard], config: ModeConfig) -> None:
        """Order the deck by historical misses, most-missed first."""
        super().__init__(cards, config)
        order = list(self._cards)
        # Non-cryptographic, seedable shuffle; see RandomMode for rationale.
        random.Random(config.seed).shuffle(order)  # nosec B311
        order.sort(key=lambda card: config.history.get(card.front, 0), reverse=True)
        self._queue: deque[Flashcard] = deque(order)
        self._attempts: dict[Flashcard, int] = {}

    def next_card(self) -> Flashcard | None:
        """Return the card at the front of the priority queue."""
        if not self._queue:
            return None
        return self._queue.popleft()

    @property
    def remaining(self) -> int:
        """Cards currently queued, including scheduled repeats."""
        return len(self._queue)

    def record_result(self, card: Flashcard, correct: bool) -> None:
        """Schedule a repeat of ``card`` if it was missed and has attempts left."""
        attempts = self._attempts.get(card, 0) + 1
        self._attempts[card] = attempts
        if correct or attempts >= self._config.max_attempts:
            return
        position = min(self._config.requeue_gap * attempts, len(self._queue))
        self._queue.insert(position, card)


class QuizModeFactory:
    """Create quiz-mode strategies by name."""

    _registry: ClassVar[dict[str, type[QuizMode]]] = {}

    @classmethod
    def register(cls, mode_class: type[QuizMode]) -> type[QuizMode]:
        """Register a mode class under its ``name``. Usable as a decorator.

        Args:
            mode_class: A concrete ``QuizMode`` subclass with a unique name.

        Returns:
            ``mode_class`` unchanged, so this works as ``@register``.

        Raises:
            ValueError: If the name is empty or already registered.
        """
        key = mode_class.name.strip().lower()
        if not key:
            raise ValueError(f"{mode_class.__name__} must define a 'name'.")
        if key in cls._registry and cls._registry[key] is not mode_class:
            raise ValueError(f"A quiz mode named '{key}' is already registered.")
        cls._registry[key] = mode_class
        return mode_class

    @classmethod
    def create(
        cls,
        mode_name: str,
        cards: Sequence[Flashcard],
        config: ModeConfig | None = None,
    ) -> QuizMode:
        """Instantiate the mode registered under ``mode_name``.

        Args:
            mode_name: Case-insensitive mode name, e.g. ``"adaptive"``.
            cards: The deck.
            config: Mode options; defaults to ``ModeConfig()``.

        Raises:
            ValueError: If no mode with that name exists.
        """
        key = mode_name.strip().lower()
        mode_class = cls._registry.get(key)
        if mode_class is None:
            options = ", ".join(cls.available_modes())
            raise ValueError(
                f"Unknown quiz mode '{mode_name}'. Choose from: {options}."
            )
        return mode_class(cards, config or ModeConfig())

    @classmethod
    def available_modes(cls) -> list[str]:
        """Return the registered mode names, sorted."""
        return sorted(cls._registry)

    @classmethod
    def describe_modes(cls) -> dict[str, str]:
        """Return a mapping of mode name to description."""
        return {name: cls._registry[name].description for name in cls.available_modes()}


for _mode in (SequentialMode, RandomMode, AdaptiveMode):
    QuizModeFactory.register(_mode)


class QuizEngine:
    """Run a quiz using a pluggable ``QuizMode`` strategy.

    The engine is UI-agnostic: it hands out cards, checks answers, informs
    the strategy, and keeps statistics. ``quizzer.session`` drives it from
    the terminal, and tests drive it directly.
    """

    def __init__(self, mode: QuizMode, limit: int | None = None) -> None:
        """Create an engine.

        Args:
            mode: The card-selection strategy.
            limit: Stop after this many questions (``None`` for no limit).

        Raises:
            ValueError: If ``limit`` is less than 1.
        """
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        self._mode = mode
        self._limit = limit
        self._current: Flashcard | None = None
        self.stats = SessionStats()

    @property
    def mode(self) -> QuizMode:
        """The active strategy."""
        return self._mode

    @property
    def remaining(self) -> int:
        """Questions still to come, respecting ``limit``."""
        queued = self._mode.remaining + (1 if self._current else 0)
        if self._limit is None:
            return queued
        return max(0, min(queued, self._limit - self.stats.total_questions))

    def next_card(self) -> Flashcard | None:
        """Advance to and return the next card, or ``None`` when finished.

        Raises:
            RuntimeError: If the previous card has not been answered yet.
        """
        if self._current is not None:
            raise RuntimeError("Answer the current card before asking for another.")
        if self._limit is not None and self.stats.total_questions >= self._limit:
            return None
        self._current = self._mode.next_card()
        return self._current

    def answer(self, response: str) -> AnswerResult:
        """Check ``response`` against the current card.

        Args:
            response: The user's answer (compared case-insensitively).

        Returns:
            The result, which is also added to ``stats``.

        Raises:
            RuntimeError: If there is no current card.
        """
        if self._current is None:
            raise RuntimeError("There is no card to answer. Call next_card() first.")
        card = self._current
        self._current = None
        result = AnswerResult(
            card=card, given=response, correct=card.is_correct(response)
        )
        self.stats.record(result)
        self._mode.record_result(card, result.correct)
        return result
