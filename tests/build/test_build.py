"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_build.py

Tests build pipeline behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cvworkbench.build.pipeline as pipeline_module
from cvworkbench.build.rendering import RenderError
from cvworkbench.cli import app


def test_build_generates_markdown() -> None:
    output_path = Path("var/dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert "Alex Example" in content
    assert ".tag-" not in content


def test_build_marks_publication_roles() -> None:
    output_path = Path("var/dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    content = output_path.read_text()
    assert "Alex Example\\*" in content


def test_create_run_dir_adds_suffix_when_timestamp_collides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(pipeline_module, "datetime", FrozenDateTime)

    runs_root = tmp_path / "var" / "runs"
    first = pipeline_module.create_run_dir(runs_root)
    second = pipeline_module.create_run_dir(runs_root)

    assert first.name == "2026-01-01T00-00-00Z"
    assert second.name == "2026-01-01T00-00-00Z-01"


def test_build_project_writes_outputs_to_project_run_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
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
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--project",
            "job",
            "--format",
            "md",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    project_runs = sorted((tmp_path / "var" / "runs" / "projects" / "job").iterdir())
    assert len(project_runs) == 1
    assert (project_runs[0] / "cv.md").exists()
    assert not (tmp_path / "var" / "dist" / "base" / "cv.md").exists()


def test_build_canonical_matches_variant_selection(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
                "  include_tags: [core]",
                "  max_bullets_per_role: 1",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
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
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: core-1",
                "        text: Keep first core bullet.",
                "        tags: [core]",
                "      - id: core-2",
                "        text: Drop second core bullet by max limit.",
                "        tags: [core]",
                "      - id: extra-1",
                "        text: Drop unmatched bullet.",
                "        tags: [other]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: kept-project",
                "    name: Keep Project",
                "    summary: Keep this summary.",
                "    tags: [core]",
                "  - id: dropped-project",
                "    name: Drop Project",
                "    summary: Drop this summary.",
                "    tags: [other]",
            ]
        )
        + "\n"
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

    result = pipeline_module.build_documents(
        sot_path=sot_path,
        config_path=config_path,
        variant_id="base",
        formats=["md"],
    )

    canonical = result.canonical_path.read_text()

    assert "Keep first core bullet." in canonical
    assert "Drop second core bullet by max limit." not in canonical
    assert "Drop unmatched bullet." not in canonical
    assert "Keep Project" in canonical
    assert "Keep this summary." in canonical
    assert "Drop Project" not in canonical
    assert "Drop this summary." not in canonical


def test_build_rejects_formats_that_normalize_to_empty() -> None:
    with pytest.raises(ValueError, match="No output formats selected"):
        pipeline_module.build_documents(
            sot_path=Path("sot.sample"),
            config_path=Path("config/workbench.yaml"),
            variant_id="base",
            formats=["   "],
        )


def test_build_render_failure_does_not_wait_for_manifest_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    metadata_started = threading.Event()
    metadata_release = threading.Event()
    metadata_finished = threading.Event()

    def fake_collect_manifest_metadata(**kwargs):
        metadata_started.set()
        metadata_release.wait(timeout=1.0)
        metadata_finished.set()
        return None

    def fake_render_documents(requests, **kwargs) -> None:
        first = list(requests)[0]
        first.output_path.write_text("rendered")
        after_each_success = kwargs.get("after_each_success")
        if after_each_success is not None:
            after_each_success(first)
        assert metadata_started.wait(timeout=0.2)
        raise RenderError("render failed")

    monkeypatch.setattr(
        pipeline_module, "collect_manifest_metadata", fake_collect_manifest_metadata
    )
    monkeypatch.setattr(pipeline_module, "render_documents", fake_render_documents)

    start = time.monotonic()
    with pytest.raises(RenderError, match="render failed"):
        pipeline_module.build_documents(
            sot_path=Path("sot.sample"),
            config_path=Path("config/workbench.yaml"),
            variant_id="base",
            formats=["md"],
            run_dir=tmp_path / "var" / "runs" / "single",
            dist_dir=tmp_path / "var" / "dist" / "base",
        )
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    metadata_release.set()
    assert metadata_finished.wait(timeout=1.0)


def test_build_project_applies_project_ops_without_mutating_base_sot(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
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
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf]\n")
    (proposals_dir / "patch.yaml").write_text(
        "\n".join(
            [
                "patch:",
                "  format: project-ops",
                "  operations:",
                "    - op: replace-experience-bullet",
                "      role_id: role",
                "      bullet_id: b1",
                "      old_text: Did work",
                "      new_text: Delivered measurable outcomes",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--project",
            "job",
            "--format",
            "md",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    project_runs = sorted((tmp_path / "var" / "runs" / "projects" / "job").iterdir())
    assert len(project_runs) == 1
    output_text = (project_runs[0] / "cv.md").read_text()
    assert "Delivered measurable outcomes" in output_text
    assert "Delivered measurable outcomes" not in (sot_path / "experience.yaml").read_text()


def test_build_project_applies_project_summary_ops_without_mutating_base_sot(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
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
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf]\n")
    (proposals_dir / "patch.yaml").write_text(
        "\n".join(
            [
                "patch:",
                "  format: project-ops",
                "  operations:",
                "    - op: replace-project-summary",
                "      project_id: p1",
                "      old_text: Summary",
                "      new_text: Tailored project summary",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--project",
            "job",
            "--format",
            "md",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    project_runs = sorted((tmp_path / "var" / "runs" / "projects" / "job").iterdir())
    assert len(project_runs) == 1
    output_text = (project_runs[0] / "cv.md").read_text()
    assert "Tailored project summary" in output_text
    assert "Tailored project summary" not in (sot_path / "projects.yaml").read_text()
