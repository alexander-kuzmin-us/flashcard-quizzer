"""Console presentation: prompts, colored feedback and summary tables.

All terminal I/O goes through ``ConsoleUI`` and its injected ``input_func``
and output streams, which keeps the rest of the application testable
without a real terminal.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TextIO

from quizzer.models import Flashcard
from quizzer.progress import CardRecord
from quizzer.stats import AnswerResult, SessionStats


class Color:
    """ANSI escape codes used by the UI."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


def supports_color(stream: TextIO, disabled: bool = False) -> bool:
    """Decide whether to emit ANSI colors on ``stream``.

    Colors are off when requested (``--no-color``), when the ``NO_COLOR``
    environment variable is set (see https://no-color.org), or when output
    is not an interactive terminal (for example, piped to a file).

    Args:
        stream: The output stream.
        disabled: ``True`` if the user passed ``--no-color``.
    """
    if disabled or os.environ.get("NO_COLOR") is not None:
        return False
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty) or not isatty():
        return False
    if os.name == "nt":  # pragma: no cover - platform specific
        try:
            colorama = importlib.import_module("colorama")
            colorama.just_fix_windows_console()
        except (ImportError, AttributeError):
            pass  # Windows Terminal and modern consoles handle ANSI natively.
    return True


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a simple ASCII table.

    Args:
        headers: Column titles.
        rows: Table rows; each must have ``len(headers)`` cells.

    Returns:
        The table as a multi-line string (no trailing newline).

    Raises:
        ValueError: If a row has the wrong number of cells.
    """
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("Every row must have one cell per header.")
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def line(cells: Sequence[str]) -> str:
        """Format one row with padded, pipe-separated cells."""
        padded = (f" {cell.ljust(width)} " for cell, width in zip(cells, widths))
        return "|" + "|".join(padded) + "|"

    parts = [border, line(headers), border]
    parts.extend(line(row) for row in rows)
    parts.append(border)
    return "\n".join(parts)


class ConsoleUI:
    """Terminal user interface for the quiz."""

    def __init__(
        self,
        input_func: Callable[[str], str] = input,
        out: TextIO | None = None,
        err: TextIO | None = None,
        use_color: bool = False,
    ) -> None:
        """Create the UI.

        Args:
            input_func: Reads one line of user input given a prompt.
            out: Stream for normal output (defaults to ``sys.stdout``).
            err: Stream for warnings and errors (defaults to ``sys.stderr``).
            use_color: Emit ANSI colors.
        """
        self._input = input_func
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr
        self._use_color = use_color

    def _paint(self, text: str, *codes: str) -> str:
        """Wrap ``text`` in ANSI codes when color is enabled."""
        if not self._use_color or not codes:
            return text
        return "".join(codes) + text + Color.RESET

    def _print(self, text: str = "") -> None:
        """Write a line to the output stream."""
        print(text, file=self._out)

    # ------------------------------------------------------------------ messages
    def info(self, message: str) -> None:
        """Show an informational message."""
        self._print(message)

    def warn(self, message: str) -> None:
        """Show a warning on the error stream."""
        print(self._paint(f"Warning: {message}", Color.YELLOW), file=self._err)

    def error(self, message: str) -> None:
        """Show an error on the error stream."""
        print(self._paint(f"Error: {message}", Color.RED, Color.BOLD), file=self._err)

    # ---------------------------------------------------------------- quiz flow
    def show_welcome(self, deck: str, mode: str, card_count: int) -> None:
        """Print the session banner and how to quit."""
        title = self._paint("Flashcard Quizzer", Color.BOLD, Color.CYAN)
        self._print(title)
        self._print(f"Deck: {deck} ({card_count} cards)  |  Mode: {mode}")
        self._print(self._paint("Type 'exit' or press Ctrl+C to stop.", Color.DIM))
        self._print()

    def ask(self, card: Flashcard, number: int, remaining: int) -> str:
        """Show the front of ``card`` and return the user's answer.

        Args:
            card: The card being asked.
            number: 1-based question counter.
            remaining: Questions left, including this one.

        Raises:
            KeyboardInterrupt: If the user presses Ctrl+C.
            EOFError: If input is closed (Ctrl+D / end of piped input).
        """
        header = self._paint(f"Question {number}", Color.BOLD)
        self._print(f"{header} ({remaining} remaining)")
        self._print(f"  {card.front}")
        return self._input("  Your answer: ")

    def show_feedback(self, result: AnswerResult) -> None:
        """Print Correct (green) or Incorrect (red) with the right answer."""
        if result.correct:
            self._print(self._paint("  Correct!", Color.GREEN, Color.BOLD))
        else:
            verdict = self._paint("  Incorrect.", Color.RED, Color.BOLD)
            self._print(f"{verdict} The answer is: {result.card.back}")
        self._print()

    def show_summary(self, stats: SessionStats, reason: str = "completed") -> None:
        """Print the end-of-session summary table and missed terms.

        Args:
            stats: The session statistics.
            reason: Why the session ended (``completed``, ``exit``,
                ``interrupted`` or ``eof``).
        """
        if reason != "completed":
            self._print()
            self._print(self._paint("Quiz ended early.", Color.YELLOW))
        self._print(self._paint("Session Summary", Color.BOLD, Color.CYAN))
        rows = [
            ["Total Questions", str(stats.total_questions)],
            ["Correct", str(stats.correct_count)],
            ["Incorrect", str(stats.incorrect_count)],
            ["Accuracy %", f"{stats.accuracy:.1f}%"],
        ]
        self._print(render_table(["Metric", "Value"], rows))

        missed = stats.missed_terms
        if not stats.total_questions:
            self._print("No questions were answered.")
        elif missed:
            self._print(self._paint("Missed terms:", Color.RED, Color.BOLD))
            answers = {r.card.front: r.card.back for r in stats.results}
            self._print(
                render_table(
                    ["Term", "Correct answer"],
                    [[term, answers[term]] for term in missed],
                )
            )
        else:
            self._print(self._paint("Perfect score. No missed terms!", Color.GREEN))

    def show_lifetime_stats(
        self, deck: str, cards: Sequence[Flashcard], records: Mapping[str, CardRecord]
    ) -> None:
        """Print lifetime per-card statistics, most-missed first."""
        self._print(self._paint(f"Lifetime stats for {deck}", Color.BOLD, Color.CYAN))

        def sort_key(card: Flashcard) -> tuple[int, str]:
            """Most-missed first, then alphabetical."""
            record = records.get(card.front, CardRecord())
            return (-record.misses, card.front.casefold())

        rows = []
        for card in sorted(cards, key=sort_key):
            record = records.get(card.front, CardRecord())
            accuracy = f"{record.accuracy:.1f}%" if record.attempts else "-"
            rows.append(
                [
                    card.front,
                    str(record.attempts),
                    str(record.correct),
                    str(record.misses),
                    accuracy,
                ]
            )
        self._print(
            render_table(["Term", "Attempts", "Correct", "Missed", "Accuracy"], rows)
        )
        if not any(record.attempts for record in records.values()):
            self._print("No history yet. Play a round to start tracking progress.")
