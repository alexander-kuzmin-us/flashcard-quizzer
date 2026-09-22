"""Tests for cross-session progress tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quizzer.models import Flashcard
from quizzer.progress import CardRecord, ProgressStore, progress_filename
from quizzer.stats import AnswerResult

DNS = Flashcard("DNS", "Domain Name System")
TLS = Flashcard("TLS", "Transport Layer Security")


def make_store(tmp_path: Path, deck: str = "deck.json") -> ProgressStore:
    return ProgressStore(tmp_path / deck, tmp_path / "progress")


def test_card_record_properties() -> None:
    assert CardRecord().accuracy == 0.0
    record = CardRecord(attempts=4, correct=3)
    assert record.misses == 1
    assert record.accuracy == 75.0


def test_progress_filename_is_sanitised_and_unique(tmp_path: Path) -> None:
    name = progress_filename(tmp_path / "my deck (v2)!.json")
    assert name.startswith("my_deck__v2__-")
    assert name.endswith(".json")
    assert "/" not in name and ".." not in name
    other = progress_filename(tmp_path / "sub" / "my deck (v2)!.json")
    assert name != other


def test_progress_filename_handles_symbol_only_names(tmp_path: Path) -> None:
    assert progress_filename(tmp_path / "!!!.json").startswith("___-")


def test_round_trip_update_save_load(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.load() == []
    store.update(
        [
            AnswerResult(DNS, "x", False),
            AnswerResult(DNS, "y", True),
            AnswerResult(TLS, "z", True),
        ]
    )
    store.save()

    reloaded = make_store(tmp_path)
    assert reloaded.load() == []
    assert reloaded.records["DNS"] == CardRecord(2, 1)
    assert reloaded.miss_counts() == {"DNS": 1, "TLS": 0}
    assert reloaded.path.exists()


def test_reset_deletes_history(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.update([AnswerResult(DNS, "x", False)])
    store.save()
    store.reset()
    assert not store.path.exists()
    assert store.records == {}


def test_corrupt_progress_file_is_ignored_with_warning(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.path.write_text("{not json", encoding="utf-8")
    warnings = store.load()
    assert warnings and "could not be read" in warnings[0]
    assert store.records == {}


@pytest.mark.parametrize("payload", [[1, 2], {"cards": [1]}, {"cards": "x"}])
def test_unexpected_progress_format_is_ignored(tmp_path: Path, payload: object) -> None:
    store = make_store(tmp_path)
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert "unexpected format" in store.load()[0]


def test_invalid_entries_are_skipped_individually(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    cards = {
        "good": {"attempts": 2, "correct": 1},
        "negative": {"attempts": -1, "correct": 0},
        "too_many_correct": {"attempts": 1, "correct": 2},
        "bool": {"attempts": True, "correct": 0},
        "string": {"attempts": "3", "correct": 1},
        "not_a_dict": 5,
    }
    store.path.write_text(json.dumps({"cards": cards}), encoding="utf-8")
    warnings = store.load()
    assert list(store.records) == ["good"]
    assert len(warnings) == 5
