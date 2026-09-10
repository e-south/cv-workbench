"""Source-version lifecycle boundaries and recoverable mutations."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.sot_versions import (
    SotPackError,
    SotVersionError,
    activate_version,
    create_version,
    list_versions,
)


def _pack(tmp_path: Path) -> Path:
    root = tmp_path / "pack"
    for name in ("base", "experiment"):
        version = root / "versions" / name
        version.mkdir(parents=True)
        (version / "notes.txt").write_text(f"{name} fixture text\n")
    (root / "ACTIVE").write_bytes(b"base\n")
    return root


@pytest.mark.parametrize("target", ["file", "external_directory"])
def test_activation_rejects_non_version_targets(tmp_path: Path, target: str) -> None:
    root = _pack(tmp_path)
    candidate = root / "versions" / "invalid"
    if target == "file":
        candidate.write_text("Not a source directory")
    else:
        external = tmp_path / "external"
        external.mkdir()
        candidate.symlink_to(external, target_is_directory=True)

    with pytest.raises((SotPackError, SotVersionError)):
        activate_version(root, "invalid")

    assert (root / "ACTIVE").read_bytes() == b"base\n"


@pytest.mark.parametrize("surface", ["api", "cli"])
def test_activation_preserves_an_external_active_target(tmp_path: Path, surface: str) -> None:
    root = _pack(tmp_path)
    external = tmp_path / "external-selection"
    external.write_bytes(b"External fixture bytes\n")
    active = root / "ACTIVE"
    active.unlink()
    active.symlink_to(external)

    if surface == "api":
        failure = None
        try:
            activate_version(root, "experiment")
        except (SotPackError, SotVersionError) as exc:
            failure = exc
    else:
        result = CliRunner().invoke(
            app, ["sot", "activate", "experiment", "--sot-path", str(root), "--plain"]
        )

    assert external.read_bytes() == b"External fixture bytes\n"
    assert active.is_symlink()
    if surface == "api":
        assert failure is not None
        assert "External fixture bytes" not in str(failure)
    else:
        assert result.exit_code == 1
        assert "ERROR:" in result.stderr
        assert "External fixture bytes" not in result.output


@pytest.mark.parametrize("interruption", [OSError, KeyboardInterrupt])
def test_activation_restores_selection_after_a_failed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: type[BaseException]
) -> None:
    root = _pack(tmp_path)
    active = root / "ACTIVE"
    active.chmod(0o640)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    original_write = Path.write_text
    original_replace = os.replace
    interrupted = False

    def fail_direct_write(path: Path, *args, **kwargs):
        nonlocal interrupted
        if path == active:
            path.write_bytes(b"partial selection")
            interrupted = True
            raise interruption("Injected activation interruption")
        return original_write(path, *args, **kwargs)

    def fail_replacement(source, destination):
        nonlocal interrupted
        result = original_replace(source, destination)
        if Path(destination) == active and not interrupted:
            interrupted = True
            raise interruption("Injected activation interruption")
        return result

    monkeypatch.setattr(Path, "write_text", fail_direct_write)
    monkeypatch.setattr(os, "replace", fail_replacement)
    failure = None
    try:
        activate_version(root, "experiment")
    except (OSError, SotPackError, KeyboardInterrupt) as exc:
        failure = exc

    assert interrupted
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert stat.S_IMODE(active.stat().st_mode) == 0o640
    expected = KeyboardInterrupt if interruption is KeyboardInterrupt else SotPackError
    assert isinstance(failure, expected)


@pytest.mark.parametrize("invalid", ["symbolic_link", "encoding", "multiline", "embedded_null"])
def test_list_rejects_an_unsafe_selection_record(tmp_path: Path, invalid: str) -> None:
    root = _pack(tmp_path)
    active = root / "ACTIVE"
    if invalid == "symbolic_link":
        external = tmp_path / "external-selection"
        external.write_text("External fixture contents")
        active.unlink()
        active.symlink_to(external)
    elif invalid == "encoding":
        active.write_bytes(b"\xff")
    else:
        active.write_bytes(b"two\nlines\n" if invalid == "multiline" else b"nul\x00name\n")
    with pytest.raises(SotVersionError):
        list_versions(root)


@pytest.mark.parametrize("interruption", [OSError, KeyboardInterrupt])
def test_clone_removes_partial_version_after_a_failed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: type[BaseException]
) -> None:
    root = _pack(tmp_path)
    source = root / "versions" / "base"
    (source / "second.txt").write_text("Second fixture file\n")
    target = root / "versions" / "new"
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    original_copy = shutil.copyfile
    original_replace = os.replace
    interrupted = False

    def after_write(destination):
        nonlocal interrupted
        if Path(destination).is_relative_to(target) and not interrupted:
            interrupted = True
            raise interruption("Injected clone interruption")

    def fail_direct_copy(source, destination, *args, **kwargs):
        result = original_copy(source, destination, *args, **kwargs)
        after_write(destination)
        return result

    def fail_replacement(source, destination):
        result = original_replace(source, destination)
        after_write(destination)
        return result

    monkeypatch.setattr(shutil, "copyfile", fail_direct_copy)
    monkeypatch.setattr(os, "replace", fail_replacement)
    failure = None
    try:
        create_version(root, "new", "base")
    except (OSError, SotPackError, KeyboardInterrupt) as exc:
        failure = exc

    assert interrupted
    assert not target.exists()
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    expected = KeyboardInterrupt if interruption is KeyboardInterrupt else SotPackError
    assert isinstance(failure, expected)


@pytest.mark.parametrize("invalid", ["external_base", "file_link", "directory_link", "fifo"])
def test_clone_rejects_unsafe_sources(tmp_path: Path, invalid: str) -> None:
    root = _pack(tmp_path)
    source = root / "versions" / "base"
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_bytes(b"External fixture contents\n")
    if invalid == "external_base":
        source = root / "versions" / "linked"
        source.symlink_to(external, target_is_directory=True)
    elif invalid == "file_link":
        (source / "linked.txt").symlink_to(sentinel)
    elif invalid == "directory_link":
        (source / "linked").symlink_to(external, target_is_directory=True)
    else:
        os.mkfifo(source / "pipe")

    with pytest.raises((SotPackError, SotVersionError)):
        create_version(root, "new", source.name)

    assert not (root / "versions" / "new").exists()
    assert (root / "ACTIVE").read_bytes() == b"base\n"
    assert sentinel.read_bytes() == b"External fixture contents\n"


@pytest.mark.parametrize("obstacle", ["directory", "file", "dangling_link"])
def test_clone_preserves_an_occupied_destination(tmp_path: Path, obstacle: str) -> None:
    root = _pack(tmp_path)
    target = root / "versions" / "new"
    if obstacle == "directory":
        target.mkdir()
    elif obstacle == "file":
        target.write_bytes(b"Existing fixture bytes")
    else:
        target.symlink_to(tmp_path / "absent")
    before = target.lstat()
    with pytest.raises(SotPackError):
        create_version(root, "new", "base")
    assert target.lstat() == before
    if obstacle == "file":
        assert target.read_bytes() == b"Existing fixture bytes"
    assert (root / "ACTIVE").read_bytes() == b"base\n"


def test_clone_preserves_bytes_permissions_and_empty_directories(tmp_path: Path) -> None:
    root = _pack(tmp_path)
    source = root / "versions" / "base"
    source.chmod(0o750)
    (source / "notes.txt").chmod(0o640)
    (source / "empty").mkdir(mode=0o700)
    target = create_version(root, "new", "base")
    assert target == root / "versions" / "new"
    assert (target / "notes.txt").read_bytes() == b"base fixture text\n"
    assert stat.S_IMODE((target / "notes.txt").stat().st_mode) == 0o640
    assert stat.S_IMODE(target.stat().st_mode) == 0o750
    assert (target / "empty").is_dir()
    assert list((target / "empty").iterdir()) == []
    assert stat.S_IMODE((target / "empty").stat().st_mode) == 0o700
    assert (root / "ACTIVE").read_bytes() == b"base\n"


@pytest.mark.parametrize("concurrent_change", ["source", "destination"])
def test_clone_preserves_an_observed_concurrent_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, concurrent_change: str
) -> None:
    root = _pack(tmp_path)
    source_file = root / "versions" / "base" / "notes.txt"
    target = root / "versions" / "new"
    original_read = Path.read_bytes
    changed = False

    def read_then_change(path: Path):
        nonlocal changed
        payload = original_read(path)
        if path == source_file and not changed:
            changed = True
            if concurrent_change == "source":
                path.write_bytes(b"Concurrent source edit\n")
            else:
                target.mkdir()
                (target / "other.txt").write_bytes(b"Concurrent destination\n")
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_then_change)
    with pytest.raises(SotPackError):
        create_version(root, "new", "base")
    assert changed
    if concurrent_change == "source":
        assert source_file.read_bytes() == b"Concurrent source edit\n"
        assert not target.exists()
    else:
        assert [path.name for path in target.iterdir()] == ["other.txt"]
        assert (target / "other.txt").read_bytes() == b"Concurrent destination\n"
    assert (root / "ACTIVE").read_bytes() == b"base\n"


def test_activation_preserves_a_selection_changed_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _pack(tmp_path)
    active = root / "ACTIVE"
    original_write = Path.write_bytes
    changed = False

    def write_then_change(path: Path, payload: bytes):
        nonlocal changed
        result = original_write(path, payload)
        if path.parent == root and path.name.startswith(".ACTIVE.cvw-stage-") and not changed:
            changed = True
            active.write_bytes(b"Concurrent selection\n")
        return result

    monkeypatch.setattr(Path, "write_bytes", write_then_change)
    with pytest.raises(SotPackError):
        activate_version(root, "experiment")
    assert changed
    assert active.read_bytes() == b"Concurrent selection\n"
    assert sorted(p.name for p in root.iterdir()) == ["ACTIVE", "versions"]
