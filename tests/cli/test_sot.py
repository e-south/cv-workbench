"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_sot.py

Tests SoT version pack commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


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
    assert (tmp_path / "sot" / "versions" / "experiment").exists()

    (tmp_path / "sot" / "versions" / "experiment" / "person.yaml").write_text(
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
