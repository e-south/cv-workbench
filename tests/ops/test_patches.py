"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_patches.py

Verify patch execution preserves source ownership and commits captured edits safely.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import os
from difflib import unified_diff

import pytest

from cvworkbench.ops import patches


def _diff(name, before, after):
    return "".join(
        unified_diff(before.splitlines(True), after.splitlines(True), fromfile=name, tofile=name)
    )


def _files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_patch_preserves_an_existing_temporary_filename(tmp_path, kind):
    source = tmp_path / "source"
    source.mkdir()
    target = source / "person.yaml"
    target.write_text("name: Original\n")
    note = tmp_path / "operator-note.txt"
    note.write_text("Keep this unrelated content.\n")
    temporary = source / ".cvw.patch.tmp"
    if kind == "symlink":
        temporary.symlink_to(note)
    else:
        temporary.write_text("Keep the existing source-side file.\n")
    patches.apply_patch_text(
        patch_text=_diff("person.yaml", "name: Original\n", "name: Updated\n"), cwd=source
    )
    assert target.read_text() == "name: Updated\n"
    assert note.read_text() == "Keep this unrelated content.\n"
    if kind == "symlink":
        assert temporary.is_symlink()
    else:
        assert temporary.read_text() == "Keep the existing source-side file.\n"


def test_patch_file_executes_the_bytes_it_read(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    target = source / "person.yaml"
    target.write_text("name: Original\n")
    patch = tmp_path / "edits.diff"
    patch.write_text(_diff("person.yaml", "name: Original\n", "name: Captured\n"))
    which = patches._which
    observed = []

    def edit_after_read(command):
        observed.append(command)
        patch.write_text(_diff("person.yaml", "name: Original\n", "name: Later edit\n"))
        return which(command)

    monkeypatch.setattr(patches, "_which", edit_after_read)
    patches.apply_patch_file(patch_path=patch, cwd=source)
    assert observed == ["patch"]
    assert target.read_text() == "name: Captured\n"
    assert "Later edit" in patch.read_text()


def test_source_edit_after_dry_run_is_preserved_without_partial_patch_writes(tmp_path, monkeypatch):
    first, second = tmp_path / "person.yaml", tmp_path / "projects.yaml"
    first.write_text("name: Original\n")
    second.write_text("summary: Original\n")
    diff = _diff(first.name, first.read_text(), "name: Updated\n")
    diff += _diff(second.name, second.read_text(), "summary: Updated\n")
    run = patches._run_patch
    observed = []

    def edit_after_dry_run(*args, **kwargs):
        result = run(*args, **kwargs)
        if kwargs["dry_run"]:
            observed.append(True)
            second.write_text("summary: Independent edit\n")
        return result

    monkeypatch.setattr(patches, "_run_patch", edit_after_dry_run)
    with pytest.raises(patches.PatchError):
        patches.apply_patch_text(patch_text=diff, cwd=tmp_path)
    assert observed == [True]
    assert _files(tmp_path) == {
        "person.yaml": b"name: Original\n",
        "projects.yaml": b"summary: Independent edit\n",
    }


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_tool_failure_after_writes_leaves_source_unchanged(tmp_path, monkeypatch, error):
    target = tmp_path / "person.yaml"
    target.write_text("name: Original\n")
    run = patches._run_patch
    observed = []

    def fail_after_apply(*args, **kwargs):
        result = run(*args, **kwargs)
        if not kwargs["dry_run"]:
            observed.append(True)
            raise error("patch process interrupted")
        return result

    monkeypatch.setattr(patches, "_run_patch", fail_after_apply)
    with pytest.raises(patches.PatchError if error is OSError else KeyboardInterrupt):
        patches.apply_patch_text(
            patch_text=_diff(target.name, target.read_text(), "name: Updated\n"), cwd=tmp_path
        )
    assert observed == [True]
    assert _files(tmp_path) == {"person.yaml": b"name: Original\n"}


def test_patch_creation_deletion_and_update_commit_together(tmp_path):
    updated, removed = tmp_path / "person.yaml", tmp_path / "old.yaml"
    updated.write_text("name: Original\n")
    updated.chmod(0o600)
    removed.write_text("old: true\n")
    diff = _diff(updated.name, updated.read_text(), "name: Updated\n")
    diff += "--- /dev/null\n+++ new.yaml\n@@ -0,0 +1 @@\n+new: true\n"
    diff += "--- old.yaml\n+++ /dev/null\n@@ -1 +0,0 @@\n-old: true\n"
    patches.apply_patch_text(patch_text=diff, cwd=tmp_path)
    assert _files(tmp_path) == {"person.yaml": b"name: Updated\n", "new.yaml": b"new: true\n"}
    assert updated.stat().st_mode & 0o777 == 0o600


def test_patch_distinguishes_hunk_content_from_file_headers(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("-- Original\n")
    patches.apply_patch_text(
        patch_text=_diff(target.name, target.read_text(), "++ Replacement\n"), cwd=tmp_path
    )
    assert target.read_text() == "++ Replacement\n"


def test_explicit_identical_replacement_is_valid(tmp_path):
    target = tmp_path / "person.yaml"
    target.write_text("name: Original\n")
    patches.apply_patch_text(
        patch_text="--- person.yaml\n+++ person.yaml\n@@ -1 +1 @@\n-name: Original\n+name: Original\n",
        cwd=tmp_path,
    )
    assert _files(tmp_path) == {"person.yaml": b"name: Original\n"}


@pytest.mark.parametrize("malformed", ["preamble", "missing_hunk", "truncated_hunk", "bad_counts"])
def test_malformed_patch_fails_before_tool_resolution(tmp_path, monkeypatch, malformed):
    target = tmp_path / "person.yaml"
    target.write_text("name: Original\n")
    patch = _diff(target.name, target.read_text(), "name: Updated\n")
    if malformed == "preamble":
        patch = "Unexpected non-patch instructions.\n" + patch
    elif malformed == "missing_hunk":
        patch = "--- person.yaml\n+++ person.yaml\n"
    elif malformed == "truncated_hunk":
        patch = "\n".join(patch.splitlines()[:-1]) + "\n"
    else:
        patch = patch.replace("@@ -1 +1 @@", "@@ -1,2 +1 @@")
    calls = []
    which = patches._which

    def observed(command):
        calls.append(command)
        return which(command)

    monkeypatch.setattr(patches, "_which", observed)
    with pytest.raises(patches.PatchError):
        patches.apply_patch_text(patch_text=patch, cwd=tmp_path)
    assert calls == []
    assert _files(tmp_path) == {"person.yaml": b"name: Original\n"}


@pytest.mark.parametrize("invalid", [None, False, 3, b"patch"])
def test_patch_text_requires_a_string_without_side_effects(tmp_path, invalid):
    with pytest.raises(patches.PatchError, match="must be a string"):
        patches.apply_patch_text(patch_text=invalid, cwd=tmp_path)
    assert not list(tmp_path.iterdir())


def test_unreadable_patch_text_has_a_domain_error(tmp_path):
    patch = tmp_path / "patch.diff"
    patch.write_bytes(b"\xff")
    with pytest.raises(patches.PatchError, match="could not be read"):
        patches.apply_patch_file(patch_path=patch, cwd=tmp_path)
    assert patch.read_bytes() == b"\xff"


def test_new_source_files_respect_the_callers_private_umask(tmp_path):
    previous = os.umask(0o077)
    try:
        patches.apply_patch_text(
            patch_text="--- /dev/null\n+++ private.yaml\n@@ -0,0 +1 @@\n+private: true\n",
            cwd=tmp_path,
        )
    finally:
        os.umask(previous)
    assert (tmp_path / "private.yaml").stat().st_mode & 0o777 == 0o600


def test_patch_preserves_missing_final_newline(tmp_path):
    target = tmp_path / "notes.md"
    target.write_bytes(b"Original")
    patches.apply_patch_text(
        patch_text="--- notes.md\n+++ notes.md\n@@ -1 +1 @@\n-Original\n"
        "\\ No newline at end of file\n+Updated\n\\ No newline at end of file\n",
        cwd=tmp_path,
    )
    assert target.read_bytes() == b"Updated"


@pytest.mark.parametrize(
    "case", ["duplicate", "rename", "traversal", "symlink", "directory", "existing_new"]
)
def test_unsafe_or_ambiguous_targets_fail_without_writes(tmp_path, case):
    source = tmp_path / "source"
    source.mkdir()
    target = source / "person.yaml"
    target.write_text("name: Original\n")
    diff = _diff(target.name, target.read_text(), "name: Updated\n")
    if case == "duplicate":
        diff += diff
    elif case == "rename":
        diff = diff.replace("+++ person.yaml", "+++ renamed.yaml")
    elif case == "traversal":
        diff = diff.replace("person.yaml", "../person.yaml")
    elif case == "symlink":
        (source / "alias.yaml").symlink_to(target)
        diff = diff.replace("person.yaml", "alias.yaml")
    elif case == "directory":
        (source / "directory.yaml").mkdir()
        diff = diff.replace("person.yaml", "directory.yaml")
    else:
        diff = "--- /dev/null\n+++ person.yaml\n@@ -0,0 +1 @@\n+name: Updated\n"
    before = _files(tmp_path)
    with pytest.raises(patches.PatchError):
        patches.apply_patch_text(patch_text=diff, cwd=source)
    assert _files(tmp_path) == before


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_patch_commit_failure_recovers_created_deleted_and_updated_source(
    tmp_path, monkeypatch, error
):
    from cvworkbench import storage

    updated, removed = tmp_path / "person.yaml", tmp_path / "old.yaml"
    updated.write_text("name: Original\n")
    removed.write_text("old: true\n")
    diff = _diff(updated.name, updated.read_text(), "name: Updated\n")
    diff += "--- /dev/null\n+++ new.yaml\n@@ -0,0 +1 @@\n+new: true\n"
    diff += "--- old.yaml\n+++ /dev/null\n@@ -1 +0,0 @@\n-old: true\n"
    before = _files(tmp_path)
    unlink = storage.Path.unlink
    observed = []

    def fail_after_deletion(path, *args, **kwargs):
        result = unlink(path, *args, **kwargs)
        if path == removed:
            observed.append(True)
            raise error("source deletion interrupted")
        return result

    monkeypatch.setattr(storage.Path, "unlink", fail_after_deletion)
    with pytest.raises(patches.PatchError if error is OSError else KeyboardInterrupt):
        patches.apply_patch_text(patch_text=diff, cwd=tmp_path)
    assert observed == [True]
    assert _files(tmp_path) == before
