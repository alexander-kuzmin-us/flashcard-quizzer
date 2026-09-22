"""Tests for quiz-mode strategies, the factory, and the engine."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from quizzer.models import Flashcard
from quizzer.quiz_engine import (
    AdaptiveMode,
    ModeConfig,
    QuizEngine,
    QuizMode,
    QuizModeFactory,
    RandomMode,
    SequentialMode,
)


def drain(mode: QuizMode, correct: bool = True) -> list[str]:
    """Ask every card, answering all right or all wrong. Return fronts."""
    asked: list[str] = []
    while (card := mode.next_card()) is not None:
        asked.append(card.front)
        mode.record_result(card, correct)
    return asked


def deck(size: int) -> list[Flashcard]:
    """Build a deck of cards named c1..cN."""
    return [Flashcard(f"c{i}", f"a{i}") for i in range(1, size + 1)]


# ------------------------------------------------------------- required tests
@pytest.mark.parametrize(
    ("name", "expected_class"),
    [
        ("sequential", SequentialMode),
        ("random", RandomMode),
        ("adaptive", AdaptiveMode),
        ("  ADAPTIVE ", AdaptiveMode),
    ],
)
def test_quiz_mode_factory(
    name: str, expected_class: type[QuizMode], sample_cards: list[Flashcard]
) -> None:
    mode = QuizModeFactory.create(name, sample_cards)
    assert type(mode) is expected_class
    assert isinstance(mode, QuizMode)


def test_adaptive_mode_behavior(sample_cards: list[Flashcard]) -> None:
    """A missed card is asked again; correct cards are not repeated.

    History puts TLS first so the order is deterministic regardless of seed
    (an earlier version of this test relied on shuffle order and was flaky
    in intent: when TLS happened to be last, an immediate repeat is correct).
    """
    config = ModeConfig(seed=0, requeue_gap=1, history={"TLS": 1})
    mode = AdaptiveMode(sample_cards, config)
    asked: list[str] = []
    missed_once: set[str] = set()
    while (card := mode.next_card()) is not None:
        asked.append(card.front)
        correct = card.front != "TLS" or "TLS" in missed_once
        if not correct:
            missed_once.add("TLS")
        mode.record_result(card, correct)

    assert asked.count("TLS") == 2
    assert asked.count("DNS") == 1
    assert asked.count("SSH") == 1
    assert asked[0] == "TLS"
    first, second = [i for i, front in enumerate(asked) if front == "TLS"]
    assert second == first + 2, "repeat comes back after `requeue_gap` other cards"


# ------------------------------------------------------------ sequential/random
def test_sequential_mode_preserves_file_order() -> None:
    assert drain(SequentialMode(deck(5), ModeConfig())) == [
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
    ]


def test_sequential_mode_ignores_wrong_answers() -> None:
    assert drain(SequentialMode(deck(3), ModeConfig()), correct=False) == [
        "c1",
        "c2",
        "c3",
    ]


def test_sequential_remaining_counts_down() -> None:
    mode = SequentialMode(deck(2), ModeConfig())
    assert mode.remaining == 2
    mode.next_card()
    assert mode.remaining == 1
    mode.next_card()
    assert mode.remaining == 0
    assert mode.next_card() is None


def test_random_mode_asks_every_card_exactly_once() -> None:
    asked = drain(RandomMode(deck(20), ModeConfig(seed=7)))
    assert sorted(asked) == sorted(f"c{i}" for i in range(1, 21))
    assert asked != [f"c{i}" for i in range(1, 21)]


def test_random_mode_is_reproducible_with_seed() -> None:
    first = drain(RandomMode(deck(10), ModeConfig(seed=42)))
    second = drain(RandomMode(deck(10), ModeConfig(seed=42)))
    assert first == second


def test_random_mode_does_not_mutate_input_deck() -> None:
    cards = deck(10)
    original = list(cards)
    drain(RandomMode(cards, ModeConfig(seed=1)))
    assert cards == original


def test_random_remaining() -> None:
    mode = RandomMode(deck(3), ModeConfig(seed=1))
    mode.next_card()
    assert mode.remaining == 2


# ----------------------------------------------------------------- adaptive
def test_adaptive_prioritises_historically_missed_cards() -> None:
    history = {"c4": 5, "c2": 1}
    asked = drain(AdaptiveMode(deck(5), ModeConfig(seed=3, history=history)))
    assert asked[:2] == ["c4", "c2"]
    assert sorted(asked[2:]) == ["c1", "c3", "c5"]


def test_adaptive_respects_max_attempts() -> None:
    asked = drain(AdaptiveMode(deck(2), ModeConfig(max_attempts=3)), correct=False)
    assert asked.count("c1") == 3
    assert asked.count("c2") == 3
    assert len(asked) == 6


def test_adaptive_single_card_repeats_until_correct() -> None:
    mode = AdaptiveMode(deck(1), ModeConfig(max_attempts=5))
    answers: Iterator[bool] = iter([False, False, True])
    asked = 0
    while (card := mode.next_card()) is not None:
        asked += 1
        mode.record_result(card, next(answers))
    assert asked == 3


def test_adaptive_gap_grows_so_missed_cards_do_not_starve_deck() -> None:
    """Regression: with a fixed gap, 3 missed cards looped and starved the deck."""
    mode = AdaptiveMode(deck(10), ModeConfig(seed=None, requeue_gap=2, max_attempts=3))
    asked = drain(mode, correct=False)
    unique_in_first_seven = len(set(asked[:7]))
    assert unique_in_first_seven >= 4, asked[:7]


def test_adaptive_remaining_grows_after_miss() -> None:
    mode = AdaptiveMode(deck(2), ModeConfig())
    card = mode.next_card()
    assert card is not None
    assert mode.remaining == 1
    mode.record_result(card, correct=False)
    assert mode.remaining == 2


# ------------------------------------------------------------ config/factory
def test_mode_requires_cards() -> None:
    with pytest.raises(ValueError, match="at least one card"):
        SequentialMode([], ModeConfig())


def test_mode_config_rejects_zero_max_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        ModeConfig(max_attempts=0)


def test_mode_config_rejects_negative_gap() -> None:
    with pytest.raises(ValueError, match="requeue_gap"):
        ModeConfig(requeue_gap=-1)


def test_factory_unknown_mode_lists_options(sample_cards: list[Flashcard]) -> None:
    with pytest.raises(ValueError, match="Choose from: adaptive, random, sequential"):
        QuizModeFactory.create("spaced", sample_cards)


def test_factory_available_modes_and_descriptions() -> None:
    assert QuizModeFactory.available_modes() == ["adaptive", "random", "sequential"]
    assert set(QuizModeFactory.describe_modes()) == {"adaptive", "random", "sequential"}


def test_factory_register_new_mode_without_other_changes(
    sample_cards: list[Flashcard], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extensibility: a new strategy plugs in through the factory only."""
    monkeypatch.setattr(QuizModeFactory, "_registry", dict(QuizModeFactory._registry))

    @QuizModeFactory.register
    class ReverseMode(SequentialMode):
        name = "reverse"
        description = "last card first"

        def __init__(self, cards: list[Flashcard], config: ModeConfig) -> None:
            super().__init__(list(reversed(cards)), config)

    mode = QuizModeFactory.create("reverse", sample_cards)
    assert drain(mode) == ["SSH", "TLS", "DNS"]


def test_factory_register_rejects_duplicates_and_blank_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(QuizModeFactory, "_registry", dict(QuizModeFactory._registry))

    class Clash(SequentialMode):
        name = "random"

    class Nameless(SequentialMode):
        name = " "

    with pytest.raises(ValueError, match="already registered"):
        QuizModeFactory.register(Clash)
    with pytest.raises(ValueError, match="must define a 'name'"):
        QuizModeFactory.register(Nameless)
    assert QuizModeFactory.register(RandomMode) is RandomMode  # idempotent


def test_factory_uses_default_config(sample_cards: list[Flashcard]) -> None:
    mode = QuizModeFactory.create("adaptive", sample_cards)
    assert len(drain(mode, correct=False)) == 9  # 3 cards x default 3 attempts


# ------------------------------------------------------------------- engine
def test_engine_checks_answers_and_records_stats(sample_cards: list[Flashcard]) -> None:
    engine = QuizEngine(SequentialMode(sample_cards, ModeConfig()))
    assert engine.next_card() == sample_cards[0]
    result = engine.answer("domain name system")
    assert result.correct
    assert engine.stats.total_questions == 1
    assert isinstance(engine.mode, SequentialMode)


def test_engine_limit_stops_early(sample_cards: list[Flashcard]) -> None:
    engine = QuizEngine(SequentialMode(sample_cards, ModeConfig()), limit=2)
    asked = 0
    while engine.next_card() is not None:
        engine.answer("x")
        asked += 1
    assert asked == 2
    assert engine.remaining == 0


def test_engine_remaining_includes_current_card(sample_cards: list[Flashcard]) -> None:
    engine = QuizEngine(SequentialMode(sample_cards, ModeConfig()))
    engine.next_card()
    assert engine.remaining == 3
    engine.answer("x")
    assert engine.remaining == 2


def test_engine_forwards_results_to_adaptive_strategy() -> None:
    engine = QuizEngine(AdaptiveMode(deck(1), ModeConfig(max_attempts=2)))
    engine.next_card()
    engine.answer("wrong")
    assert engine.next_card() is not None  # repeated because it was missed


def test_engine_rejects_invalid_limit(sample_cards: list[Flashcard]) -> None:
    with pytest.raises(ValueError, match="limit"):
        QuizEngine(SequentialMode(sample_cards, ModeConfig()), limit=0)


def test_engine_answer_without_card_raises(sample_cards: list[Flashcard]) -> None:
    engine = QuizEngine(SequentialMode(sample_cards, ModeConfig()))
    with pytest.raises(RuntimeError, match="next_card"):
        engine.answer("x")


def test_engine_next_card_twice_without_answer_raises(
    sample_cards: list[Flashcard],
) -> None:
    engine = QuizEngine(SequentialMode(sample_cards, ModeConfig()))
    engine.next_card()
    with pytest.raises(RuntimeError, match="Answer the current card"):
        engine.next_card()
