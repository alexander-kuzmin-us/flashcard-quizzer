# Code Quality Verification

Generated on 2026-09-22 by running each command from the repository root.

Environment: Python 3.12.3. The full suite was also run separately on Python 3.10.20: 163 passed.

## `black --check .`

```
All done! ✨ 🍰 ✨
24 files would be left unchanged.

exit code: 0
```

## `isort --check-only .`

```
Skipped 1 files

exit code: 0
```

## `flake8 .`

```
(no output: no findings)

exit code: 0
```

## `mypy .`

```
Success: no issues found in 24 source files

exit code: 0
```

## `bandit -q -r quizzer utils main.py`

```
(no output: no findings)

exit code: 0
```

## `python -m pytest --cov=. --cov-report=html --cov-report=term`

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/claude/flashcard-quizzer
configfile: pyproject.toml
testpaths: tests
plugins: cov-7.1.0
collected 163 items

tests/test_exporters.py ........                                         [  4%]
tests/test_file_handler.py .......................                       [ 19%]
tests/test_flashcard_loader.py ............................              [ 36%]
tests/test_integration.py ...............................                [ 55%]
tests/test_models.py .........                                           [ 60%]
tests/test_progress.py ..........                                        [ 66%]
tests/test_quiz_modes.py ................................                [ 86%]
tests/test_stats.py ....                                                 [ 88%]
tests/test_ui.py ..................                                      [100%]

================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.3-final-0 ________________

Name                     Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------
main.py                      2      2      0      0     0%   9-11
quizzer/__init__.py          1      0      0      0   100%
quizzer/cli.py             127      0     18      0   100%
quizzer/data_loader.py      78      0     40      0   100%
quizzer/exporters.py        51      0      6      0   100%
quizzer/models.py           16      0      2      0   100%
quizzer/progress.py         78      0     16      0   100%
quizzer/quiz_engine.py     150      0     32      0   100%
quizzer/session.py          29      0      4      0   100%
quizzer/stats.py            37      0      6      0   100%
quizzer/ui.py              102      0     22      0   100%
utils/__init__.py            0      0      0      0   100%
utils/file_handler.py       75      0     14      1    99%   132->134
--------------------------------------------------------------------
TOTAL                      746      2    160      1    99%
Coverage HTML written to dir htmlcov
============================= 163 passed in 0.96s ==============================

exit code: 0
```

## Required test scenarios

```
tests/test_flashcard_loader.py::test_load_valid_flashcards_array PASSED  [ 11%]
tests/test_flashcard_loader.py::test_load_invalid_json PASSED            [ 22%]
tests/test_flashcard_loader.py::test_load_missing_required_field PASSED  [ 33%]
tests/test_quiz_modes.py::test_quiz_mode_factory[sequential-SequentialMode] PASSED [ 44%]
tests/test_quiz_modes.py::test_quiz_mode_factory[random-RandomMode] PASSED [ 55%]
tests/test_quiz_modes.py::test_quiz_mode_factory[adaptive-AdaptiveMode] PASSED [ 66%]
tests/test_quiz_modes.py::test_quiz_mode_factory[  ADAPTIVE -AdaptiveMode] PASSED [ 77%]
tests/test_quiz_modes.py::test_adaptive_mode_behavior PASSED             [ 88%]
tests/test_integration.py::test_full_session PASSED                      [100%]
============================== 9 passed in 0.04s ===============================
```

Note: `main.py` shows 0% because it is only executed as a subprocess in
`tests/test_integration.py` (`test_main_*`), which coverage does not trace. It
is three lines that import and call `quizzer.cli.main`, which is covered at 100%.
