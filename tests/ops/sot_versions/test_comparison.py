"""Exercise source-version comparison through real files and CLI output."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.sot_versions import SotPackError, diff_versions

pytestmark = pytest.mark.usefixtures("sample_workspace")


@pytest.fixture
def version_pack(tmp_path: Path) -> Path:
    root = tmp_path / "pack"
    for version in ("base", "experiment"):
        shutil.copytree(Path("sot.sample"), root / "versions" / version)
    (root / "ACTIVE").write_text("base\n")
    return root


@pytest.mark.parametrize("change", ["edit", "add", "remove", "inline", "internal_link"])
def test_compare_versions_includes_declared_snippet_changes(
    version_pack: Path, change: str
) -> None:
    right = version_pack / "versions/experiment"
    target = right / "snippets/letter_open.md"
    old_text = target.read_text().strip()
    new_text = "A revised opening for this opportunity."
    if change == "edit":
        target.write_text(new_text + "\n")
    elif change == "internal_link":
        internal = target.with_name("internal.md")
        target.rename(internal)
        target.symlink_to(internal.name)
        internal.write_text(new_text + "\n")
    elif change == "remove":
        target.unlink()
    else:
        manifest = right / "snippets.yaml"
        snippets = yaml.safe_load(manifest.read_text())
        extra = {"id": "extra", "scope": "letter-open"}
        if change == "add":
            extra["path"] = "snippets/extra.md"
            (right / "snippets/extra.md").write_text(new_text + "\n")
        else:
            extra["text"] = new_text
        snippets["snippets"].append(extra)
        manifest.write_text(yaml.safe_dump(snippets))
    before = {str(p): p.read_bytes() for p in version_pack.rglob("*") if p.is_file()}

    diff = diff_versions(version_pack, "base", "experiment")
    if change == "remove":
        assert f"-{old_text}" in diff
    else:
        assert new_text in diff
    if change in {"edit", "remove", "internal_link"}:
        assert "snippets/letter_open.md" in diff
    if change == "add":
        assert "snippets/extra.md" in diff

    result = CliRunner().invoke(
        app, ["sot", "diff", "base", "experiment", "--sot-path", str(version_pack), "--json"]
    )
    assert result.exit_code == 0, result.stdout
    assert (new_text if change != "remove" else old_text) in result.stdout
    assert {str(p): p.read_bytes() for p in version_pack.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("changed", [False, True])
def test_version_diff_json_is_machine_readable(version_pack: Path, changed: bool) -> None:
    if changed:
        target = version_pack / "versions/experiment/snippets/letter_open.md"
        target.write_text("A new opening.\n")
    expected_diff = diff_versions(version_pack, "base", "experiment")
    result = CliRunner().invoke(
        app, ["sot", "diff", "base", "experiment", "--sot-path", str(version_pack), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "command": "sot.diff",
        "data": {
            "root": str(version_pack.resolve()),
            "left": "base",
            "right": "experiment",
            "diff": expected_diff,
        },
    }
    if not changed:
        assert expected_diff == ""


@pytest.mark.parametrize(
    "escape",
    ["absolute", "traversal", "snippet_link", "version_link", "source_link", "manifest_link"],
)
def test_diff_rejects_reads_outside_named_versions(
    version_pack: Path, monkeypatch: pytest.MonkeyPatch, escape: str
) -> None:
    outside = version_pack.parent / "outside"
    shutil.copytree(Path("sot.sample"), outside)
    protected = outside / "private.md"
    protected.write_text("Private fixture content must not be read.\n")
    right = version_pack / "versions/experiment"
    if escape == "version_link":
        shutil.rmtree(right)
        right.symlink_to(outside, target_is_directory=True)
    elif escape in {"source_link", "manifest_link"}:
        filename = "person.yaml" if escape == "source_link" else "snippets.yaml"
        (right / filename).unlink()
        (right / filename).symlink_to(outside / filename)
    else:
        manifest = right / "snippets.yaml"
        snippets = yaml.safe_load(manifest.read_text())
        if escape == "absolute":
            path = str(protected)
        elif escape == "traversal":
            path = "../../../outside/private.md"
        else:
            (right / "snippets/private.md").symlink_to(protected)
            path = "snippets/private.md"
        snippets["snippets"].append({"id": "private", "scope": "letter-open", "path": path})
        manifest.write_text(yaml.safe_dump(snippets))

    original_read = Path.read_text
    forbidden_reads: list[Path] = []

    def observed_read(path: Path, *args, **kwargs):
        if path.resolve().is_relative_to(outside):
            forbidden_reads.append(path)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", observed_read)
    with pytest.raises(SotPackError, match="within|relative"):
        diff_versions(version_pack, "base", "experiment")
    result = CliRunner().invoke(
        app, ["sot", "diff", "base", "experiment", "--sot-path", str(version_pack), "--plain"]
    )
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert not forbidden_reads
    assert "Private fixture content" not in result.output


@pytest.mark.parametrize("invalid", ["yaml", "utf8", "io"])
def test_diff_rejects_unreadable_source_with_actionable_cli_error(
    version_pack: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    target = version_pack / "versions/experiment/snippets.yaml"
    if invalid == "yaml":
        target.write_text("snippets: [PRIVATE_FIXTURE_VALUE")
    elif invalid == "utf8":
        target.write_bytes(b"\xff")
    else:
        original_read = Path.read_text

        def failed_read(path: Path, *args, **kwargs):
            if path == target:
                raise PermissionError("injected read failure")
            return original_read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failed_read)
    with pytest.raises(SotPackError, match="snippets.yaml"):
        diff_versions(version_pack, "base", "experiment")
    result = CliRunner().invoke(
        app, ["sot", "diff", "base", "experiment", "--sot-path", str(version_pack), "--plain"]
    )
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert "snippets.yaml" in result.output
    assert "PRIVATE_FIXTURE_VALUE" not in result.output
