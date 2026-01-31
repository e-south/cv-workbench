"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ux/test_init.py

Tests init command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.scaffold import resolve_template_root


def _write_minimal_sot_sample(root: Path) -> None:
    sot_sample = root / "sot.sample"
    sot_sample.mkdir(parents=True)
    (sot_sample / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_sample / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_sample / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_sample / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_sample / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_sample / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )


def _write_minimal_theme(root: Path) -> None:
    theme_root = root / "build" / "themes" / "default"
    (theme_root / "pandoc").mkdir(parents=True, exist_ok=True)
    (theme_root / "styles" / "pdf").mkdir(parents=True, exist_ok=True)
    (theme_root / "styles" / "html").mkdir(parents=True, exist_ok=True)
    (theme_root / "theme.yaml").write_text(
        "\n".join(
            [
                "id: default",
                "description: Default theme",
                "routes:",
                "  pdf:",
                "    to: latex",
                "    pdf_engine: xelatex",
                "    template: default",
                "    defaults:",
                "      - pandoc/common.defaults.yaml",
                "      - pandoc/pdf.defaults.yaml",
                "  html_preview:",
                "    to: html5",
                "    template: default",
                "    defaults:",
                "      - pandoc/common.defaults.yaml",
                "      - pandoc/html.defaults.yaml",
                "  docx:",
                "    to: docx",
                "    template: default",
                "    defaults:",
                "      - pandoc/common.defaults.yaml",
                "      - pandoc/docx.defaults.yaml",
            ]
        )
        + "\n"
    )
    (theme_root / "pandoc" / "common.defaults.yaml").write_text("standalone: true\n")
    (theme_root / "pandoc" / "pdf.defaults.yaml").write_text(
        "variables:\n  geometry: margin=0.8in\n"
    )
    (theme_root / "pandoc" / "html.defaults.yaml").write_text("standalone: true\n")
    (theme_root / "pandoc" / "docx.defaults.yaml").write_text("standalone: true\n")
    (theme_root / "styles" / "pdf" / "modern.tex").write_text(
        "\\usepackage{setspace}\n\\setstretch{1.05}\n"
    )
    (theme_root / "styles" / "html" / "modern.css").write_text(
        "body { font-family: sans-serif; }\\n"
    )


def _write_minimal_config(root: Path) -> None:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "workbench.yaml").write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../local/sot",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "render:",
                "  themes_dir: ../build/themes",
                "  theme: default",
                "  style_preset: modern",
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
    (config_dir / "site-sync.yaml").write_text(
        "\n".join(
            [
                "site:",
                "  repo_path: ../site",
                "  publish_variant: base",
                "  cv_markdown: src/content/cv/cv.md",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )


def test_init_creates_scaffold(tmp_path: Path, monkeypatch) -> None:
    template_root = tmp_path / "template"
    template_root.mkdir()
    _write_minimal_sot_sample(template_root)
    _write_minimal_theme(template_root)
    _write_minimal_config(template_root)

    monkeypatch.setenv("CVW_TEMPLATE_DIR", str(template_root))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(app, ["init", "--plain"])

    assert result.exit_code == 0
    root = Path(cwd)
    assert (root / "local/sot").exists()
    assert (root / "config/workbench.yaml").exists()
    assert (root / "config/variants/base.yaml").exists()
    assert (root / "config/site-sync.yaml").exists()
    assert (root / "var/dist").exists()
    assert (root / "var/runs").exists()
    assert (root / "var/drafts").exists()
    assert (root / "var/reviews").exists()
    assert (root / "var/registry/contexts").exists()
    assert (root / "var/projects").exists()
    assert (root / "build/themes/default/theme.yaml").exists()


def test_default_template_root_contains_scaffold() -> None:
    template_root = resolve_template_root()

    assert (template_root / "sot.sample").exists()
    assert (template_root / "config/workbench.yaml").exists()
