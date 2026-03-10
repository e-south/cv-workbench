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


def test_reviewpack_uses_latest_project_run_for_variant(tmp_path: Path) -> None:
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

    assert result.exit_code == 0
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout


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


def test_import_docx_uses_latest_project_run_for_variant(tmp_path: Path, monkeypatch) -> None:
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

    assert result.exit_code == 0
    assert "run_id: projects/job/2026-01-03T00-00-00Z" in result.stdout
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "project-before" in patch_text


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
