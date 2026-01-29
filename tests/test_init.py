"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_init.py

Tests init command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_minimal_sot_sample(root: Path) -> None:
    sot_sample = root / "sot.sample"
    sot_sample.mkdir(parents=True)
    (sot_sample / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_sample / "experience.yaml").write_text("roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n")
    (sot_sample / "projects.yaml").write_text("projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n")
    (sot_sample / "skills.yaml").write_text("skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n")
    (sot_sample / "education.yaml").write_text("education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n")
    (sot_sample / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )


def _write_minimal_config(root: Path) -> None:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "workbench.yaml").write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../sot",
                "  dist: ../dist",
                "  runs: ../runs",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    (config_dir / "publish.yaml").write_text(
        "\n".join(
            [
                "publish:",
                "  variants:",
                "    - base",
            ]
        )
        + "\n"
    )


def test_init_creates_scaffold(tmp_path: Path, monkeypatch) -> None:
    template_root = tmp_path / "template"
    template_root.mkdir()
    _write_minimal_sot_sample(template_root)
    _write_minimal_config(template_root)

    monkeypatch.setenv("CVW_TEMPLATE_DIR", str(template_root))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(app, ["init", "--plain"])

    assert result.exit_code == 0
    root = Path(cwd)
    assert (root / "sot").exists()
    assert (root / "config/workbench.yaml").exists()
    assert (root / "config/variants/base.yaml").exists()
    assert (root / "registry/contexts").exists()
