"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_preview.py

Tests preview command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_preview_once_builds_html_without_session(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, html]",
            ]
        )
        + "\n"
    )
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "preview",
            "--once",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert "preview_file:" in result.stdout
    assert "preview_url:" not in result.stdout
    html_path = tmp_path / "var" / "dist" / "base" / "cv.html"
    assert html_path.exists()
    session_path = tmp_path / "var" / "runs" / "preview" / "session.json"
    assert not session_path.exists()


def test_preview_once_allows_project_with_explicit_sot_path(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, html]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  projects: ../var/projects",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  base_variant: base",
                f"  sot_path: {sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "variant:\n  id: base\n  outputs: [md, pdf, html]\n"
    )
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "preview",
            "--once",
            "--project",
            "job",
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert "preview_file:" in result.stdout
    assert (tmp_path / "var" / "dist" / "base" / "cv.html").exists()


def test_preview_rejects_nonlocal_host_binding(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("CVW_DEV_HOST", "0.0.0.0")

    result = runner.invoke(
        app,
        [
            "preview",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
    )

    assert result.exit_code == 2
    assert "non-local preview binding is not supported" in result.stderr
