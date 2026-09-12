"""Create independent source-version packs without changing their inputs."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cvworkbench.storage as storage
from cvworkbench.cli import app
from cvworkbench.ops.sot_versions import SotPackError, initialization, initialize_pack

pytestmark = pytest.mark.usefixtures("sample_workspace")


def _files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_initialize_pack_cli_copies_source_without_retargeting(tmp_path: Path) -> None:
    source = Path("sot.sample").resolve()
    (source / "empty").mkdir()
    (source / "notes.txt").write_text("Ancillary source notes.\n")
    expected = _files(source)
    config = Path("config/workbench.yaml").read_bytes()
    destination = tmp_path / "new-parent" / "pack"
    result = CliRunner().invoke(
        app,
        [
            "sot",
            "init",
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--name",
            "baseline",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "command": "sot.init",
        "data": {
            "source": str(source),
            "root": str(destination.resolve()),
            "active": "baseline",
            "version": str(destination.resolve() / "versions/baseline"),
        },
    }
    assert (destination / "ACTIVE").read_text() == "baseline\n"
    assert _files(destination / "versions/baseline") == expected
    assert (destination / "versions/baseline/empty").is_dir()
    assert _files(source) == expected
    assert Path("config/workbench.yaml").read_bytes() == config

    listed = CliRunner().invoke(app, ["sot", "list", "--sot-path", str(destination), "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["data"]["active"] == "baseline"


@pytest.mark.parametrize("selector", ["pack", "pinned"])
def test_initialize_pack_reports_the_selected_source(tmp_path: Path, selector: str) -> None:
    original = initialize_pack(source=Path("sot.sample"), destination=tmp_path / "original")
    source = original.root if selector == "pack" else original.version
    result = initialize_pack(source=source, destination=tmp_path / "copy")
    assert result.source == original.version
    assert _files(result.version) == _files(original.version)
    assert stat.S_IMODE(result.root.stat().st_mode) == 0o700
    assert stat.S_IMODE((result.root / "ACTIVE").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "name", ["", "..", "nested/name", " base", "base ", "two\nlines", "nul\x00name"]
)
def test_initialize_pack_rejects_invalid_version_names(tmp_path: Path, name: str) -> None:
    destination = tmp_path / "pack"
    with pytest.raises(SotPackError, match="version name"):
        initialize_pack(source=Path("sot.sample"), destination=destination, name=name)
    assert not destination.exists()


def test_initialize_pack_rejects_a_wrong_directory_before_reading_its_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "wrong-directory"
    source.mkdir()
    unrelated = source / "unrelated.bin"
    unrelated.write_bytes(b"Unrelated fixture bytes.")
    reads: list[Path] = []
    original_read = Path.read_bytes

    def observed_read(path: Path):
        if path == unrelated:
            reads.append(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", observed_read)
    with pytest.raises(SotPackError):
        initialize_pack(source=source, destination=tmp_path / "pack")
    assert not reads
    assert not (tmp_path / "pack").exists()


def test_initialize_pack_keeps_its_initial_active_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = initialize_pack(source=Path("sot.sample"), destination=tmp_path / "original")
    original_validate = initialization.validate_sot

    def change_active(staged: Path):
        errors = original_validate(staged)
        (original.root / "ACTIVE").write_text("changed-by-another-actor\n")
        return errors

    monkeypatch.setattr(initialization, "validate_sot", change_active)
    result = initialize_pack(source=original.root, destination=tmp_path / "copy")
    assert result.source == original.version
    assert _files(result.version) == _files(original.version)
    assert (original.root / "ACTIVE").read_text() == "changed-by-another-actor\n"


@pytest.mark.parametrize("obstacle", ["directory", "file", "symlink", "inside", "ancestor"])
def test_initialize_pack_preserves_occupied_or_overlapping_destinations(
    tmp_path: Path, obstacle: str
) -> None:
    source = Path("sot.sample").resolve()
    before = _files(source)
    destination = tmp_path / "pack"
    if obstacle == "directory":
        destination.mkdir()
        (destination / "keep.txt").write_text("Keep existing work.")
    elif obstacle == "file":
        destination.write_text("Keep existing work.")
    elif obstacle == "symlink":
        destination.symlink_to(tmp_path / "missing")
    elif obstacle == "inside":
        destination = source / "new-pack"
    else:
        destination = source.parent

    with pytest.raises(SotPackError, match="absent|overlap"):
        initialize_pack(source=source, destination=destination)
    assert _files(source) == before
    if obstacle == "directory":
        assert (destination / "keep.txt").read_text() == "Keep existing work."
    elif obstacle == "file":
        assert destination.read_text() == "Keep existing work."
    elif obstacle == "symlink":
        assert destination.is_symlink()
        assert not (tmp_path / "missing").exists()
    elif obstacle == "inside":
        assert not destination.exists()


@pytest.mark.parametrize(
    "invalid", ["missing", "schema", "yaml", "file_link", "directory_link", "fifo"]
)
def test_initialize_pack_rejects_invalid_sources_before_destination_writes(
    tmp_path: Path, invalid: str
) -> None:
    source = Path("sot.sample").resolve()
    destination = tmp_path / "new-parent/pack"
    if invalid == "missing":
        source = tmp_path / "missing"
    elif invalid == "schema":
        (source / "person.yaml").write_text("name: Sample\n")
    elif invalid == "yaml":
        (source / "person.yaml").write_text("name: [PRIVATE_FIXTURE_VALUE")
    elif invalid.endswith("link"):
        outside = tmp_path / "outside"
        outside.mkdir()
        protected = outside / "private.txt"
        protected.write_text("Private fixture content.")
        (source / "linked").symlink_to(
            outside if invalid == "directory_link" else protected,
            target_is_directory=invalid == "directory_link",
        )
    else:
        os.mkfifo(source / "named-pipe")
    result = CliRunner().invoke(
        app, ["sot", "init", "--source", str(source), "--destination", str(destination), "--json"]
    )
    assert result.exit_code == 1, result.output
    assert "ERROR:" in result.output
    assert "PRIVATE_FIXTURE_VALUE" not in result.output
    assert not destination.parent.exists()


def test_initialize_pack_rejects_an_observed_source_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path("sot.sample").resolve()
    destination = tmp_path / "pack"
    original_validate = initialization.validate_sot
    staged_paths: list[Path] = []

    def change_after_validation(staged: Path):
        staged_paths.append(staged)
        assert stat.S_IMODE(staged.stat().st_mode) == 0o700
        assert stat.S_IMODE((staged / "person.yaml").stat().st_mode) == 0o600
        errors = original_validate(staged)
        (source / "notes.txt").write_text("Intervening source edit.")
        return errors

    monkeypatch.setattr(initialization, "validate_sot", change_after_validation)
    with pytest.raises(SotPackError, match="Source changed"):
        initialize_pack(source=source, destination=destination)
    assert not destination.exists()
    assert (source / "notes.txt").read_text() == "Intervening source edit."
    assert staged_paths and all(not path.exists() for path in staged_paths)


def test_initialize_pack_preserves_a_destination_created_during_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "pack"
    original_validate = initialization.validate_sot

    def occupy_destination(staged: Path):
        errors = original_validate(staged)
        destination.mkdir()
        (destination / "keep.txt").write_text("Concurrent work.")
        return errors

    monkeypatch.setattr(initialization, "validate_sot", occupy_destination)
    with pytest.raises(SotPackError, match="must be absent"):
        initialize_pack(source=Path("sot.sample"), destination=destination)
    assert _files(destination) == {Path("keep.txt"): b"Concurrent work."}


@pytest.mark.parametrize("interruption", [OSError, KeyboardInterrupt])
def test_initialize_pack_recovers_a_failed_activation_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: type[BaseException]
) -> None:
    source = Path("sot.sample").resolve()
    before = _files(source)
    destination = tmp_path / "new-parent/pack"
    original_replace = storage.os.replace

    def interrupted_replace(staged, target):
        if Path(target) == destination / "ACTIVE":
            raise interruption("injected activation write failure")
        return original_replace(staged, target)

    monkeypatch.setattr(storage.os, "replace", interrupted_replace)
    with pytest.raises(KeyboardInterrupt if interruption is KeyboardInterrupt else SotPackError):
        initialize_pack(source=source, destination=destination)
    assert not destination.parent.exists()
    assert _files(source) == before
