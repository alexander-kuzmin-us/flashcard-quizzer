"""Export session results to a file.

Another small Strategy + Factory pair: each ``ResultExporter`` knows one
file format and ``ExporterFactory`` picks one from the output file's
extension (``.json`` or ``.csv``).
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from quizzer.stats import SessionStats


class ExportError(Exception):
    """Raised when results cannot be exported. The message is user-friendly."""


class ResultExporter(ABC):
    """Strategy interface for writing session results."""

    extension: ClassVar[str] = ""

    @abstractmethod
    def export(self, stats: SessionStats, path: Path, meta: dict[str, str]) -> None:
        """Write ``stats`` to ``path``.

        Args:
            stats: The finished session.
            path: Destination file.
            meta: Extra context (deck, mode, timestamp) to include.
        """


class JSONExporter(ResultExporter):
    """Write the full session summary and every answer as JSON."""

    extension = ".json"

    def export(self, stats: SessionStats, path: Path, meta: dict[str, str]) -> None:
        """See ``ResultExporter.export``."""
        payload = {"session": meta, **stats.to_dict()}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")


class CSVExporter(ResultExporter):
    """Write one row per answer, convenient for spreadsheets."""

    extension = ".csv"
    columns: ClassVar[tuple[str, ...]] = ("front", "expected", "given", "correct")

    def export(self, stats: SessionStats, path: Path, meta: dict[str, str]) -> None:
        """See ``ResultExporter.export``."""
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.columns)
            writer.writeheader()
            for row in stats.to_dict()["answers"]:
                writer.writerow(
                    {name: _csv_safe(str(row[name])) for name in self.columns}
                )


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection in user-typed answers.

    Cells starting with ``= + - @`` are treated as formulas by Excel and
    LibreOffice, so they are prefixed with an apostrophe.
    """
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


class ExporterFactory:
    """Pick an exporter from a file extension."""

    _exporters: ClassVar[dict[str, type[ResultExporter]]] = {
        JSONExporter.extension: JSONExporter,
        CSVExporter.extension: CSVExporter,
    }

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """Return the supported extensions, e.g. ``['.csv', '.json']``."""
        return sorted(cls._exporters)

    @classmethod
    def for_path(cls, path: str | Path) -> ResultExporter:
        """Return an exporter matching ``path``'s extension.

        Raises:
            ExportError: If the extension is not supported.
        """
        suffix = Path(path).suffix.lower()
        exporter_class = cls._exporters.get(suffix)
        if exporter_class is None:
            supported = ", ".join(cls.supported_extensions())
            raise ExportError(
                f"Cannot export to '{path}': unsupported file type. Use {supported}."
            )
        return exporter_class()


def export_results(stats: SessionStats, path: str | Path, meta: dict[str, str]) -> Path:
    """Export ``stats`` to ``path`` using the matching exporter.

    Args:
        stats: The finished session.
        path: Destination file (``.json`` or ``.csv``).
        meta: Extra session context.

    Returns:
        The path written.

    Raises:
        ExportError: For unsupported extensions or write failures.
    """
    target = Path(path).expanduser()
    exporter = ExporterFactory.for_path(target)
    if target.parent and not target.parent.exists():
        raise ExportError(f"Cannot export to '{target}': folder does not exist.")
    try:
        exporter.export(stats, target, meta)
    except OSError as exc:
        raise ExportError(f"Could not write '{target}': {exc.strerror or exc}.")
    return target
