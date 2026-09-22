"""Tests for result exporters."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from quizzer.exporters import (
    CSVExporter,
    ExporterFactory,
    ExportError,
    JSONExporter,
    export_results,
)
from quizzer.models import Flashcard
from quizzer.stats import AnswerResult, SessionStats

META = {"deck": "d.json", "mode": "sequential"}


@pytest.fixture
def stats() -> SessionStats:
    result = SessionStats()
    result.record(AnswerResult(Flashcard("DNS", "Domain Name System"), "dns?", False))
    result.record(AnswerResult(Flashcard("SSH", "Secure Shell"), "secure shell", True))
    return result


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("out.json", JSONExporter), ("OUT.CSV", CSVExporter)],
)
def test_factory_selects_exporter_by_extension(filename: str, expected: type) -> None:
    assert isinstance(ExporterFactory.for_path(filename), expected)


def test_factory_rejects_unknown_extension() -> None:
    with pytest.raises(ExportError, match="Use .csv, .json"):
        ExporterFactory.for_path("results.xlsx")


def test_json_export(tmp_path: Path, stats: SessionStats) -> None:
    path = export_results(stats, tmp_path / "r.json", META)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["session"] == META
    assert data["total_questions"] == 2
    assert data["missed_terms"] == ["DNS"]


def test_csv_export(tmp_path: Path, stats: SessionStats) -> None:
    path = export_results(stats, tmp_path / "r.csv", META)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0] == {
        "front": "DNS",
        "expected": "Domain Name System",
        "given": "dns?",
        "correct": "False",
    }


def test_csv_export_neutralises_formula_injection(tmp_path: Path) -> None:
    stats = SessionStats()
    stats.record(AnswerResult(Flashcard("A", "1"), '=HYPERLINK("x")', False))
    path = export_results(stats, tmp_path / "r.csv", META)
    assert "'=HYPERLINK" in path.read_text(encoding="utf-8")


def test_export_to_missing_folder_fails_cleanly(
    tmp_path: Path, stats: SessionStats
) -> None:
    with pytest.raises(ExportError, match="folder does not exist"):
        export_results(stats, tmp_path / "nope" / "r.json", META)


def test_export_write_error_is_wrapped(
    tmp_path: Path, stats: SessionStats, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: JSONExporter, *args: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(JSONExporter, "export", boom)
    with pytest.raises(ExportError, match="Permission denied"):
        export_results(stats, tmp_path / "r.json", META)
