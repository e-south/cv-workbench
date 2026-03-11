"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_review.py

Tests reviewpack and import-docx commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

import cvworkbench.ops.review as review_module
from cvworkbench.cli import app
from cvworkbench.config import resolve_drafts_path, resolve_reviews_path


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  projects: ../var/projects",
                "  reviews: ../var/reviews",
                "  sot: ../local/sot",
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
                "  outputs: [md, pdf, docx]",
            ]
        )
        + "\n"
    )
    return workbench


def _write_run_manifest(root: Path, run_id: str, variant_id: str, canonical: str) -> None:
    run_dir = root / "var" / "runs" / run_id
    _write_run_manifest_at(run_dir, variant_id=variant_id, canonical=canonical)


def _write_project_run_manifest(
    root: Path,
    project_id: str,
    run_id: str,
    variant_id: str,
    canonical: str,
) -> None:
    run_dir = root / "var" / "runs" / "projects" / project_id / run_id
    _write_run_manifest_at(run_dir, variant_id=variant_id, canonical=canonical)


def _write_project_manifest(root: Path, project_id: str, variant_id: str = "base") -> Path:
    project_dir = root / "var" / "projects" / project_id
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                f"  id: {project_id}",
                f"  base_variant: {variant_id}",
                f"  sot_path: {root / 'local' / 'sot'}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "\n".join(
            [
                "variant:",
                f"  id: {variant_id}",
                "  outputs: [md, pdf, docx]",
            ]
        )
        + "\n"
    )
    (proposals_dir / "patch.yaml").write_text(
        "patch:\n  format: unified-diff\n  diff: \"\"\n"
    )
    return project_dir


def _write_run_manifest_at(
    run_dir: Path,
    *,
    variant_id: str,
    canonical: str,
    review_ready: bool = False,
    bullet_text: str = "x",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "canonical.md").write_text(canonical)
    outputs = {"md": "cv.md"}
    (run_dir / "cv.md").write_text(canonical)
    if review_ready:
        outputs["pdf"] = "cv.pdf"
        outputs["docx"] = "cv.docx"
        (run_dir / "cv.pdf").write_bytes(b"pdf")
        (run_dir / "cv.docx").write_bytes(b"docx")
        (run_dir / "selection.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "b1",
                            "type": "bullet",
                            "included": True,
                            "text": bullet_text,
                            "role_id": "r1",
                        }
                    ]
                }
            )
        )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "formats": list(outputs),
                "outputs": outputs,
                "variant": {"id": variant_id},
                "resume": {"path": "resume.json", "hash": "hash"},
            },
            indent=2,
        )
        + "\n"
    )


def _write_minimal_sot(root: Path) -> Path:
    sot_path = root / "local" / "sot"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample User\n")
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Example Co",
                "    title: Engineer",
                "    start: 2021",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Delivered outcomes.",
                "        tags:",
                "          - impact",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: project-1\n    name: Example Project\n    summary: Example summary.\n    tags:\n      - sample\n"
    )
    (sot_path / "skills.yaml").write_text(
        "skills:\n  - id: skill-1\n    name: Languages\n    keywords:\n      - Python\n"
    )
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: edu-1\n    institution: Example University\n    area: Computer Science\n    tags:\n      - sample\n"
    )
    (sot_path / "letters.yaml").write_text(
        "\n".join(
            [
                "letters:",
                "  - id: default-letter",
                "    title: Cover Letter",
                "    salutation: Dear Hiring Manager,",
                "    closing: Sincerely,",
                "    sections:",
                "      - id: intro",
                "        text: Intro text.",
                "        tags:",
                "          - general",
            ]
        )
        + "\n"
    )
    return sot_path


def test_reviewpack_creates_bundle(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "2026-01-01T00-00-00Z",
        variant_id="base",
        canonical="before\n",
        review_ready=True,
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    out_dir = resolve_reviews_path(config_path) / "base"
    assert (out_dir / "cv.docx").exists()
    assert (out_dir / "cv.pdf").exists()
    assert (out_dir / "review.md").exists()


def test_reviewpack_requires_runs(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code != 0
    assert "No runs available" in (result.stderr or "")
    assert "workflow --id review.import" in (result.stderr or "")


def test_reviewpack_ignores_invalid_run_dirs_when_valid_run_exists(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "2026-01-02T00-00-00Z",
        variant_id="base",
        canonical="before\n",
        review_ready=True,
    )
    invalid_dir = tmp_path / "var" / "runs" / "2026-01-01T00-00-00Z"
    invalid_dir.mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    out_dir = resolve_reviews_path(config_path) / "base"
    assert (out_dir / "cv.docx").exists()
    assert (out_dir / "cv.pdf").exists()


def test_reviewpack_rejects_manifest_outputs_outside_run_dir(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    run_dir = tmp_path / "var" / "runs" / "2026-01-02T00-00-00Z"
    _write_run_manifest_at(
        run_dir,
        variant_id="base",
        canonical="before\n",
        review_ready=True,
    )
    (tmp_path / "secret.docx").write_bytes(b"secret")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["outputs"]["docx"] = "../../../secret.docx"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code != 0
    assert "escapes run directory" in (result.stderr or "")
    assert not (resolve_reviews_path(config_path) / "base").exists()


def test_import_docx_writes_patch(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", "before\n")

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    assert drafts_dir.exists()
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    notes_files = list(drafts_dir.rglob("notes.md"))
    assert notes_files
    assert "not directly applyable to SoT" in notes_files[0].read_text()


def test_import_docx_generates_applyable_patch_for_experience_bullet_edits(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    canonical = "\n".join(
        [
            "## Experience",
            "",
            "### Engineer - Example Co",
            "2021 — Present",
            "",
            "- Delivered outcomes.",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace("Delivered outcomes.", "Delivered measurable outcomes.")

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"][0]["op"] == "replace-experience-bullet"
    notes_files = list(drafts_dir.rglob("notes.md"))
    assert notes_files
    notes_text = notes_files[0].read_text()
    assert "- apply_status: ready" in notes_text

    apply_result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(patch_files[0].parent),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert apply_result.exit_code == 0
    assert "Delivered measurable outcomes." in (sot_path / "experience.yaml").read_text()


def test_import_docx_normalizes_wrapped_markdown_without_forcing_review_diff_only(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_minimal_sot(tmp_path)
    canonical = "\n".join(
        [
            "# Sample User",
            "",
            "## Experience",
            "",
            "### Engineer - Example Co",
            "2021 — Present",
            "",
            "- Delivered outcomes.",
            "",
            "## Publications",
            "",
            "### Example Paper",
            "[Sample User]{.author .role-self}, Other Author Nature | 2024 | 1, 1–2",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "\n".join(
            [
                "# Sample User",
                "",
                "## Experience",
                "",
                "### Engineer - Example Co",
                "",
                "2021 --- Present",
                "",
                "- Delivered",
                "  outcomes.",
                "",
                "## Publications",
                "",
                "### Example Paper",
                "Sample User\\*, Other Author Nature \\| 2024 \\| 1, 1--2",
                "",
            ]
        )

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"] == []

    notes_files = list(resolve_drafts_path(config_path).rglob("notes.md"))
    assert notes_files
    assert "- apply_status: ready_no_changes" in notes_files[0].read_text()
    assert "next_step: Review notes.md; the normalized patch is a verified no-op" in result.stdout


def test_import_docx_normalizes_flattened_noneditable_sections_without_forcing_review_diff_only(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_minimal_sot(tmp_path)
    canonical = "\n".join(
        [
            "# Sample User",
            "",
            "## Experience",
            "",
            "### Engineer - Example Co",
            "2021 — Present",
            "",
            "- Delivered outcomes.",
            "",
            "## Projects",
            "",
            "### Example Project",
            "Example summary.",
            "",
            "## Education",
            "",
            "### Example State University",
            "BS - Computer Science",
            "2014 — 2018",
            "",
            "## References",
            "",
            "### Dr. Jane Advisor",
            "Professor | Example University",
            "PhD Advisor | jane.advisor@example.edu",
            "Available upon request.",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "\n".join(
            [
                "# Sample User",
                "",
                "## Experience",
                "",
                "### Engineer - Example Co",
                "",
                "2021 --- Present",
                "",
                "- Delivered outcomes.",
                "",
                "## Projects",
                "",
                "### Example Project",
                "",
                "Example summary.",
                "",
                "## Education",
                "",
                "### Example State University",
                "",
                "BS - Computer Science 2014 --- 2018",
                "",
                "## References",
                "",
                "### Dr. Jane Advisor",
                "",
                "Professor \\| Example University PhD Advisor \\| jane.advisor@example.edu Available upon request.",
                "",
            ]
        )

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"] == []

    notes_files = list(resolve_drafts_path(config_path).rglob("notes.md"))
    assert notes_files
    assert "- apply_status: ready_no_changes" in notes_files[0].read_text()


def test_import_docx_maps_duplicate_experience_bullets_by_position(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Example Co",
                "    title: Engineer",
                "    start: 2021",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Delivered outcomes.",
                "        tags:",
                "          - impact",
                "      - id: bullet-2",
                "        text: Delivered outcomes.",
                "        tags:",
                "          - impact",
            ]
        )
        + "\n"
    )
    canonical = "\n".join(
        [
            "## Experience",
            "",
            "### Engineer - Example Co",
            "2021 — Present",
            "",
            "- Delivered outcomes.",
            "",
            "- Delivered outcomes.",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace(
            "- Delivered outcomes.\n\n- Delivered outcomes.",
            "- Delivered outcomes.\n\n- Delivered measurable outcomes.",
        )

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files

    apply_result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(patch_files[0].parent),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert apply_result.exit_code == 0
    updated = yaml.safe_load((sot_path / "experience.yaml").read_text())
    assert isinstance(updated, dict)
    bullets = updated["roles"][0]["bullets"]
    assert bullets[0]["text"] == "Delivered outcomes."
    assert bullets[1]["text"] == "Delivered measurable outcomes."


def test_import_docx_generates_applyable_patch_for_filtered_project_summary_edits(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    base_variant_path = config_path.parent / "variants" / "base.yaml"
    base_variant_path.write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, docx]",
                "  include_tags: [sample]",
            ]
        )
        + "\n"
    )
    sot_path = _write_minimal_sot(tmp_path)
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags: [sample]",
                "  - id: project-2",
                "    name: Hidden Project",
                "    summary: Hidden summary.",
                "    tags: [internal]",
            ]
        )
        + "\n"
    )
    canonical = "\n".join(
        [
            "## Projects",
            "",
            "### Example Project",
            "Example summary.",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace("Example summary.", "Tailored example summary.")

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"][0]["op"] == "replace-project-summary"

    apply_result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(patch_files[0].parent),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert apply_result.exit_code == 0
    updated_projects = yaml.safe_load((sot_path / "projects.yaml").read_text())
    assert updated_projects["projects"][0]["summary"] == "Tailored example summary."
    assert updated_projects["projects"][1]["summary"] == "Hidden summary."


def test_import_docx_keeps_review_diff_only_for_unsupported_heading_edits(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_minimal_sot(tmp_path)
    canonical = "\n".join(
        [
            "## Experience",
            "",
            "### Engineer - Example Co",
            "2021 — Present",
            "",
            "- Delivered outcomes.",
            "",
        ]
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", canonical)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace("Engineer - Example Co", "Principal Engineer - Example Co")

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "canonical.md" in patch_text
    notes_files = list(drafts_dir.rglob("notes.md"))
    assert notes_files
    assert "- apply_status: review_diff_only" in notes_files[0].read_text()


def test_import_docx_uses_variant_latest_run(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", "base-before\n")
    _write_run_manifest(tmp_path, "2026-01-02T00-00-00Z", "cover", "cover-before\n")

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "base-before" in patch_text


def test_import_docx_reports_hint_when_runs_are_missing(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code != 0
    assert "No runs available" in (result.stderr or "")
    assert "cvw reviewpack --variant" in (result.stderr or "")


def test_import_docx_ignores_invalid_run_dirs_when_variant_resolves_latest_run(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-02T00-00-00Z", "base", "base-before\n")
    invalid_dir = tmp_path / "var" / "runs" / "2026-01-01T00-00-00Z"
    invalid_dir.mkdir(parents=True, exist_ok=True)

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "base-before" in patch_text


def test_reviewpack_variant_ignores_project_scoped_runs(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "2026-01-02T00-00-00Z",
        variant_id="base",
        canonical="base-before\n",
        review_ready=True,
    )
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "projects" / "job" / "2026-01-03T00-00-00Z",
        variant_id="base",
        canonical="project-before\n",
        review_ready=True,
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    assert "run_id: 2026-01-02T00-00-00Z" in result.stdout


def test_reviewpack_variant_rejects_project_only_runs(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "projects" / "job" / "2026-01-03T00-00-00Z",
        variant_id="base",
        canonical="project-before\n",
        review_ready=True,
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code != 0
    assert "No non-project runs available for variant: base" in (result.stderr or "")
    assert "--project <project-id>" in (result.stderr or "")


def test_reviewpack_uses_explicit_run_and_isolates_project_review_dir(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    _write_run_manifest(tmp_path, "2026-01-04T00-00-00Z", "base", "base-before\n")
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "projects" / "job" / "2026-01-03T00-00-00Z",
        variant_id="base",
        canonical="project-before\n",
        review_ready=True,
        bullet_text="project bullet",
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "reviewpack",
                "--run",
                "projects/job/2026-01-03T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    out_dir = resolve_reviews_path(config_path) / "projects" / "job"
    assert out_dir.exists()
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout
    assert (out_dir / "cv.docx").read_bytes() == b"docx"
    assert "project bullet" in (out_dir / "review.md").read_text()


def test_reviewpack_force_replaces_existing_pack(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "2026-01-04T00-00-00Z",
        variant_id="base",
        canonical="base-before\n",
        review_ready=True,
    )
    review_dir = resolve_reviews_path(config_path) / "base"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "stale.txt").write_text("stale")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "reviewpack",
                "--variant",
                "base",
                "--force",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    assert not (review_dir / "stale.txt").exists()
    assert (review_dir / "cv.docx").exists()


def test_reviewpack_uses_project_selector_for_latest_project_run(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    _write_run_manifest_at(
        tmp_path / "var" / "runs" / "projects" / "job" / "2026-01-03T00-00-00Z",
        variant_id="base",
        canonical="project-before\n",
        review_ready=True,
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--project", "job", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    out_dir = resolve_reviews_path(config_path) / "projects" / "job"
    assert out_dir.exists()
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout


def test_reviewpack_project_run_mismatch_reports_selector_hint(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    _write_project_manifest(tmp_path, "other")
    _write_project_run_manifest(
        tmp_path,
        "other",
        "2026-01-03T00-00-00Z",
        "base",
        "other-before\n",
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "reviewpack",
                "--project",
                "job",
                "--run",
                "projects/other/2026-01-03T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code != 0
    assert "Run does not belong to project: job" in (result.stderr or "")
    assert "reviewpack --project job" in (result.stderr or "")
    assert "drop `--project`" in (result.stderr or "")


def test_import_docx_variant_ignores_project_scoped_runs(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-02T00-00-00Z", "base", "base-before\n")
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        "project-before\n",
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    assert "run_id: 2026-01-02T00-00-00Z" in result.stdout
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "base-before" in patch_text


def test_import_docx_variant_rejects_project_only_runs(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        "project-before\n",
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code != 0
    assert "No non-project runs available for variant: base" in (result.stderr or "")
    assert "--run <run-id>" in (result.stderr or "")


def test_import_docx_uses_project_selector(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        "project-before\n",
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--project",
                "job",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.diff"))
    assert patch_files
    assert "project-before" in patch_files[0].read_text()


def test_import_docx_project_selector_writes_project_ops_patch_for_summary_edits(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    _write_project_manifest(tmp_path, "job")
    canonical = "\n".join(
        [
            "## Projects",
            "",
            "### Example Project",
            "Example summary.",
            "",
        ]
    )
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        canonical,
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace("Example summary.", "Tailored project summary.")

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--project",
                "job",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"][0]["op"] == "replace-project-summary"
    assert patch_payload["patch"]["operations"][0]["project_id"] == "project-1"

    apply_result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(patch_files[0].parent),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert apply_result.exit_code == 0
    assert "Tailored project summary." in (sot_path / "projects.yaml").read_text()


def test_import_docx_project_selector_reconciles_existing_project_summary_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_minimal_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    project_dir = _write_project_manifest(tmp_path, "job")
    (project_dir / "proposals" / "patch.yaml").write_text(
        yaml.safe_dump(
            {
                "patch": {
                    "format": "project-ops",
                    "operations": [
                        {
                            "op": "replace-project-summary",
                            "project_id": "project-1",
                            "old_text": "Example summary.",
                            "new_text": "Overlay summary.",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )
    canonical = "\n".join(
        [
            "## Projects",
            "",
            "### Example Project",
            "Overlay summary.",
            "",
        ]
    )
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        canonical,
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return canonical.replace("Overlay summary.", "Reviewed summary.")

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--project",
                "job",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.yaml"))
    assert patch_files
    patch_payload = yaml.safe_load(patch_files[0].read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"][0]["op"] == "replace-project-summary"
    assert patch_payload["patch"]["operations"][0]["old_text"] == "Example summary."
    assert patch_payload["patch"]["operations"][0]["new_text"] == "Reviewed summary."

    apply_result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(patch_files[0].parent),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert apply_result.exit_code == 0
    assert "Reviewed summary." in (sot_path / "projects.yaml").read_text()


def test_import_docx_project_run_override_uses_pinned_run(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-03T00-00-00Z",
        "base",
        "project-before\n",
    )
    _write_project_run_manifest(
        tmp_path,
        "job",
        "2026-01-04T00-00-00Z",
        "base",
        "project-after\n",
    )

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--project",
                "job",
                "--run",
                "projects/job/2026-01-03T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout
    patch_files = list(resolve_drafts_path(config_path).rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "project-before" in patch_text
    assert "project-after" not in patch_text


def test_import_docx_requires_run_variant_or_project(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 2
    assert "Provide one of --run, --variant, or --project" in (result.stderr or "")
