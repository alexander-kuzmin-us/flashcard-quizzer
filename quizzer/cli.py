"""Command-line interface: argument parsing and application wiring."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from quizzer import __version__
from quizzer.data_loader import FlashcardLoadError, load_flashcards
from quizzer.exporters import ExporterFactory, ExportError, export_results
from quizzer.models import Flashcard
from quizzer.progress import DEFAULT_PROGRESS_DIR, ProgressStore
from quizzer.quiz_engine import ModeConfig, QuizEngine, QuizModeFactory
from quizzer.session import SessionOutcome, run_quiz
from quizzer.ui import ConsoleUI, supports_color

logger = logging.getLogger("quizzer")


def positive_int(text: str) -> int:
    """``argparse`` type that accepts only integers of 1 or more."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number")
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more (got {value})")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. ``--help`` lists every flag."""
    modes = QuizModeFactory.describe_modes()
    mode_help = "; ".join(f"{name}: {desc}" for name, desc in modes.items())
    exts = " or ".join(ExporterFactory.supported_extensions())
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Flashcard Quizzer: practise flashcards from a JSON deck.",
        epilog=(
            "examples:\n"
            "  python main.py -f data/glossary.json\n"
            "  python main.py -m adaptive -f data/python_basics.json\n"
            "  python main.py -m random -f data/glossary.json -n 5 --seed 42\n"
            "  python main.py -f data/glossary.json --stats\n"
            "  python main.py -f data/glossary.json --export results.csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-f", "--file", required=True, help="path to the JSON flashcard deck"
    )
    parser.add_argument(
        "-m",
        "--mode",
        default="sequential",
        type=str.lower,
        choices=QuizModeFactory.available_modes(),
        help=f"quiz mode (default: sequential). {mode_help}",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="show lifetime per-card statistics for the deck and exit",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=positive_int,
        metavar="N",
        help="ask at most N questions",
    )
    parser.add_argument(
        "--seed", type=int, help="random seed for reproducible random/adaptive order"
    )
    parser.add_argument(
        "--max-attempts",
        type=positive_int,
        default=3,
        metavar="N",
        help="adaptive mode: ask a missed card at most N times per session "
        "(default: 3)",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        help=f"save the session results to PATH ({exts})",
    )
    parser.add_argument(
        "--progress-dir",
        type=Path,
        default=DEFAULT_PROGRESS_DIR,
        metavar="DIR",
        help="where per-deck history is stored (default: ~/.flashcard_quizzer)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not record this session in the deck history",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="delete the saved history for this deck and exit",
    )
    parser.add_argument("--no-color", action="store_true", help="disable colors")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log diagnostic details to stderr"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show full tracebacks for unexpected errors",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def configure_logging(verbose: bool, stream: TextIO) -> None:
    """Send ``quizzer`` log records to ``stream`` (DEBUG if verbose)."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.propagate = False


def main(
    argv: Sequence[str] | None = None,
    input_func: Callable[[str], str] = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the application.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).
        input_func: Source of user input (injectable for tests).
        out: Stream for normal output (defaults to ``sys.stdout``).
        err: Stream for errors (defaults to ``sys.stderr``).

    Returns:
        Process exit code: 0 on success, 1 on a handled error. ``argparse``
        exits with 2 on invalid arguments.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose, err)
    ui = ConsoleUI(input_func, out, err, supports_color(out, args.no_color))
    try:
        return _run(args, ui)
    except KeyboardInterrupt:
        ui.info("\nGoodbye!")
        return 0
    except Exception as exc:  # last-resort guard: never show a raw traceback
        if args.debug:
            raise
        logger.debug("Unexpected error", exc_info=True)
        ui.error(f"Unexpected problem: {exc}. Re-run with --debug for details.")
        return 1


def _open_store(args: argparse.Namespace, ui: ConsoleUI) -> ProgressStore | None:
    """Create and load the progress store, or return ``None`` if unavailable."""
    try:
        store = ProgressStore(args.file, args.progress_dir)
    except OSError as exc:
        ui.warn(f"Progress tracking is off: cannot use '{args.progress_dir}' ({exc}).")
        return None
    for warning in store.load():
        ui.warn(warning)
    logger.debug("Progress file: %s", store.path)
    return store


def _run(args: argparse.Namespace, ui: ConsoleUI) -> int:
    """Execute the command described by ``args``."""
    try:
        cards = load_flashcards(args.file)
    except FlashcardLoadError as exc:
        ui.error(str(exc))
        return 1
    deck_name = Path(args.file).name
    logger.debug("Loaded %d cards from %s", len(cards), args.file)

    store = _open_store(args, ui)
    if args.reset_progress:
        return _reset_progress(store, deck_name, ui)
    if args.stats:
        ui.show_lifetime_stats(deck_name, cards, store.records if store else {})
        return 0
    return _play(args, ui, cards, deck_name, store)


def _reset_progress(store: ProgressStore | None, deck_name: str, ui: ConsoleUI) -> int:
    """Handle ``--reset-progress``."""
    if store is None:
        return 1
    store.reset()
    ui.info(f"Progress for {deck_name} has been reset.")
    return 0


def _play(
    args: argparse.Namespace,
    ui: ConsoleUI,
    cards: list[Flashcard],
    deck_name: str,
    store: ProgressStore | None,
) -> int:
    """Run one interactive quiz, then save progress and export if requested."""
    config = ModeConfig(
        seed=args.seed,
        history=store.miss_counts() if store is not None else {},
        max_attempts=args.max_attempts,
    )
    engine = QuizEngine(QuizModeFactory.create(args.mode, cards, config), args.limit)

    ui.show_welcome(deck_name, args.mode, len(cards))
    outcome = run_quiz(engine, ui)
    ui.show_summary(outcome.stats, outcome.reason)

    if store is not None and not args.no_save:
        _save_progress(store, outcome, ui)
    if args.export:
        return _export(args.export, outcome, deck_name, args.mode, ui)
    return 0


def _save_progress(
    store: ProgressStore, outcome: SessionOutcome, ui: ConsoleUI
) -> None:
    """Fold the session into the deck history; warn (not fail) on errors."""
    if not outcome.stats.total_questions:
        return
    store.update(outcome.stats.results)
    try:
        store.save()
    except RuntimeError as exc:
        ui.warn(f"Could not save progress: {exc}")


def _export(
    path: str, outcome: SessionOutcome, deck_name: str, mode: str, ui: ConsoleUI
) -> int:
    """Handle ``--export``. Returns the exit code."""
    meta = {
        "deck": deck_name,
        "mode": mode,
        "ended": outcome.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        written = export_results(outcome.stats, path, meta)
    except ExportError as exc:
        ui.error(str(exc))
        return 1
    ui.info(f"Results exported to {written}")
    return 0
