"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_sot.py

Tests SoT version pack commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.config import resolve_sot_path


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  sot: ../local/sot\nvariants:\n  default: base\n")
    return config_path


def _write_minimal_sot(version_dir: Path, name: str) -> None:
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "person.yaml").write_text(f"id: {name}\nname: {name}\n")
    (version_dir / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Example",
                "    title: Engineer",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Did work",
                "        tags: [tag]",
            ]
        )
        + "\n"
    )
    (version_dir / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: proj-1",
                "    name: Project",
                "    summary: Summary",
                "    tags: [tag]",
            ]
        )
        + "\n"
    )
    (version_dir / "skills.yaml").write_text("skills:\n  - name: Python\n")
    (version_dir / "education.yaml").write_text(
        "\n".join(
            [
                "schools:",
                "  - id: school-1",
                "    name: Example University",
                "    degree: BS",
                "    start: 2010",
                "    end: 2014",
            ]
        )
        + "\n"
    )
    (version_dir / "letters.yaml").write_text("letters: []\n")


def _write_versions(root: Path) -> None:
    versions_root = root / "local" / "sot" / "versions"
    _write_minimal_sot(versions_root / "base", "base")
    (root / "local" / "sot" / "ACTIVE").write_text("base\n")


def test_sot_list_and_activate(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_versions(tmp_path)
    _write_minimal_sot(tmp_path / "local" / "sot" / "versions" / "alt", "alt")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sot",
            "list",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert "base" in result.stdout
    assert "alt" in result.stdout

    activate = runner.invoke(
        app,
        [
            "sot",
            "activate",
            "alt",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert activate.exit_code == 0
    assert "active: alt" in activate.stdout
    assert (tmp_path / "local" / "sot" / "ACTIVE").read_text().strip() == "alt"


def test_sot_new_and_diff(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_versions(tmp_path)

    runner = CliRunner()
    created = runner.invoke(
        app,
        [
            "sot",
            "new",
            "experiment",
            "--from",
            "base",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert created.exit_code == 0
    assert (tmp_path / "local" / "sot" / "versions" / "experiment").exists()

    (tmp_path / "local" / "sot" / "versions" / "experiment" / "person.yaml").write_text(
        "id: experiment\nname: Experiment\n"
    )

    diffed = runner.invoke(
        app,
        [
            "sot",
            "diff",
            "base",
            "experiment",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert diffed.exit_code == 0
    assert "Experiment" in diffed.stdout


@pytest.mark.parametrize("selection", [b"", b"\xff", b"absent\n", None])
@pytest.mark.parametrize("selector", ["explicit", "configured"])
def test_explicit_version_actions_recover_a_damaged_selection(
    tmp_path: Path, selection: bytes | None, selector: str
) -> None:
    config = _write_config(tmp_path)
    _write_versions(tmp_path)
    root = tmp_path / "local" / "sot"
    _write_minimal_sot(root / "versions" / "alt", "alt")
    active = root / "ACTIVE"
    if selection is None:
        active.unlink()
    else:
        active.write_bytes(selection)
    before = {
        path.relative_to(root): path.read_bytes()
        for path in (root / "versions").rglob("*")
        if path.is_file()
    }
    configuration = config.read_bytes()
    options = ["--sot-path", str(root)] if selector == "explicit" else ["--config", str(config)]
    runner = CliRunner()

    # Document consumers must still reject a broken active selection.
    with pytest.raises(ValueError):
        resolve_sot_path(root, config)
    compared = runner.invoke(app, ["sot", "diff", "base", "alt", *options, "--json"])
    assert compared.exit_code == 0, compared.output
    assert json.loads(compared.stdout)["data"]["diff"]
    created = runner.invoke(app, ["sot", "new", "recovered", "--from", "base", *options, "--json"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout)["data"]["from"] == "base"
    if selection is None:
        assert not active.exists()
    else:
        assert active.read_bytes() == selection
    activated = runner.invoke(app, ["sot", "activate", "recovered", *options, "--json"])
    assert activated.exit_code == 0, activated.output
    assert active.read_bytes() == b"recovered\n"
    if selection is None:
        assert stat.S_IMODE(active.stat().st_mode) == 0o600
    assert resolve_sot_path(root, config) == (root / "versions" / "recovered").resolve()
    assert config.read_bytes() == configuration
    assert all((root / path).read_bytes() == payload for path, payload in before.items())


def test_default_clone_requires_a_valid_selection(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    _write_versions(tmp_path)
    root = tmp_path / "local" / "sot"
    (root / "ACTIVE").unlink()
    result = CliRunner().invoke(
        app, ["sot", "new", "experiment", "--config", str(config), "--json"]
    )
    assert result.exit_code == 1
    assert "Active SoT file not found" in result.stderr
    assert not (root / "ACTIVE").exists()
    assert not (root / "versions" / "experiment").exists()


def test_empty_explicit_clone_base_does_not_select_a_default(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    _write_versions(tmp_path)
    root = tmp_path / "local" / "sot"
    result = CliRunner().invoke(
        app, ["sot", "new", "experiment", "--from", "", "--config", str(config), "--json"]
    )
    assert result.exit_code == 1
    assert "version name is required" in result.stderr
    assert not (root / "versions" / "experiment").exists()


def test_activation_requires_an_existing_version_container(tmp_path: Path) -> None:
    flat = tmp_path / "flat-source"
    _write_minimal_sot(flat, "base")
    before = {path.name: path.read_bytes() for path in flat.iterdir()}
    result = CliRunner().invoke(app, ["sot", "activate", "base", "--sot-path", str(flat), "--json"])
    assert result.exit_code == 1
    assert "SoT versions not initialized" in result.stderr
    assert {path.name: path.read_bytes() for path in flat.iterdir()} == before


def test_version_inventory_json_preserves_individual_names(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    _write_versions(tmp_path)
    root = tmp_path / "local" / "sot"
    _write_minimal_sot(root / "versions" / "draft, review", "draft")
    runner = CliRunner()
    result = runner.invoke(app, ["sot", "list", "--config", str(config), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["versions"] == ["base", "draft, review"]
    plain = runner.invoke(app, ["sot", "list", "--config", str(config), "--plain"])
    assert plain.exit_code == 0, plain.output
    assert "versions: base, draft, review" in plain.stdout
