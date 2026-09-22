"""Tests for utils.file_handler (starter tests plus the new JSON reader)."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from utils.file_handler import FileHandler, FileReadError, read_json_file


class TestFileHandler:
    """Original starter tests, typed and extended."""

    def setup_method(self) -> None:
        """Set up a handler over a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.file_handler = FileHandler(self.temp_dir)

    def teardown_method(self) -> None:
        """Remove the temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_save_data_creates_file(self) -> None:
        data = {"test": "data", "number": 42}
        self.file_handler.save_data("test.json", data)
        assert self.file_handler.file_exists("test.json")
        assert self.file_handler.load_data("test.json") == data

    def test_load_nonexistent_file_returns_empty_dict(self) -> None:
        assert self.file_handler.load_data("nonexistent.json") == {}

    def test_save_invalid_data_raises_error(self) -> None:
        with pytest.raises(RuntimeError, match="Failed to save data"):
            self.file_handler.save_data("invalid.json", {"function": lambda x: x})

    def test_save_invalid_data_leaves_no_file(self) -> None:
        with pytest.raises(RuntimeError):
            self.file_handler.save_data("invalid.json", {"bad": object()})
        assert self.file_handler.list_files() == []

    def test_save_overwrites_atomically_without_temp_leftovers(self) -> None:
        self.file_handler.save_data("a.json", {"v": 1})
        self.file_handler.save_data("a.json", {"v": 2})
        assert self.file_handler.load_data("a.json") == {"v": 2}
        assert self.file_handler.list_files() == ["a.json"]

    def test_save_write_failure_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_replace(src: str, dst: str) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", broken_replace)
        with pytest.raises(RuntimeError, match="disk full"):
            self.file_handler.save_data("a.json", {"v": 1})
        assert self.file_handler.list_files() == []

    def test_load_corrupt_file_raises_runtime_error(self) -> None:
        (Path(self.temp_dir) / "bad.json").write_text("{nope", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Failed to load data"):
            self.file_handler.load_data("bad.json")

    def test_file_exists(self) -> None:
        assert not self.file_handler.file_exists("test.json")
        self.file_handler.save_data("test.json", {"test": "data"})
        assert self.file_handler.file_exists("test.json")

    def test_delete_file(self) -> None:
        self.file_handler.save_data("test.json", {"test": "data"})
        self.file_handler.delete_file("test.json")
        assert not self.file_handler.file_exists("test.json")

    def test_delete_nonexistent_file_no_error(self) -> None:
        self.file_handler.delete_file("nonexistent.json")

    def test_list_files(self) -> None:
        self.file_handler.save_data("file1.json", {"data": 1})
        self.file_handler.save_data("file2.json", {"data": 2})
        assert self.file_handler.list_files() == ["file1.json", "file2.json"]


def test_file_handler_creates_nested_directories(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    FileHandler(nested)
    assert nested.is_dir()


class TestReadJsonFile:
    """Every failure mode maps to one friendly FileReadError."""

    def test_reads_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "ok.json"
        path.write_text('[{"a": 1}]', encoding="utf-8")
        assert read_json_file(path) == [{"a": 1}]

    def test_tolerates_utf8_bom(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + b'{"cards": []}')
        assert read_json_file(path) == {"cards": []}

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileReadError, match="File not found"):
            read_json_file(tmp_path / "missing.json")

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileReadError, match="is a directory"):
            read_json_file(tmp_path)

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("   \n", encoding="utf-8")
        with pytest.raises(FileReadError, match="is empty"):
            read_json_file(path)

    def test_file_too_large(self, tmp_path: Path) -> None:
        path = tmp_path / "big.json"
        path.write_text("[" + "1," * 50 + "1]", encoding="utf-8")
        with pytest.raises(FileReadError, match="exceeds"):
            read_json_file(path, max_bytes=10)

    def test_non_utf8_file(self, tmp_path: Path) -> None:
        path = tmp_path / "latin1.json"
        path.write_bytes(b'["caf\xe9"]')
        with pytest.raises(FileReadError, match="not a UTF-8"):
            read_json_file(path)

    def test_malformed_json_reports_line_and_column(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text('[{"front": "a",\n}]', encoding="utf-8")
        with pytest.raises(FileReadError, match=r"not valid JSON.*line 2"):
            read_json_file(path)

    def test_permission_denied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "locked.json"
        path.write_text("[]", encoding="utf-8")

        def deny(self: Path, encoding: str | None = None) -> str:
            raise PermissionError

        monkeypatch.setattr(Path, "read_text", deny)
        with pytest.raises(FileReadError, match="Permission denied"):
            read_json_file(path)

    def test_generic_os_error_on_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "io.json"
        path.write_text("[]", encoding="utf-8")

        def fail(self: Path, encoding: str | None = None) -> str:
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(Path, "read_text", fail)
        with pytest.raises(FileReadError, match="Input/output error"):
            read_json_file(path)

    def test_stat_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "stat.json"
        path.write_text("[]", encoding="utf-8")
        real_stat = Path.stat

        def flaky_stat(self: Path, **kwargs: bool) -> os.stat_result:
            if self.name == "stat.json" and not kwargs:
                raise OSError(13, "Access denied")
            return real_stat(self, **kwargs)

        monkeypatch.setattr(Path, "stat", flaky_stat)
        monkeypatch.setattr(Path, "exists", lambda self: True)
        monkeypatch.setattr(Path, "is_dir", lambda self: False)
        with pytest.raises(FileReadError, match="Could not access"):
            read_json_file(path)
