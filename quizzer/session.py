"""The interactive quiz loop that connects ``QuizEngine`` to ``ConsoleUI``."""

from __future__ import annotations

from dataclasses import dataclass

from quizzer.models import normalize_answer
from quizzer.quiz_engine import QuizEngine
from quizzer.stats import SessionStats
from quizzer.ui import ConsoleUI

#: Inputs that end the quiz early (compared case-insensitively).
EXIT_COMMANDS: frozenset[str] = frozenset({"exit", "quit"})


@dataclass(frozen=True)
class SessionOutcome:
    """How a session ended.

    Attributes:
        stats: Statistics for the answered questions.
        reason: ``completed``, ``exit``, ``interrupted`` (Ctrl+C) or
            ``eof`` (input closed).
    """

    stats: SessionStats
    reason: str

    @property
    def completed(self) -> bool:
        """``True`` if every scheduled question was asked."""
        return self.reason == "completed"


def run_quiz(engine: QuizEngine, ui: ConsoleUI) -> SessionOutcome:
    """Ask questions until the deck is exhausted or the user quits.

    Typing ``exit`` or ``quit`` ends the quiz, unless that word is actually
    the correct answer to the current card. Ctrl+C and end-of-input also end
    the quiz gracefully; the caller still gets the stats collected so far.

    Args:
        engine: A ready-to-run engine.
        ui: Console UI used for prompts and feedback.

    Returns:
        The session outcome.
    """
    number = 0
    try:
        while (card := engine.next_card()) is not None:
            number += 1
            response = ui.ask(card, number, engine.remaining)
            wants_exit = normalize_answer(response) in EXIT_COMMANDS
            if wants_exit and not card.is_correct(response):
                return SessionOutcome(engine.stats, "exit")
            ui.show_feedback(engine.answer(response))
    except KeyboardInterrupt:
        return SessionOutcome(engine.stats, "interrupted")
    except EOFError:
        return SessionOutcome(engine.stats, "eof")
    return SessionOutcome(engine.stats, "completed")
