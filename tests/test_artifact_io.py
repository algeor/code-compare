from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from pr_suggestion_metrics.artifact_io import (
    atomic_replace_text,
    iter_jsonl_objects,
    parse_jsonl_objects,
    read_jsonl_objects,
    staged_output_directory,
    write_jsonl_object_lines,
    write_jsonl_objects,
)


def test_atomic_replace_text_uses_sibling_and_replaces_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("old", encoding="utf-8")
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def record_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        replace_calls.append((source_path, destination_path))
        real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", record_replace)

    atomic_replace_text(path, "new café\n")

    assert path.read_bytes() == b"new caf\xc3\xa9\n"
    assert len(replace_calls) == 1
    temporary_path, destination_path = replace_calls[0]
    assert temporary_path.parent == path.parent
    assert destination_path == path
    assert not temporary_path.exists()


def test_atomic_replace_text_cleans_up_when_promotion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("old", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("promotion failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="promotion failed"):
        atomic_replace_text(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.iterdir()) == [path]


def test_staged_output_directory_promotes_with_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "output"
    rename_calls: list[tuple[Path, Path]] = []
    real_rename = os.rename

    def record_rename(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        rename_calls.append((source_path, destination_path))
        real_rename(source_path, destination_path)

    monkeypatch.setattr(os, "rename", record_rename)

    with staged_output_directory(path) as staging_path:
        assert staging_path.parent == path.parent
        (staging_path / "artifact.txt").write_text("complete", encoding="utf-8")

    assert (path / "artifact.txt").read_text(encoding="utf-8") == "complete"
    assert rename_calls == [(staging_path, path)]
    assert not staging_path.exists()


def test_staged_output_directory_cleans_up_on_exception(tmp_path: Path) -> None:
    path = tmp_path / "output"

    with pytest.raises(RuntimeError, match="generation failed"):
        with staged_output_directory(path) as staging_path:
            (staging_path / "partial.txt").write_text("partial", encoding="utf-8")
            raise RuntimeError("generation failed")

    assert not path.exists()
    assert not staging_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_staged_output_directory_does_not_overwrite_target(tmp_path: Path) -> None:
    path = tmp_path / "output"

    with pytest.raises(FileExistsError, match="Output target already exists"):
        with staged_output_directory(path) as staging_path:
            (staging_path / "new.txt").write_text("new", encoding="utf-8")
            path.mkdir()
            (path / "existing.txt").write_text("existing", encoding="utf-8")

    assert (path / "existing.txt").read_text(encoding="utf-8") == "existing"
    assert not staging_path.exists()


def test_parse_jsonl_objects_rejects_non_object_rows() -> None:
    with pytest.raises(ValueError, match=r"Expected a JSON object at fixture.jsonl:2"):
        parse_jsonl_objects('{"example_id": "one"}\n[]\n', source="fixture.jsonl")


def test_iter_jsonl_objects_preserves_physical_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('\n{"example_id": "one"}\n  \n{"example_id": "two"}\n', encoding="utf-8")

    assert list(iter_jsonl_objects(path)) == [
        (2, {"example_id": "one"}),
        (4, {"example_id": "two"}),
    ]


def test_iter_jsonl_objects_supports_explicit_decode_errors(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_bytes(b'{"name": "caf\xff"}\n')

    with pytest.raises(UnicodeDecodeError):
        list(iter_jsonl_objects(path))

    assert list(iter_jsonl_objects(path, errors="replace")) == [(1, {"name": "caf\ufffd"})]


def test_read_jsonl_objects_reports_path_and_line(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps({"example_id": "one"}) + "\n{invalid}\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"Invalid JSON at {path}:2"):
        read_jsonl_objects(path)


def test_write_jsonl_objects_preserves_serialization_options(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"

    write_jsonl_objects(
        path,
        [{"z": "café", "a": [1, 2]}],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert path.read_bytes() == b'{"a":[1,2],"z":"caf\xc3\xa9"}\n'


def test_write_jsonl_object_lines_preserves_serialized_bytes(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"

    write_jsonl_object_lines(path, ['{"name":"café","optional":null}'])

    assert path.read_bytes() == b'{"name":"caf\xc3\xa9","optional":null}\n'


def test_write_jsonl_objects_can_replace_atomically(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text("old\n", encoding="utf-8")

    write_jsonl_objects(path, [{"name": "café"}], ensure_ascii=False, atomic=True)

    assert path.read_bytes() == b'{"name": "caf\xc3\xa9"}\n'


def test_write_jsonl_objects_rejects_non_object_rows_before_writing(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text("existing\n", encoding="utf-8")
    invalid_rows: Any = [{"example_id": "one"}, []]

    with pytest.raises(ValueError, match=rf"Expected a JSON object at {path}:2"):
        write_jsonl_objects(path, invalid_rows)

    assert path.read_text(encoding="utf-8") == "existing\n"
