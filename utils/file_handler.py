"""File handling utilities for JSON persistence.

This module extends the starter ``FileHandler`` with:

* ``read_json_file``: a standalone reader for arbitrary paths that raises a
  single, friendly ``FileReadError`` for every failure mode (missing file,
  directory instead of file, permission problems, bad encoding, oversized
  file, malformed JSON). The flashcard loader builds on this.
* Atomic writes in ``FileHandler.save_data`` so a crash or Ctrl+C in the
  middle of saving progress can never leave a half-written file behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

#: Default upper bound for JSON files we are willing to read (5 MiB).
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


class FileReadError(Exception):
    """Raised when a JSON file cannot be read or parsed.

    The message is always safe to show directly to an end user.
    """


def read_json_file(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> Any:
    """Read and parse a JSON file from an arbitrary path.

    Args:
        path: Location of the JSON file.
        max_bytes: Reject files larger than this many bytes. Guards against
            accidentally pointing the app at a huge or binary file.

    Returns:
        The decoded JSON value (usually a ``dict`` or ``list``).

    Raises:
        FileReadError: If the file is missing, unreadable, too large, not
            valid UTF-8, or not valid JSON.
    """
    file_path = Path(path)
    _check_readable(file_path, max_bytes)
    text = _read_text(file_path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FileReadError(
            f"'{file_path}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from None


def _check_readable(file_path: Path, max_bytes: int) -> None:
    """Validate that ``file_path`` is an existing file within the size limit."""
    if not file_path.exists():
        raise FileReadError(f"File not found: '{file_path}'. Check the path.")
    if file_path.is_dir():
        raise FileReadError(f"'{file_path}' is a directory, not a JSON file.")
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise FileReadError(f"Could not access '{file_path}': {exc.strerror}.")
    if size > max_bytes:
        raise FileReadError(
            f"'{file_path}' is {size:,} bytes, which exceeds the "
            f"{max_bytes:,}-byte limit for flashcard files."
        )


def _read_text(file_path: Path) -> str:
    """Read ``file_path`` as UTF-8 (a leading BOM is tolerated)."""
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except PermissionError:
        raise FileReadError(f"Permission denied when reading '{file_path}'.")
    except UnicodeDecodeError:
        raise FileReadError(f"'{file_path}' is not a UTF-8 encoded text file.")
    except OSError as exc:
        raise FileReadError(f"Could not read '{file_path}': {exc.strerror}.")
    if not text.strip():
        raise FileReadError(f"'{file_path}' is empty.")
    return text


class FileHandler:
    """Handle JSON persistence inside a single data directory."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        """Create the handler, creating ``data_dir`` (and parents) if needed.

        Args:
            data_dir: Directory in which all files are stored.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_data(self, filename: str, data: Any) -> None:
        """Atomically save JSON-serialisable data to ``filename``.

        The data is written to a temporary file in the same directory and
        then moved into place with ``os.replace``, so readers never observe
        a partially written file.

        Args:
            filename: Name of the file inside ``data_dir``.
            data: Any JSON-serialisable value.

        Raises:
            RuntimeError: If the data cannot be serialised or written.
        """
        filepath = self.data_dir / filename
        try:
            payload = json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Failed to save data to {filename}: {exc}")

        tmp_name = ""
        try:
            fd, tmp_name = tempfile.mkstemp(
                dir=self.data_dir, prefix=".tmp-", suffix=".json"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, filepath)
        except OSError as exc:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise RuntimeError(f"Failed to save data to {filename}: {exc}")

    def load_data(self, filename: str) -> Any:
        """Load JSON data from ``filename``.

        Args:
            filename: Name of the file inside ``data_dir``.

        Returns:
            The decoded JSON value, or an empty ``dict`` if the file does
            not exist (a missing save file simply means "no data yet").

        Raises:
            RuntimeError: If the file exists but cannot be read or parsed.
        """
        filepath = self.data_dir / filename
        if not filepath.exists():
            return {}
        try:
            return read_json_file(filepath)
        except FileReadError as exc:
            raise RuntimeError(f"Failed to load data from {filename}: {exc}")

    def file_exists(self, filename: str) -> bool:
        """Return ``True`` if ``filename`` exists in the data directory."""
        return (self.data_dir / filename).exists()

    def delete_file(self, filename: str) -> None:
        """Delete ``filename`` from the data directory if it exists."""
        filepath = self.data_dir / filename
        if filepath.exists():
            filepath.unlink()

    def list_files(self) -> list[str]:
        """List the names of all regular files in the data directory."""
        return sorted(f.name for f in self.data_dir.iterdir() if f.is_file())
