# Prompt Log

The prompts used to direct the AI agent (Claude) through the build, in order. The
requirements were decomposed into small prompts, one milestone at a time, each ending
with the same "Definition of Done" so the agent checked its own work. Refinement
prompts triggered by review findings are listed after the phase prompts and are
cross-referenced to the detailed entries in [`docs/ai_edit_log.md`](docs/ai_edit_log.md).

**Standing Definition of Done (appended to every generation prompt):**

> Target Python 3.10+, standard library only at runtime, pip + venv. Every function
> has type hints and a Google-style docstring. When done, run `black .`,
> `isort .`, `flake8 .` (max line 88, max complexity 10) and `mypy .` in strict mode,
> then `python -m pytest`. Fix every finding by changing the code, not by adding
> suppressions, unless you explain why the suppression is correct. Show me the tool
> output.

---

## Phase 0: Review the starter and set up tooling

**P0.1**
> Clone https://github.com/udacity/cd14602-project-starter and read everything in
> `project/starter`: code, tests, docs, `.gitignore`, `.editorconfig`, `.claude/`.
> List anything that will conflict with these requirements: sample JSON decks live in
> `data/` and must be committed; `flake8 .`, `black .` and `mypy .` must pass on the
> whole repo; the starter tests must keep passing. Do not change anything yet.

**P0.2**
> Apply your fixes. Create `pyproject.toml` (black, isort, pytest, coverage with
> branch coverage that omits `tests/`, mypy strict targeting 3.10) and `.flake8`.
> Exclude `.claude`, `venv` and `htmlcov` from every tool. Trim `requirements.txt`
> to the tools we actually use.

## Phase 1: Data layer and validation

**P1.1**
> Create `quizzer/models.py` with a frozen dataclass `Flashcard(front, back,
> alternatives: tuple[str, ...] = ())` and an `is_correct(answer)` method. Comparison
> is case-insensitive (use `casefold`) and ignores leading, trailing and repeated
> whitespace. A blank answer is never correct.

**P1.2**
> Extend `utils/file_handler.py` rather than replacing it. Add
> `read_json_file(path, max_bytes=5 MiB)` that raises a single `FileReadError` with a
> user-friendly message for: missing file, directory instead of a file, permission
> denied, file over the size cap, non-UTF-8 bytes (tolerate a BOM), empty file, and
> malformed JSON (include line and column). Make `FileHandler.save_data` atomic
> (temp file + `os.replace`) and make `mkdir` create parents. Keep the original starter
> tests passing and add type hints to them.

**P1.3**
> Create `quizzer/data_loader.py` with `load_flashcards(path) -> list[Flashcard]`.
> Support both the array format `[{"front": ..., "back": ...}]` and the object format
> `{"cards": [...]}`. Validate: at least one card; each card is an object; `front` and
> `back` present, strings, non-empty after stripping; optional `alternatives` is a list
> of non-empty strings; fronts are unique case-insensitively. Ignore unknown keys.
> Raise `FlashcardLoadError` whose message names the file, the card number and the
> problem in plain English, describing types in JSON terms ("a number", "null"),
> never Python ones. No tracebacks must ever reach the user.

## Phase 2: Core logic and design patterns

**P2.1**
> Create `quizzer/stats.py` with a frozen `AnswerResult(card, given, correct)` and a
> `SessionStats` that exposes total_questions, correct_count, incorrect_count,
> accuracy (percent, 0.0 when empty), missed_terms (unique fronts in first-miss order)
> and `to_dict()` for export.

**P2.2**
> In `quizzer/quiz_engine.py`, implement the Strategy pattern. Create an abstract
> base class `QuizMode` with abstract `next_card() -> Flashcard | None`, an abstract
> `remaining` property, and a non-abstract `record_result(card, correct)` that does
> nothing by default. Pass shared options through a frozen `ModeConfig(seed,
> history, max_attempts=3, requeue_gap=2)` that validates its values. Implement:
> - `SequentialMode`: file order, each card once.
> - `RandomMode`: shuffled copy (never mutate the caller's list), seedable.
> - `AdaptiveMode`: order the deck by historical miss count (most-missed first, ties
>   shuffled). When a card is missed, re-insert it `requeue_gap` positions ahead so
>   it comes back soon but not immediately, until answered correctly or asked
>   `max_attempts` times.

**P2.3**
> Add a Factory: `QuizModeFactory` with a class-level registry, a `register`
> classmethod usable as a decorator (reject blank and duplicate names),
> `create(mode_name, cards, config=None)` (case-insensitive, unknown names raise a
> ValueError listing valid options), and `available_modes()`. Register the three
> modes. Then add `QuizEngine`, the Strategy context: it hands out cards, checks
> answers, forwards results to the strategy, keeps `SessionStats`, and supports an
> optional question limit. It must never check which concrete mode it holds.

**P2.4**
> Add `quizzer/progress.py`: a `ProgressStore` that keeps per-card attempts and
> correct counts per deck in a JSON file, using `FileHandler`. The filename must be
> derived safely from the deck path (sanitised stem plus a short hash, so there is no
> path traversal and no collision between two `cards.json` files). A missing or
> corrupt progress file must produce warnings, never a crash. Expose `miss_counts()`
> for adaptive mode.

## Phase 3: CLI and interaction

**P3.1**
> Create `quizzer/ui.py` with a `ConsoleUI` whose input function and output streams
> are injected (for tests). Green for correct, red for incorrect, using ANSI codes;
> turn colors off when output is not a TTY, when `--no-color` is passed, or when
> `NO_COLOR` is set. Render the end-of-session summary as an ASCII table with Total
> Questions, Correct, Incorrect and Accuracy %, followed by a table of missed terms
> and their answers.

**P3.2**
> Create `quizzer/session.py` with `run_quiz(engine, ui)`. Typing `exit` or `quit`
> (any case), Ctrl+C and Ctrl+D must all end the quiz gracefully and return the stats
> collected so far. Before writing it, list the edge cases this creates.

**P3.3**
> Create `quizzer/cli.py` and a thin `main.py`. Use argparse: `-f/--file`
> (required), `-m/--mode` (choices from the factory, case-insensitive), `--stats`
> (lifetime per-card stats for the deck, then exit), `-n/--limit`, `--seed`,
> `--max-attempts`, `--export PATH` (.json or .csv), `--progress-dir`, `--no-save`,
> `--reset-progress`, `--no-color`, `-v/--verbose`, `--debug`, `--version`. Include
> usage examples in the epilog. Return exit code 0 on success or early quit, 1 on
> handled errors. Wrap everything in a last-resort handler that prints one friendly
> line instead of a traceback unless `--debug` is set.

**P3.4**
> Add `quizzer/exporters.py`: a `ResultExporter` strategy with JSON and CSV
> implementations and an `ExporterFactory` that picks one from the file extension.
> Protect CSV output against spreadsheet formula injection.

**P3.5**
> Create `data/glossary.json` (array format, 12 server and networking acronyms) and
> `data/python_basics.json` (object format, 10 Python basics with short typed
> answers). Then run `python main.py --help` and play a scripted adaptive game on
> `python_basics.json` with mostly wrong answers. Show me the full transcript and the
> order the questions came in.

## Phase 4: Tests

**P4.1**
> Write a pytest suite with a `conftest.py` providing a temp-deck writer and a
> scripted fake `input()` that can also raise `KeyboardInterrupt` and `EOFError`.
> These tests are required by name and must exist exactly:
> `tests/test_flashcard_loader.py`: `test_load_valid_flashcards_array`,
> `test_load_invalid_json`, `test_load_missing_required_field`;
> `tests/test_quiz_modes.py`: `test_quiz_mode_factory`, `test_adaptive_mode_behavior`;
> `tests/test_integration.py`: `test_full_session` (simulate a user answering 3
> questions and check the final stats calculation).
> Also cover every error path, every CLI flag, and include subprocess tests that run
> the real `python main.py`. Tests must be typed so mypy strict passes on `tests/` too.
> Target over 90% coverage with test files excluded from the measurement.

**P4.2**
> Run `python -m pytest --cov=. --cov-report=html --cov-report=term` and show me the
> per-file table.

## Phase 5: Refinement prompts (triggered by review)

| # | Prompt | Why | Log entry |
| --- | --- | --- | --- |
| R1 | "Fix the starvation: make the re-insert distance grow with each miss of the same card (gap, 2*gap, 3*gap), keep `max_attempts` as the hard cap, and add a regression test." | The P3.5 transcript showed three missed cards looping and blocking the rest of the deck | 2 |
| R2 | "flake8 reports C901 on `_run` (12) and `read_json_file` (13). Split them into single-purpose helpers. Do not add `noqa`." | Complexity limit exceeded | 3 |
| R3 | "mypy can't narrow `attempts`/`correct` through the `valid` variable. Use a `TypeGuard` helper, and make sure booleans are rejected." | Unsound types in the progress parser | 4 |
| R4 | "The colorama `type: ignore` fails when colorama is installed without stubs. Make the optional import pass mypy in every environment." | Environment-dependent type check | 5 |
| R5 | "`test_adaptive_mode_behavior` fails because TLS was shuffled last. Is the test or the code wrong? Fix whichever is wrong without weakening the assertion." | Failing test | 6 |
| R6 | "Run bandit on the source and address every finding. If a finding is a false positive, explain why in the code and suppress only that line." | Security scan | 7 |
| R7 | "Review the finished project as a strict grader: every rubric line, the submission checklist, colors in a real TTY, docstring coverage, a real SIGINT against the running process, and the full suite on Python 3.10." | Final verification | 9, 10 |

## Phase 6: Documentation

**P6.1**
> Rewrite `README.md` for the finished app: features, setup for macOS/Linux and
> Windows, every flag, deck format, architecture, how to run each quality tool, and a
> breakdown of what each test file covers.

**P6.2**
> Write `docs/architecture.md` with Mermaid diagrams: module dependencies, the
> Strategy/Factory class diagram, the adaptive algorithm flowchart, and the session
> sequence including error handling.

**P6.3**
> Fill in `docs/ai_edit_log.md` using the template, with one entry per real issue we
> hit in this session. Quote the actual tool output. Do not invent problems.

**P6.4**
> Write `docs/final_report.md` using `docs/report_template.md`, 1000 to 1500 words,
> with real metrics from the tools, and save the full QA output to
> `docs/quality_report.md`.
