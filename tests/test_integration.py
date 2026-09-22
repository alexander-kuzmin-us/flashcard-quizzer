"""End-to-end tests: CLI wiring, full sessions, and the real entry point."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

from quizzer import cli
from quizzer.data_loader import load_flashcards
from quizzer.progress import ProgressStore
from quizzer.quiz_engine import ModeConfig, QuizEngine, QuizModeFactory
from quizzer.session import run_quiz
from quizzer.ui import ConsoleUI
from tests.conftest import DeckWriter, ScriptedInput

REPO_ROOT = Path(__file__).resolve().parent.parent
DECK = [
    {"front": "DNS", "back": "Domain Name System"},
    {"front": "TLS", "back": "Transport Layer Security"},
    {"front": "SSH", "back": "Secure Shell"},
]


def run_cli(
    args: list[str], answers: Iterable[str | BaseException] = ()
) -> tuple[int, str, str]:
    """Call ``cli.main`` in-process and capture its output."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(args, input_func=ScriptedInput(answers), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def deck_path(write_deck: DeckWriter) -> Path:
    return write_deck(DECK)


@pytest.fixture
def progress_args(tmp_path: Path) -> list[str]:
    return ["--progress-dir", str(tmp_path / "progress")]


# ---------------------------------------------------------------- required
def test_full_session(deck_path: Path, tmp_path: Path) -> None:
    """Simulate a user answering 3 questions and check the final stats."""
    cards = load_flashcards(deck_path)
    engine = QuizEngine(QuizModeFactory.create("sequential", cards, ModeConfig()))
    out = io.StringIO()
    ui = ConsoleUI(
        ScriptedInput(["domain name system", "wrong answer", "SECURE shell"]),
        out,
        io.StringIO(),
    )

    outcome = run_quiz(engine, ui)
    ui.show_summary(outcome.stats, outcome.reason)

    stats = outcome.stats
    assert outcome.completed
    assert stats.total_questions == 3
    assert stats.correct_count == 2
    assert stats.incorrect_count == 1
    assert stats.accuracy == pytest.approx(66.666, rel=1e-3)
    assert stats.missed_terms == ["TLS"]
    summary = out.getvalue()
    assert "| Total Questions | 3     |" in summary
    assert "| Accuracy %      | 66.7% |" in summary
    assert "TLS" in summary.split("Missed terms:")[1]


# ------------------------------------------------------------ CLI in-process
def test_cli_sequential_session_saves_progress(
    deck_path: Path, progress_args: list[str], tmp_path: Path
) -> None:
    code, out, err = run_cli(
        ["-m", "sequential", "-f", str(deck_path), *progress_args],
        ["domain name system", "x", "secure shell"],
    )
    assert code == 0, err
    assert "Mode: sequential" in out
    assert "Accuracy %      | 66.7%" in out

    store = ProgressStore(deck_path, tmp_path / "progress")
    store.load()
    assert store.miss_counts() == {"DNS": 0, "TLS": 1, "SSH": 0}


def test_cli_adaptive_uses_history_from_previous_session(
    deck_path: Path, progress_args: list[str]
) -> None:
    run_cli(
        ["-f", str(deck_path), *progress_args],
        ["domain name system", "x", "secure shell"],
    )
    code, out, _ = run_cli(
        ["-m", "adaptive", "-f", str(deck_path), "-n", "1", *progress_args],
        ["transport layer security"],
    )
    assert code == 0
    assert out.index("TLS") < out.index("Session Summary")
    assert "Question 1" in out and "DNS" not in out.split("Session Summary")[0]


def test_cli_adaptive_repeats_missed_card(
    deck_path: Path, progress_args: list[str]
) -> None:
    code, out, _ = run_cli(
        ["-m", "adaptive", "-f", str(deck_path), "--seed", "1", "--no-save"]
        + progress_args,
        ["wrong"] * 20,
    )
    assert code == 0
    assert "| Total Questions | 9     |" in out  # 3 cards x 3 attempts


def test_cli_stats_flag(deck_path: Path, progress_args: list[str]) -> None:
    run_cli(["-f", str(deck_path), *progress_args], ["x", "x", "x"])
    code, out, _ = run_cli(["-f", str(deck_path), "--stats", *progress_args])
    assert code == 0
    assert "Lifetime stats for" in out
    assert "| DNS  | 1        | 0       | 1      | 0.0%     |" in out


def test_cli_no_save(deck_path: Path, progress_args: list[str], tmp_path: Path) -> None:
    run_cli(["-f", str(deck_path), "--no-save", *progress_args], ["x", "x", "x"])
    assert not list((tmp_path / "progress").glob("*.json"))


def test_cli_reset_progress(
    deck_path: Path, progress_args: list[str], tmp_path: Path
) -> None:
    run_cli(["-f", str(deck_path), *progress_args], ["x", "x", "x"])
    code, out, _ = run_cli(["-f", str(deck_path), "--reset-progress", *progress_args])
    assert code == 0
    assert "has been reset" in out
    assert not list((tmp_path / "progress").glob("*.json"))


def test_cli_export_json(
    deck_path: Path, progress_args: list[str], tmp_path: Path
) -> None:
    target = tmp_path / "results.json"
    code, out, _ = run_cli(
        ["-f", str(deck_path), "--export", str(target), *progress_args],
        ["domain name system", "exit"],
    )
    assert code == 0
    assert "Results exported to" in out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["session"]["ended"] == "exit"
    assert data["total_questions"] == 1


def test_cli_export_bad_extension_returns_error(
    deck_path: Path, progress_args: list[str]
) -> None:
    code, _, err = run_cli(
        ["-f", str(deck_path), "--export", "r.txt", *progress_args], ["exit"]
    )
    assert code == 1
    assert "unsupported file type" in err


def test_cli_limit_and_seed(deck_path: Path, progress_args: list[str]) -> None:
    code, out, _ = run_cli(
        [
            "-m",
            "random",
            "--seed",
            "3",
            "-n",
            "2",
            "-f",
            str(deck_path),
            *progress_args,
        ],
        ["a", "b"],
    )
    assert code == 0
    assert "| Total Questions | 2     |" in out


def test_cli_mode_is_case_insensitive(
    deck_path: Path, progress_args: list[str]
) -> None:
    code, out, _ = run_cli(["-m", "RANDOM", "-f", str(deck_path), *progress_args])
    assert code == 0
    assert "Mode: random" in out


def test_cli_ctrl_c_during_quiz_exits_cleanly(
    deck_path: Path, progress_args: list[str]
) -> None:
    code, out, err = run_cli(
        ["-f", str(deck_path), *progress_args],
        ["domain name system", KeyboardInterrupt()],
    )
    assert code == 0
    assert "Quiz ended early." in out
    assert "Traceback" not in out + err


def test_cli_ctrl_c_outside_quiz_says_goodbye(
    deck_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_flashcards", interrupt)
    code, out, _ = run_cli(["-f", str(deck_path)])
    assert code == 0
    assert "Goodbye!" in out


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('[{"front": "a"', "not valid JSON"),
        ('[{"front": "a"}]', 'missing required field(s): "back"'),
        ("{}", 'no "cards" key'),
    ],
)
def test_cli_bad_deck_prints_friendly_error(
    write_deck: DeckWriter, content: str, message: str
) -> None:
    code, _, err = run_cli(["-f", str(write_deck(content))])
    assert code == 1
    assert message in err
    assert "Traceback" not in err


def test_cli_missing_file(tmp_path: Path) -> None:
    code, _, err = run_cli(["-f", str(tmp_path / "nope.json")])
    assert code == 1
    assert "File not found" in err


def test_cli_unexpected_error_is_friendly_unless_debug(
    deck_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError("boom")

    monkeypatch.setattr(cli, "load_flashcards", explode)
    code, _, err = run_cli(["-f", str(deck_path)])
    assert code == 1
    assert "Unexpected problem: boom" in err
    with pytest.raises(ZeroDivisionError):
        run_cli(["-f", str(deck_path), "--debug"])


def test_cli_progress_dir_unusable_still_plays(deck_path: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "file_not_dir"
    blocker.write_text("x", encoding="utf-8")
    code, out, err = run_cli(
        ["-f", str(deck_path), "--progress-dir", str(blocker / "sub")], ["exit"]
    )
    assert code == 0
    assert "Progress tracking is off" in err
    assert "Session Summary" in out


def test_cli_reset_without_store_fails(deck_path: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    code, _, _ = run_cli(
        ["-f", str(deck_path), "--reset-progress", "--progress-dir", str(blocker)]
    )
    assert code == 1


def test_cli_save_failure_is_a_warning(
    deck_path: Path, progress_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: ProgressStore) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(ProgressStore, "save", fail)
    code, _, err = run_cli(["-f", str(deck_path), *progress_args], ["x", "x", "x"])
    assert code == 0
    assert "Could not save progress: disk full" in err


def test_cli_corrupt_progress_warns_and_continues(
    deck_path: Path, tmp_path: Path, progress_args: list[str]
) -> None:
    store = ProgressStore(deck_path, tmp_path / "progress")
    store.path.write_text("{broken", encoding="utf-8")
    code, _, err = run_cli(["-f", str(deck_path), *progress_args], ["exit"])
    assert code == 0
    assert "Warning: Progress file could not be read" in err


def test_cli_verbose_logging(deck_path: Path, progress_args: list[str]) -> None:
    _, _, err = run_cli(["-f", str(deck_path), "-v", *progress_args], ["exit"])
    assert "[DEBUG] quizzer: Loaded 3 cards" in err


@pytest.mark.parametrize("bad", ["0", "-2", "abc"])
def test_cli_rejects_non_positive_limit(deck_path: Path, bad: str) -> None:
    with pytest.raises(SystemExit) as info:
        run_cli(["-f", str(deck_path), "-n", bad])
    assert info.value.code == 2


def test_cli_rejects_unknown_mode(deck_path: Path) -> None:
    with pytest.raises(SystemExit) as info:
        run_cli(["-f", str(deck_path), "-m", "spaced"])
    assert info.value.code == 2


# ------------------------------------------------- real process (main.py)
def run_main(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_main_help_lists_all_flags() -> None:
    result = run_main("--help")
    assert result.returncode == 0
    for flag in [
        "--file",
        "--mode",
        "--stats",
        "--limit",
        "--seed",
        "--max-attempts",
        "--export",
        "--progress-dir",
        "--no-save",
        "--reset-progress",
        "--no-color",
        "--verbose",
        "--debug",
        "--version",
    ]:
        assert flag in result.stdout


def test_main_sequential_glossary_runs(tmp_path: Path) -> None:
    result = run_main(
        "--mode",
        "sequential",
        "--file",
        "data/glossary.json",
        "--progress-dir",
        str(tmp_path),
        stdin="domain name system\nexit\n",
    )
    assert result.returncode == 0, result.stderr
    assert "Correct!" in result.stdout
    assert "\033[" not in result.stdout  # piped output: no color codes


def test_main_adaptive_python_basics_full_game(tmp_path: Path) -> None:
    answers = "\n".join(
        [
            "def",
            "len",
            "list",
            "tuple",
            "dict",
            "except",
            "None",
            "//",
            "yield",
            "import",
        ]
    )
    result = run_main(
        "-m",
        "adaptive",
        "-f",
        "data/python_basics.json",
        "--seed",
        "0",
        "--progress-dir",
        str(tmp_path),
        stdin=answers * 3,
    )
    assert result.returncode == 0, result.stderr
    assert "Session Summary" in result.stdout


def test_main_bad_file_has_no_traceback(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    result = run_main("-f", str(bad))
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
