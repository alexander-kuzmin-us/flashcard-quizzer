# Flashcard Quizzer

A terminal flashcard trainer built through AI-assisted development. It loads a deck
from JSON, quizzes you in **sequential**, **random** or **adaptive** mode, gives
colored Correct/Incorrect feedback, and ends every session with a summary table of
total questions, accuracy and missed terms.

Built for the internal ticket: *"help new hires memorize our server acronyms. It
needs to run in the terminal, load data from JSON, and have different quiz modes.
The code needs to be clean so we can extend it later."*

```
Flashcard Quizzer
Deck: glossary.json (12 cards)  |  Mode: sequential
Type 'exit' or press Ctrl+C to stop.

Question 1 (12 remaining)
  DNS
  Your answer: domain name system
  Correct!

Question 2 (11 remaining)
  HTTP
  Your answer: hyper text
  Incorrect. The answer is: Hypertext Transfer Protocol

Session Summary
+-----------------+-------+
| Metric          | Value |
+-----------------+-------+
| Total Questions | 2     |
| Correct         | 1     |
| Incorrect       | 1     |
| Accuracy %      | 50.0% |
+-----------------+-------+
Missed terms:
+------+-----------------------------+
| Term | Correct answer              |
+------+-----------------------------+
| HTTP | Hypertext Transfer Protocol |
+------+-----------------------------+
```

## Features

| Feature | Details |
| --- | --- |
| JSON decks, two layouts | Array `[{"front", "back"}]` or object `{"cards": [...]}`; optional `alternatives` list of other accepted answers |
| Validation with friendly errors | Missing file, directory, empty file, bad UTF-8, oversized file (5 MiB cap), malformed JSON (with line/column), wrong types, missing or empty fields, duplicate fronts. Never a raw traceback. |
| Three quiz modes (Strategy + Factory) | `sequential` (1 to N), `random` (shuffled, `--seed` for reproducibility), `adaptive` (see below) |
| Adaptive mode | Cards you missed in *previous* sessions come first; cards you miss *now* come back after a growing gap (2, 4, ... cards) up to `--max-attempts` times |
| Case-insensitive answers | Also ignores extra whitespace; uses `casefold` so non-English text compares correctly |
| Colored feedback | Green for correct, red for incorrect. Auto-disabled when output is piped, with `--no-color`, or when `NO_COLOR` is set |
| Session summary | Total Questions, Correct, Incorrect, Accuracy %, and a table of missed terms with correct answers |
| Lifetime stats (`--stats`) | Per-card attempts, correct, missed and accuracy across all sessions, most-missed first |
| Progress persistence | Per-deck history saved atomically under `~/.flashcard_quizzer` (`--progress-dir`, `--no-save`, `--reset-progress`) |
| Export (`--export`) | Save session results to `.json` or `.csv` (CSV is protected against spreadsheet formula injection) |
| Graceful exit | Type `exit` or `quit`, press Ctrl+C, or Ctrl+D. The summary is still shown. |
| Logging and debugging | `-v/--verbose` for diagnostic logs, `--debug` to see full tracebacks for unexpected errors |

The application itself has **no third-party runtime dependencies**; it uses only the
Python standard library.

## Getting Started

### Dependencies

- Python **3.10 or higher** (tested on 3.10.20 and 3.12.3)
- `pip` and the built-in `venv` module
- Development tools (installed from `requirements.txt`): pytest, pytest-cov, black,
  isort, flake8, mypy, bandit

### Installation

```bash
git clone <your-repo-url> flashcard-quizzer
cd flashcard-quizzer

# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

## Usage

```bash
# Show every available flag
python main.py --help

# Standard quiz loop
python main.py --mode sequential --file data/glossary.json

# Adaptive mode (Definition of Done command)
python main.py -m adaptive -f data/python_basics.json

# Five random questions, reproducible order
python main.py -m random -f data/glossary.json -n 5 --seed 42

# Lifetime per-card statistics for a deck, then exit
python main.py -f data/glossary.json --stats

# Export this session's results
python main.py -f data/glossary.json --export results.csv

# Practise without recording history / wipe history for a deck
python main.py -f data/glossary.json --no-save
python main.py -f data/glossary.json --reset-progress
```

### All flags

| Flag | Description |
| --- | --- |
| `-f, --file FILE` | Path to the JSON deck (required) |
| `-m, --mode MODE` | `sequential` (default), `random` or `adaptive` (case-insensitive) |
| `--stats` | Show lifetime per-card statistics for the deck and exit |
| `-n, --limit N` | Ask at most N questions |
| `--seed SEED` | Random seed for reproducible random/adaptive order |
| `--max-attempts N` | Adaptive mode: ask a missed card at most N times per session (default 3) |
| `--export PATH` | Save session results to `.json` or `.csv` |
| `--progress-dir DIR` | Where per-deck history lives (default `~/.flashcard_quizzer`) |
| `--no-save` | Do not record this session in the history |
| `--reset-progress` | Delete the saved history for this deck and exit |
| `--no-color` | Disable ANSI colors |
| `-v, --verbose` | Log diagnostic details to stderr |
| `--debug` | Show full tracebacks for unexpected errors |
| `--version` | Print the version |

Exit codes: `0` success (including quitting early), `1` handled error such as a bad
deck, `2` invalid command-line arguments.

### Deck format

```json
[
  {"front": "DNS", "back": "Domain Name System"},
  {"front": "CI/CD", "back": "Continuous Integration / Continuous Delivery",
   "alternatives": ["Continuous Integration and Continuous Delivery"]}
]
```

or

```json
{"name": "Python Basics", "cards": [{"front": "Keyword used to define a function", "back": "def"}]}
```

Rules: `front` and `back` are required non-empty strings; `alternatives` is an
optional list of non-empty strings; fronts must be unique (case-insensitive); extra
keys such as `tags` or `name` are ignored. Two sample decks ship in `data/`.

## Architecture

```
flashcard-quizzer/
├── main.py                 # Entry point: python main.py ...
├── quizzer/
│   ├── models.py           # Flashcard value object, answer normalisation
│   ├── data_loader.py      # JSON deck loading and validation
│   ├── quiz_engine.py      # QuizMode strategies, QuizModeFactory, QuizEngine
│   ├── stats.py            # AnswerResult, SessionStats
│   ├── progress.py         # Per-deck history used by adaptive mode
│   ├── exporters.py        # JSON/CSV exporters (Strategy + Factory)
│   ├── ui.py               # Console I/O, colors, tables
│   ├── session.py          # Interactive quiz loop (exit / Ctrl+C / EOF)
│   └── cli.py              # argparse and application wiring
├── utils/file_handler.py   # Starter FileHandler, extended (atomic writes, safe JSON reader)
├── data/                   # Sample decks: glossary.json, python_basics.json
├── tests/                  # 163 pytest tests
├── docs/                   # AI edit log, final report, architecture, quality report
├── htmlcov/                # HTML coverage report
└── prompts.md              # Prompt log
```

**Design patterns.** `QuizMode` is an abstract **Strategy** for "which card comes
next"; `SequentialMode`, `RandomMode` and `AdaptiveMode` are the concrete strategies
and `QuizEngine` is the context. `QuizModeFactory` is a registry-based **Factory**
that maps the `--mode` string to a strategy, so a future "spaced repetition" mode is
one new class plus `@QuizModeFactory.register`, with no changes to the CLI or engine
(this is demonstrated by `test_factory_register_new_mode_without_other_changes`).
The same Strategy + Factory pairing picks a JSON or CSV exporter from the output
file extension. See [docs/architecture.md](docs/architecture.md) for diagrams.

## Testing

```bash
# Run the full suite
python -m pytest tests/

# Coverage report (HTML in htmlcov/index.html, plus terminal summary)
python -m pytest --cov=. --cov-report=html --cov-report=term

# All quality gates
black --check . && isort --check-only . && flake8 . && mypy . && bandit -q -r quizzer utils main.py && python -m pytest
```

After regenerating the report, delete `htmlcov/.gitignore` (coverage.py creates it
with `*`, which would keep the report out of git).

Current results: **163 tests passing, 99% coverage** (test files excluded from the
measurement), and black, isort, flake8, mypy (strict) and bandit all clean. Full
output is in [docs/quality_report.md](docs/quality_report.md).

### Break Down Tests

| File | What it covers |
| --- | --- |
| `test_flashcard_loader.py` | Required: `test_load_valid_flashcards_array`, `test_load_invalid_json`, `test_load_missing_required_field`. Plus object format, alternatives, the bundled decks, and 16 parametrised invalid structures (wrong types, empty values, duplicates) |
| `test_quiz_modes.py` | Required: `test_quiz_mode_factory`, `test_adaptive_mode_behavior`. Plus ordering, seeding, no input mutation, history prioritisation, max-attempts cap, a regression test for the adaptive "starvation loop", factory registration/extensibility, and engine state rules |
| `test_integration.py` | Required: `test_full_session` (3 answers, final stats and summary table). Plus every CLI flag in-process, and real `python main.py` subprocess runs for `--help`, the glossary quiz, a full adaptive game, and a malformed deck with no traceback |
| `test_file_handler.py` | The starter's original tests (now typed) plus atomic writes, nested directories, and every failure mode of the JSON reader |
| `test_ui.py` | Table rendering, color rules (TTY, `--no-color`, `NO_COLOR`), green/red feedback, summary and lifetime tables, and the session loop's exit/Ctrl+C/EOF handling |
| `test_progress.py`, `test_exporters.py`, `test_stats.py`, `test_models.py` | History persistence and corruption handling, filename sanitisation, JSON/CSV export and CSV formula-injection guard, accuracy maths, case-insensitive matching |

## Project Instructions

Deliverables for the Udacity "AI-Assisted Development" project:

- [x] Complete codebase with source, tests and documentation
- [x] [`docs/ai_edit_log.md`](docs/ai_edit_log.md): 10 detailed AI interaction entries
- [x] [`prompts.md`](prompts.md): the prompt log
- [x] [`docs/final_report.md`](docs/final_report.md): final report using the template
- [x] Updated README (this file)
- [x] Coverage report: [`htmlcov/index.html`](htmlcov/index.html) and [`docs/quality_report.md`](docs/quality_report.md)
- [x] Code quality verification: black, isort, flake8, mypy, bandit all pass

## Built With

* [Python 3.10+](https://www.python.org/) - Language (standard library only at runtime)
* [pytest](https://docs.pytest.org/) and [pytest-cov](https://pytest-cov.readthedocs.io/) - Tests and coverage
* [Black](https://black.readthedocs.io/) and [isort](https://pycqa.github.io/isort/) - Formatting and import order
* [flake8](https://flake8.pycqa.org/) - Linting, including a max-complexity check
* [mypy](https://mypy.readthedocs.io/) - Static type checking in strict mode
* [Bandit](https://bandit.readthedocs.io/) - Security linting
* [Claude](https://claude.ai/) - AI assistant used to generate, review and refactor the code

## License

[License](LICENSE.txt)
