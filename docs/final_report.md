# AI-Assisted Development Project Report

**Student Name:** Alexander Kuzmin
**Project Title:** The Flashcard Quizzer
**Date:** September 22, 2026

## Executive Summary

I built the Flashcard Quizzer, a terminal application that helps new hires memorise
server acronyms. It loads a deck from JSON, quizzes the user in sequential, random or
adaptive mode, gives colored feedback, and finishes with a summary of total questions,
accuracy and missed terms. Adaptive mode remembers which cards a user missed in past
sessions, asks those first, and brings back cards missed in the current session.

I did not write the code by hand. I decomposed the ticket into about twenty prompts
across six phases, had Claude generate each piece, and required it to run black,
isort, flake8, mypy (strict) and pytest on its own output. My role was specification,
review and verification. Ten review findings changed the code, and all are logged in
`ai_edit_log.md`.

## Project Overview

### Problem Statement

New hires need a lightweight way to drill internal vocabulary, and the team needs code
clean enough to extend later (for example, a spaced-repetition mode).

### Solution Approach

The app is split into single-purpose modules: `data_loader` (validation), `quiz_engine`
(modes and engine), `stats`, `progress`, `exporters`, `ui`, `session` (the loop) and
`cli` (wiring). Only `ui` touches the terminal, and its input and output are injected,
so everything else is testable without a TTY. The runtime uses only the standard
library; development tooling is installed with pip into a venv.

### Final Features

- [x] JSON loading in array and object formats, with friendly validation errors
- [x] Case-insensitive quiz loop with green/red feedback
- [x] Sequential, random (seedable) and adaptive modes
- [x] Summary table: total questions, accuracy and missed terms
- [x] Cross-session progress and a `--stats` lifetime view
- [x] Export to JSON or CSV
- [x] Graceful exit via `exit`, Ctrl+C or Ctrl+D
- [x] Alternative accepted answers, question limits, verbose logging, `--debug`

## AI Collaboration Experience

### AI Tools Used

- [x] Claude, with a code-execution sandbox so it could run the tools itself

### Collaboration Workflow

1. **Prompt structure.** Each prompt covered one milestone and listed exact
   requirements, then ended with a standing Definition of Done: type hints,
   docstrings, run every quality tool, fix findings by changing code rather than
   suppressing them, and show me the output.
2. **Task types.** Generation (modules, tests, sample data), review (edge-case
   analysis before implementation), refactoring, and verification.
3. **Validation.** I read the diffs, but relied more on evidence: tool output, a
   scripted game transcript, a real TTY, a real SIGINT, and a Python 3.10 run.
4. **Refinement.** When something was wrong I rewrote the prompt with the specific
   finding and a constraint ("do not add noqa", "do not weaken the assertion").

### Most Valuable AI Interactions

#### Example 1: The adaptive starvation loop
**Context:** The first adaptive mode re-inserted missed cards a fixed two positions ahead.
**AI Prompt:** "Play a scripted adaptive game with mostly wrong answers and show me the
question order."
**AI Response:** The transcript showed the same three cards cycling for nine questions.
**Your Changes:** I had the gap grow with each miss and added a regression test.
**Outcome:** New cards appear three questions sooner, with the attempt cap intact.

#### Example 2: A failing test that was wrong
**Context:** `test_adaptive_mode_behavior` failed on the first full run.
**AI Prompt:** "Is the test or the code wrong? Fix whichever is wrong without
weakening the assertion."
**AI Response:** The test assumed a shuffle order; with that seed the card was last,
so an immediate repeat was correct.
**Your Changes:** Used history to make the order deterministic and made the assertion
exact.
**Outcome:** A stricter, stable test that also exercises cross-session prioritisation.

#### Example 3: Rejecting a security suggestion
**Context:** Bandit flagged `random.shuffle` (B311).
**AI Prompt:** "Address every bandit finding; if one is a false positive, explain why."
**AI Response:** Suggested the usual fix, a cryptographic generator.
**Your Changes:** Rejected it, because `SystemRandom` cannot be seeded and `--seed`
plus deterministic tests depend on seeding. Added a narrow, commented `nosec`.
**Outcome:** Bandit clean, with the reasoning recorded in the code.

### Challenges with AI Collaboration

The AI was weakest where behaviour only emerges at runtime (the starvation loop) or
depends on the environment (a `type: ignore` that passed only when colorama was
absent). It also wrote a test around an assumption it had not checked. It was
strongest at breadth: it generated dozens of parametrised invalid-deck cases I would
not have listed myself.

## Software Engineering Practices

### Code Quality Measures

- [x] Code formatting (Black, isort)
- [x] Linting (flake8 with a max-complexity limit of 10, bandit)
- [x] Type hints (mypy strict, including tests)
- [x] Documentation (docstrings on every source function and class)
- [x] Error handling (domain exceptions with user-facing messages)

### Testing Strategy

163 tests across nine files: unit tests per module, in-process CLI tests with a
scripted fake `input()`, and subprocess tests that run the real `python main.py`.
Error paths are tested as thoroughly as happy paths. Coverage is 99% with test files
excluded from the measurement. Two tests are regression tests for issues found during
review. The process was test-alongside rather than strict TDD.

### Design Patterns Used

- **Strategy:** `QuizMode` is the abstract strategy for choosing the next card;
  Sequential, Random and Adaptive are the concrete strategies, and `QuizEngine` is the
  context. I chose it because the brief describes three algorithms for one task and
  anticipates a fourth. The pattern is not forced: adaptive mode needs a feedback hook
  (`record_result`) that the others ignore, and the engine calls it without knowing
  which mode it holds.
- **Factory:** `QuizModeFactory` maps the `--mode` string to a class through a
  registry. Argparse reads its choices from the registry, so a new mode needs one
  class and one decorator, which a test demonstrates.
- The same Strategy plus Factory pairing selects a JSON or CSV exporter by extension.

### Code Structure and Organization

Dependencies point inward: `cli` depends on everything, while `quiz_engine`, `stats`
and `data_loader` depend on nothing UI-related. The main refactor split two functions
that flake8 flagged as too complex into single-purpose helpers.

## Technical Challenges and Solutions

### Challenge 1: Graceful quitting
**Problem:** "exit" might be a correct answer, and mocked Ctrl+C may not match reality.
**Solution:** The exit word only quits if it is not the right answer; a real SIGINT
was sent to the running process to confirm a clean exit.
**AI Involvement:** Claude listed the edge cases when asked before implementation.
**Lessons Learned:** Ask for edge cases first, then verify with a real signal.

### Challenge 2: Unsound types in persisted data
**Problem:** mypy could not prove progress records were integers.
**Solution:** A `TypeGuard` helper, which also rejected booleans.
**AI Involvement:** Found by mypy strict, fixed by Claude on request.
**Lessons Learned:** Strict typing finds real bugs behind cosmetic-looking errors.

## Code Quality Analysis

### Metrics

- Lines of code: about 1,370 source and 1,170 test lines (non-blank)
- Test coverage: 99% (163 tests)
- Number of functions/classes: 94 functions and methods, 23 classes
- Linting score: zero findings from black, isort, flake8, mypy strict and bandit

### Self-Assessment

- **Code Readability:** 5. Small modules, descriptive names and plain-English errors.
- **Code Maintainability:** 5. New modes and export formats plug in through factories.
- **Test Quality:** 4. Thorough, but a few tests assert on exact table spacing.
- **Documentation:** 5. README, architecture diagrams, prompt log and edit log.

## Learning Outcomes

### Technical Skills Developed

Strategy and Factory in practice, atomic file writes, `TypeGuard`, and testing
interactive CLIs through dependency injection.

### AI Collaboration Skills

Specific prompts with explicit constraints, a shared Definition of Done, and above
all asking for evidence instead of assurances.

### Software Engineering Insights

Tools configured before coding (especially complexity limits) prevent problems
rather than finding them later.

## Reflection

### What Worked Well

Making the AI run the tools and show the output, and playing the app like a user.

### What Could Be Improved

I would configure the full tool gate, including bandit, before Phase 1, and I would
write the required test names first as a failing specification.

### Future Enhancements

A spaced-repetition mode (the factory is ready for it), fuzzy matching for typos,
multiple-choice questions, and per-user profiles.

## Conclusion

AI-assisted development moved my work from writing code to specifying, reviewing and
verifying it. The AI produced working code quickly; the value I added was deciding
what "correct" meant and demanding proof. I will keep using a standing Definition of
Done and evidence-first review in my QA work.

## Appendices

### Appendix A: AI Interaction Log

See `docs/ai_edit_log.md`; entries 2, 6 and 7 correspond to the examples above.

### Appendix B: Code Statistics

See `docs/quality_report.md` and `htmlcov/index.html`.

### Appendix C: Additional Resources

The starter's `ai_guidance/` checklists, `docs/design_patterns.md`, the mypy
`TypeGuard` documentation, and the NO_COLOR convention (https://no-color.org).
