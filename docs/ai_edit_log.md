# AI Edit Log

**Project:** The Flashcard Quizzer
**Author:** Alexander Kuzmin
**AI tool:** Claude (Anthropic), working with a code-execution sandbox so it could
run black, isort, flake8, mypy, bandit and pytest on its own output.

Every entry below records a real event from the build: a tool failure, a failing
test, a manual run that exposed a flaw, or a suggestion that was rejected. The phase
prompts referenced here are reproduced in full in [`prompts.md`](../prompts.md).

---

## 2026-09-22 - 1. Reviewing the starter repo before generating anything

**Context:** Before generating new code I wanted to know what the starter repository
would break once real code sat on top of it.

**AI Tool Used:** Claude

**Prompt/Request:** "Clone the starter repo, read every file (code, config, docs,
`.gitignore`, `.claude/`), and list anything that will conflict with the
requirements: JSON decks in `data/`, `flake8 .` passing, mypy passing, and the
starter tests still running."

**AI Response:** Claude found four problems. (1) `.gitignore` ignores `data/`, so the
sample decks required by `python main.py -f data/glossary.json` would silently never
reach GitHub. (2) `.claude/commands/*` are Python scripts that fail black and flake8,
so `flake8 .` could never pass. (3) `FileHandler.__init__` calls `mkdir(exist_ok=True)`
without `parents=True`. (4) `utils/task_manager.py` is unrelated to-do CRUD demo code.

**Changes Made:** Removed `data/` and `htmlcov/` from `.gitignore` (the coverage report
is a deliverable); excluded `.claude`, `venv` and `htmlcov` in `.flake8`,
`pyproject.toml` (black, isort, mypy); kept and extended `FileHandler`; removed
`task_manager.py` and its test.

**Reasoning:** The `.gitignore` issue is the most dangerous kind of bug: everything
works locally and fails for the grader. I kept `FileHandler` because the rubric asks
for work that extends the starter code; `task_manager` had no role in a flashcard app,
and keeping dead code to inflate coverage would be dishonest.

**Outcome:** A clean baseline where the quality tools measure only project code.

**Lessons Learned:** Review the scaffolding with the same suspicion as generated code.
Ignore files and tool configs are code too.

---

## 2026-09-22 - 2. Adaptive mode starved the deck (found by playing, not by tests)

**Context:** First working version of `AdaptiveMode`. A missed card was re-inserted a
fixed 2 positions ahead in the queue.

**AI Tool Used:** Claude

**Prompt/Request:** "Play a scripted adaptive game on `python_basics.json` with mostly
wrong answers and show me the question order."

**AI Response:** The transcript showed the first 9 questions cycling through the same
3 cards (None, yield, import, None, yield, import...). Each missed card was re-inserted
ahead of the others, so three missed cards formed a loop and no new card appeared until
all three hit the attempt cap.

**Changes Made:** Prompted: "Fix the starvation: make the re-insert distance grow with
each miss of the same card (gap, 2*gap, 3*gap), keep `max_attempts` as the hard cap,
and add a regression test." The n-th miss now re-inserts at `n * requeue_gap`. Added
`test_adaptive_gap_grows_so_missed_cards_do_not_starve_deck`.

**Reasoning:** "Prioritise cards the user gets wrong" should not mean "trap a
struggling user on three cards". A growing gap is also a lightweight version of
spaced repetition, which fits the future-mode story in the brief.

**Outcome:** Fresh cards now enter by question 7 instead of question 10 in the same
all-wrong scenario, and every card is still capped at 3 attempts.

**Lessons Learned:** Unit tests only check the behaviour you thought to specify. Using
the app like a real user exposed a design flaw that no test would have caught.

---

## 2026-09-22 - 3. flake8 complexity check forced a refactor of `_run` and `read_json_file`

**Context:** The first full lint run after Phase 3.

**AI Tool Used:** Claude

**Prompt/Request:** "Run black, isort, flake8 and mypy on the whole project and fix
everything they report. Do not suppress warnings; restructure the code."

**AI Response:** flake8 (configured with `max-complexity = 10`) reported
`C901 '_run' is too complex (12)` in `cli.py` and `C901 'read_json_file' is too
complex (13)` in `file_handler.py`, plus four lines over 88 characters.

**Changes Made:** Split `read_json_file` into `_check_readable` (exists, is-a-file,
size cap) and `_read_text` (encoding and permission errors). Split `cli._run` into
`_reset_progress`, `_play`, `_save_progress` and `_export`, each with one job.

**Reasoning:** A `# noqa: C901` would have been faster, but the warning was right:
`_run` was loading, resetting, showing stats, playing, saving and exporting in one
function. After the split, each path can be read and tested on its own.

**Outcome:** flake8 clean, and every CLI branch reached 100% coverage.

**Lessons Learned:** Configure the complexity check. Generated code tends to grow
long orchestration functions, and a linter catches that faster than a code review.

---

## 2026-09-22 - 4. mypy strict found an unsound type in the progress file parser

**Context:** Validating records read back from the progress JSON file.

**AI Tool Used:** Claude

**Prompt/Request:** Same as entry 3 (fix everything mypy reports under `strict = true`).

**AI Response:** The first version computed `valid = isinstance(attempts, int) and ...`
then returned `CardRecord(attempts, correct) if valid else None`. mypy reported
`Argument 1 to "CardRecord" has incompatible type "Any | None"; expected "int"`.
It cannot narrow types through a boolean stored in a variable.

**Changes Made:** Added a `_is_count(value) -> TypeGuard[int]` helper (non-negative
int, and explicitly rejects `bool`, which is a subclass of `int` in Python) and used
it directly in the `if` statements.

**Reasoning:** The runtime logic was correct, but only by convention. With the
`TypeGuard`, the type checker proves that `CardRecord` only ever receives real
integers. The `bool` rejection also fixes a subtle bug: `{"attempts": true}` would
otherwise have loaded as 1 attempt.

**Outcome:** mypy strict passes on all 24 files, including the tests. Added
`test_invalid_entries_are_skipped_individually` covering negatives, booleans, strings
and `correct > attempts`.

**Lessons Learned:** Strict type checking is a code reviewer that never gets tired.
It found a real edge case (booleans) while complaining about something that looked
purely cosmetic.

---

## 2026-09-22 - 5. Rejected a `# type: ignore` that only worked on one machine

**Context:** Optional `colorama` support so colors work on legacy Windows consoles.

**AI Tool Used:** Claude

**Prompt/Request:** Same lint pass as entry 3.

**AI Response:** The generated `import colorama  # type: ignore[import-not-found]`
failed mypy in the sandbox, where colorama *is* installed but has no type stubs (a
different error code, `import-untyped`, plus an "unused ignore" error). On a machine
without colorama the original comment would have been correct.

**Changes Made:** Replaced the static import with
`importlib.import_module("colorama")` inside a `try/except ImportError`.

**Reasoning:** Adding more error codes to the ignore would pass on one machine and
fail on another. That is a flaky build waiting for the grader. Dynamic import is
correct whether colorama is missing, present without stubs, or present with stubs.

**Outcome:** mypy passes regardless of what is installed. The app still has zero
required runtime dependencies.

**Lessons Learned:** Be suspicious of any suppression comment written by the AI.
Check it against every environment the code will run in, not just the current one.

---

## 2026-09-22 - 6. A failing test that was wrong, not the code

**Context:** First run of the full test suite: 162 passed, 1 failed.

**AI Tool Used:** Claude

**Prompt/Request:** "Write `test_adaptive_mode_behavior`: prove that adaptive mode
repeats an incorrect card, does not repeat correct cards, and does not repeat a
missed card immediately."

**AI Response:** The generated test used `seed=0` and assumed TLS would be followed
by other cards. With that seed TLS was shuffled *last*, so it was correctly repeated
immediately (nothing else remained) and the assertion `second > first + 1` failed.

**Changes Made:** Instead of weakening the assertion or changing the seed until it
passed, I made the test deterministic by passing `history={"TLS": 1}`, which puts TLS
first. The assertion is now exact: the repeat comes back after `requeue_gap` cards.

**Reasoning:** Picking a seed that happens to pass would hide the same fragility.
Using history both removes the dependency on shuffle order and exercises the
cross-session prioritisation feature in the same test.

**Outcome:** The test is stricter than before (exact position, not just "later") and
cannot break if the shuffle implementation changes.

**Lessons Learned:** When an AI-written test fails, first ask whether the test encodes
the right expectation. Changing code to satisfy a wrong test introduces bugs.

---

## 2026-09-22 - 7. Rejected bandit's suggestion to replace `random`

**Context:** Security scan with bandit (it is listed in the starter requirements, so a
reviewer may run it).

**AI Tool Used:** Claude

**Prompt/Request:** "Run bandit on the source and address every finding."

**AI Response:** Two `B311` findings: "Standard pseudo-random generators are not
suitable for security/cryptographic purposes" on the two `random.Random(seed).shuffle`
calls. The generic fix is to use `secrets` / `SystemRandom`.

**Changes Made:** Rejected the switch. Added a comment explaining why and a narrow
`# nosec B311` on those two lines only. (A first attempt put extra words after the
`nosec` code, which bandit tried to parse as test IDs; moved the explanation to its own
line.)

**Reasoning:** Card order is not a security boundary, and `SystemRandom` cannot be
seeded. That would break `--seed` and every deterministic test of random and adaptive
mode.

**Outcome:** bandit clean, with the reasoning documented in the code for the next
reader.

**Lessons Learned:** Security tools report patterns, not risk. The right response is
sometimes a documented exception rather than a code change, but it must be narrow and
explained.

---

## 2026-09-22 - 8. Hardening the starter `FileHandler` instead of replacing it

**Context:** Adaptive mode needs to save history after every session. The starter's
`save_data` opened the target file in `"w"` mode and wrote into it directly.

**AI Tool Used:** Claude

**Prompt/Request:** "Extend `utils/file_handler.py` rather than replacing it. Add a
reader that turns every failure (missing, directory, too large, bad encoding, bad
JSON) into one friendly exception, and make saves safe against Ctrl+C mid-write. Keep
the original tests passing and bring them up to mypy strict."

**AI Response:** Added `read_json_file` with a 5 MiB cap and `FileReadError`, switched
`save_data` to write a temp file and `os.replace` it into place, added
`parents=True` to `mkdir`, and changed `load_data`'s return type from `Dict` to `Any`
(JSON can decode to a list, so the old annotation was wrong). Also serialised to a
string *before* opening any file, so unserialisable data can no longer leave an empty
file behind.

**Changes Made:** Accepted, then asked for tests proving each claim:
`test_save_invalid_data_leaves_no_file`, `test_save_write_failure_raises_runtime_error`
(no temp file left behind), `test_file_handler_creates_nested_directories`, and one
test per reader failure mode. The starter's original tests gained type hints and
lost an unused import that flake8 flagged.

**Reasoning:** A progress file truncated by Ctrl+C would cost a user their history.
Atomic replace is the standard fix, and it was cheap to do here.

**Outcome:** 23 file-handler tests (7 original, 16 new), 99% branch coverage.

**Lessons Learned:** "Extend the starter code" is a good constraint. It forced a
review of code I would otherwise have trusted because it came with the project.

---

## 2026-09-22 - 9. Edge cases in quitting: "exit" as a real answer, and real Ctrl+C

**Context:** Designing the quiz loop's quit handling.

**AI Tool Used:** Claude

**Prompt/Request:** "Typing exit or pressing Ctrl+C must quit gracefully and still
show the summary. What edge cases does that create?"

**AI Response:** Claude flagged three cases: a card whose correct answer is literally
"exit" or "quit" (plausible in a Python deck); Ctrl+D / closed stdin raising
`EOFError`; and the fact that simulating `KeyboardInterrupt` in a test is not the same
as a real SIGINT arriving while `input()` is blocked.

**Changes Made:** The exit command only ends the quiz if it is *not* the correct
answer to the current card (`test_exit_is_accepted_as_answer_when_it_is_correct`).
EOF ends the session the same way as Ctrl+C. I also asked Claude to send a real
`SIGINT` to a running `python main.py` process: exit code 0, no traceback, and the
summary was printed.

**Reasoning:** A quit word that could mark a correct answer wrong would be a small but
real frustration. Verifying real signal handling gave me confidence the mocked tests
reflect reality.

**Outcome:** Exit, quit, Ctrl+C and Ctrl+D all end cleanly with a summary; partial
sessions are still saved to history.

**Lessons Learned:** Asking the AI "what edge cases does this create?" before
accepting code was more productive than asking it to "handle edge cases".

---

## 2026-09-22 - 10. Final review pass: small leaks and compatibility

**Context:** Last review against the rubric and the code review checklist.

**AI Tool Used:** Claude

**Prompt/Request:** "Review the finished project as a strict grader. Check every
rubric line and the submission checklist, run the app from a real TTY to confirm
colors, check docstring coverage, and verify it on Python 3.10 since that is the
minimum version."

**AI Response and Changes Made:**
- `--help` printed the default progress directory as an absolute path
  (`/root/.flashcard_quizzer`), leaking the local username into help output. Changed
  it to `~/.flashcard_quizzer`.
- An AST scan found two nested helper functions without docstrings; added them.
- CSV export wrote user-typed answers verbatim. An answer like `=HYPERLINK(...)` would
  run as a formula in Excel, so cells starting with `= + - @` are now prefixed with an
  apostrophe (`test_csv_export_neutralises_formula_injection`).
- The sandbox runs Python 3.12. Installed Python 3.10.20 separately and ran the full
  suite: 163 passed, so nothing depends on 3.11+ features.
- `htmlcov/` was un-ignored in the root `.gitignore` but still never reached git:
  coverage.py writes its own `htmlcov/.gitignore` containing `*`. Found by checking
  `git ls-files` after the first commit; deleted that file so the coverage report
  deliverable is actually submitted.
- Ran the app through `script` to get a real TTY and confirmed the green (`\033[32m`)
  and red (`\033[31m`) codes appear, and that piped output has no color codes.

**Reasoning:** Each item is small, but together they are the difference between
"passes the tests" and "ready for someone else to run".

**Outcome:** All tools clean: black, isort, flake8, mypy strict, bandit; 163 tests;
99% coverage.

**Lessons Learned:** The final review found issues in areas that had no tests:
help text, output to other programs, and the minimum Python version. Checklists
still matter after the tests are green.

---

## Reflection Questions

1. **What types of tasks did AI help with most effectively?** Boilerplate-heavy but
   well-specified work: argparse wiring, validation branches, table rendering, and
   especially test generation for error paths (dozens of parametrised invalid decks).
2. **Where did I need the most modifications?** Behaviour that is only visible when
   the app is used (entry 2) and environment-dependent code (entries 5 and 10).
3. **Patterns in AI strengths and weaknesses:** Strong at breadth and at following
   explicit constraints (type hints, docstrings, no tracebacks). Weaker at noticing
   emergent behaviour and at knowing whether a suppression comment is portable.
4. **How did my prompting improve?** Early prompts asked for features; later prompts
   asked for evidence ("run it and show me the order", "send a real SIGINT", "prove it
   on 3.10"). Evidence-seeking prompts found more problems.
5. **What would I do differently?** Configure the full tool gate (including the
   complexity limit and bandit) before Phase 1 instead of after Phase 3.

## Summary Statistics

- **Total AI interactions logged:** 10 (from about 25 prompts and tool runs in the session)
- **Lines of AI-generated code used:** about 1,370 source lines and 1,170 test lines
  (non-blank, including docstrings)
- **Lines of AI-generated code modified after review:** about 200 across the entries
  above (the two refactors in entry 3 account for most of it)
- **Most helpful AI interaction:** Entry 2. The scripted game exposed a design flaw
  the tests could not.
- **Most challenging AI interaction:** Entry 6. Deciding the test, not the code, was
  wrong.
- **Biggest lesson learned:** Make the AI produce evidence: tool output, transcripts,
  real signals, a real 3.10 interpreter. Then review the evidence, not the claims.
