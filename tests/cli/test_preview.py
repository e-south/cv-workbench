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


def test_preview_once_reports_invalid_variant_catalog_without_traceback(tmp_path: Path) -> None:
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
    (variants_dir / "bad.yaml").write_text("not_variant: true\n")
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

    assert result.exit_code != 0
    assert "Variant file must contain a 'variant' mapping" in (result.stderr or "")
    assert "Traceback" not in (result.stderr or "")


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
    project_sot_path = tmp_path / "sot.project"
    project_sot_path.mkdir(parents=True, exist_ok=True)
    (project_sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (project_sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (project_sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (project_sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (project_sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (project_sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    override_sot_path = tmp_path / "sot.override"
    override_sot_path.mkdir(parents=True, exist_ok=True)
    (override_sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (override_sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Override work\n        tags: [core]\n"
    )
    (override_sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (override_sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (override_sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (override_sot_path / "letters.yaml").write_text(
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
                f"  sot_path: {project_sot_path}",
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
            str(override_sot_path),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert "preview_file:" in result.stdout
    output_path = tmp_path / "var" / "runs" / "preview" / "job" / "cv.html"
    assert output_path.exists()
    assert "Override work" in output_path.read_text()
    assert "Did work" not in output_path.read_text()
    assert not (tmp_path / "var" / "dist" / "base" / "cv.html").exists()


def test_preview_once_applies_project_ops_without_writing_shared_dist(tmp_path: Path) -> None:
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
    output_path = tmp_path / "var" / "runs" / "preview" / "job" / "cv.html"
    assert output_path.exists()
    assert "Delivered measurable outcomes" in output_path.read_text()
    assert not (tmp_path / "var" / "dist" / "base" / "cv.html").exists()
    assert not (tmp_path / "var" / "runs" / "preview" / "job" / "sot").exists()


def test_preview_once_renders_project_summary_ops(tmp_path: Path) -> None:
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
    output_path = tmp_path / "var" / "runs" / "preview" / "job" / "cv.html"
    assert output_path.exists()
    assert "Tailored project summary" in output_path.read_text()
    assert not (tmp_path / "var" / "dist" / "base" / "cv.html").exists()
    assert not (tmp_path / "var" / "runs" / "preview" / "job" / "sot").exists()


def test_preview_once_project_override_stays_pinned_to_explicit_version_dir(tmp_path: Path) -> None:
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

    version_root = tmp_path / "sot.versions"
    version_one = version_root / "versions" / "v1"
    version_two = version_root / "versions" / "v2"
    version_one.mkdir(parents=True, exist_ok=True)
    version_two.mkdir(parents=True, exist_ok=True)
    (version_root / "ACTIVE").write_text("v2\n")
    for target, bullet_text in (
        (version_one, "Pinned version work"),
        (version_two, "Active version work"),
    ):
        (target / "person.yaml").write_text("id: sample\nname: Sample\n")
        (target / "experience.yaml").write_text(
            "\n".join(
                [
                    "roles:",
                    "  - id: role",
                    "    company: Co",
                    "    title: Title",
                    "    start: 2020",
                    "    bullets:",
                    f"      - id: b1\n        text: {bullet_text}\n        tags: [core]",
                ]
            )
            + "\n"
        )
        (target / "projects.yaml").write_text(
            "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
        )
        (target / "skills.yaml").write_text(
            "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
        )
        (target / "education.yaml").write_text(
            "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
        )
        (target / "letters.yaml").write_text(
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
                f"  sot_path: {version_root}",
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
            str(version_one),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    output_path = tmp_path / "var" / "runs" / "preview" / "job" / "cv.html"
    assert output_path.exists()
    html = output_path.read_text()
    assert "Pinned version work" in html
    assert "Active version work" not in html


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
