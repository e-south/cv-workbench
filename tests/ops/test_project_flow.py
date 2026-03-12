"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_flow.py

Tests project creation flow.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from cvworkbench.ingestion.ingest import ExtractResult
from cvworkbench.ops.projects import (
    ProjectError,
    apply_project_patch,
    append_replace_experience_bullet_operation,
    append_replace_project_summary_operation,
    create_project_from_file,
    create_project_from_url,
    load_project,
    load_project_patch,
    prepare_project_sot,
)
from cvworkbench.ops.variant_lifecycle import VariantLifecycleError, register_variant


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    base_variant = {
        "variant": {
            "id": "base",
            "outputs": ["md"],
            "include_tags": [],
            "exclude_tags": [],
        }
    }
    (variants_dir / "base.yaml").write_text(yaml.safe_dump(base_variant, sort_keys=False))
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths: {}",
                "variant_lifecycle:",
                "  ttl_days: 7",
            ]
        )
        + "\n"
    )
    return config_path


def test_create_project_from_url(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)

    def _fake_extract(url: str, user_agent: str | None) -> ExtractResult:
        return ExtractResult(
            text="Sample job text",
            extractor="mock",
            extractor_version="1.0",
            raw_html="<html></html>",
        )

    monkeypatch.setattr("cvworkbench.ops.projects.fetch_and_extract", _fake_extract)

    result = create_project_from_url(
        url="https://example.com/jobs/1",
        slug="acme",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    project_dir = tmp_path / "var" / "projects" / "acme"
    assert result.project_dir == project_dir
    assert (project_dir / "project.yaml").exists()
    assert (project_dir / "job" / "extracted.txt").read_text() == "Sample job text\n"
    assert not (project_dir / "job" / "raw.html").exists()
    assert (project_dir / "job" / "signals.json").exists()
    assert (project_dir / "proposals" / "variant.yaml").exists()
    assert (project_dir / "proposals" / "patch.yaml").exists()


def test_create_project_from_file(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    project_dir = tmp_path / "var" / "projects" / "orbit"
    assert result.project_dir == project_dir
    assert (project_dir / "job" / "extracted.txt").read_text() == "Job description text\n"

    spec = load_project(project_dir)
    assert spec.project_id == "orbit"
    assert spec.base_variant_id == "base"
    assert spec.variant_path.exists()
    variant_payload = yaml.safe_load(spec.variant_path.read_text())
    assert variant_payload["variant"]["id"] == "proposal-orbit"

    patch_payload = yaml.safe_load(result.patch_path.read_text())
    assert patch_payload["patch"]["format"] == "project-ops"
    assert patch_payload["patch"]["operations"] == []

    diff = load_project_patch(project_dir)
    assert diff == ""

    apply_project_patch(project_dir=project_dir, sot_path=sot_path)


def test_create_project_from_file_rolls_back_on_variant_registration_failure(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    def _boom(**kwargs) -> None:
        raise VariantLifecycleError("registry unavailable")

    monkeypatch.setattr("cvworkbench.ops.projects.register_variant", _boom)

    with pytest.raises(ProjectError, match="registry unavailable"):
        create_project_from_file(
            job_path=job_path,
            slug="orbit",
            base_variant_id="base",
            config_path=config_path,
            sot_path=sot_path,
            store_raw=False,
        )

    project_dir = tmp_path / "var" / "projects" / "orbit"
    assert not project_dir.exists()
    assert not any(path.name.startswith(".orbit.tmp-") for path in project_dir.parent.iterdir())

    monkeypatch.setattr("cvworkbench.ops.projects.register_variant", register_variant)
    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    assert result.project_dir == project_dir


def test_load_project_patch_rejects_legacy_unified_diff_payload(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )
    result.patch_path.write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

    with pytest.raises(ProjectError, match="project-ops"):
        load_project_patch(project_dir=result.project_dir, sot_path=sot_path)


def test_project_ops_replace_experience_bullet_prepare_and_apply(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )
    result.patch_path.write_text(
        yaml.safe_dump(
            {
                "patch": {
                    "format": "project-ops",
                    "operations": [
                        {
                            "op": "replace-experience-bullet",
                            "role_id": "role-1",
                            "bullet_id": "bullet-1",
                            "old_text": "Built platform foundations.",
                            "new_text": "Built platform foundations for regulated delivery.",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )

    diff = load_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "experience.yaml" in diff
    assert "-        text: Built platform foundations." in diff
    assert "Built platform foundations for regulated delivery." in diff

    prepared = prepare_project_sot(
        project_dir=result.project_dir,
        sot_path=sot_path,
        target_dir=tmp_path / "var" / "runs" / "project-preview" / "sot",
    )
    assert prepared != sot_path
    assert "regulated delivery" in (prepared / "experience.yaml").read_text()
    assert "regulated delivery" not in (sot_path / "experience.yaml").read_text()

    apply_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "regulated delivery" in (sot_path / "experience.yaml").read_text()


def test_append_replace_experience_bullet_operation_snapshots_current_text(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    patch = append_replace_experience_bullet_operation(
        project_dir=result.project_dir,
        sot_path=sot_path,
        role_id="role-1",
        bullet_id="bullet-1",
        new_text="Built platform foundations for regulated delivery.",
    )

    assert len(patch.operations) == 1
    op = patch.operations[0]
    assert op["old_text"] == "Built platform foundations."
    assert op["new_text"] == "Built platform foundations for regulated delivery."
    diff = load_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "Built platform foundations for regulated delivery." in diff


def test_project_ops_replace_project_summary_prepare_and_apply(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )
    result.patch_path.write_text(
        yaml.safe_dump(
            {
                "patch": {
                    "format": "project-ops",
                    "operations": [
                        {
                            "op": "replace-project-summary",
                            "project_id": "project-1",
                            "old_text": "Example summary.",
                            "new_text": "Example summary tailored for regulated delivery.",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )

    diff = load_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "projects.yaml" in diff
    assert "Example summary tailored for regulated delivery." in diff

    prepared = prepare_project_sot(
        project_dir=result.project_dir,
        sot_path=sot_path,
        target_dir=tmp_path / "var" / "runs" / "project-preview" / "sot",
    )
    assert prepared != sot_path
    assert "regulated delivery" in (prepared / "projects.yaml").read_text()
    assert "regulated delivery" not in (sot_path / "projects.yaml").read_text()

    apply_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "regulated delivery" in (sot_path / "projects.yaml").read_text()


def test_append_replace_project_summary_operation_snapshots_current_text(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    patch = append_replace_project_summary_operation(
        project_dir=result.project_dir,
        sot_path=sot_path,
        project_id="project-1",
        new_text="Example summary tailored for regulated delivery.",
    )

    assert len(patch.operations) == 1
    op = patch.operations[0]
    assert op["old_text"] == "Example summary."
    assert op["new_text"] == "Example summary tailored for regulated delivery."
    diff = load_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    assert "Example summary tailored for regulated delivery." in diff


def test_append_project_operations_serializes_concurrent_writers(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    barrier = threading.Barrier(2)
    projects_module = __import__("cvworkbench.ops.projects", fromlist=["_load_project_patch_authoring_state"])
    original_loader = projects_module._load_project_patch_authoring_state

    def _delayed_loader(project_dir: Path):
        state = original_loader(project_dir)
        try:
            barrier.wait(timeout=0.2)
        except threading.BrokenBarrierError:
            pass
        return state

    monkeypatch.setattr(
        "cvworkbench.ops.projects._load_project_patch_authoring_state",
        _delayed_loader,
    )

    start_gate = threading.Barrier(3)
    errors: list[BaseException] = []

    def _append_experience() -> None:
        try:
            start_gate.wait(timeout=1.0)
            append_replace_experience_bullet_operation(
                project_dir=result.project_dir,
                sot_path=sot_path,
                role_id="role-1",
                bullet_id="bullet-1",
                new_text="Built platform foundations for regulated delivery.",
            )
        except BaseException as exc:  # pragma: no cover - exercised only on failure
            errors.append(exc)

    def _append_project() -> None:
        try:
            start_gate.wait(timeout=1.0)
            append_replace_project_summary_operation(
                project_dir=result.project_dir,
                sot_path=sot_path,
                project_id="project-1",
                new_text="Example summary tailored for regulated delivery.",
            )
        except BaseException as exc:  # pragma: no cover - exercised only on failure
            errors.append(exc)

    threads = [
        threading.Thread(target=_append_experience),
        threading.Thread(target=_append_project),
    ]
    for thread in threads:
        thread.start()
    start_gate.wait(timeout=1.0)
    for thread in threads:
        thread.join()

    assert not errors
    payload = yaml.safe_load(result.patch_path.read_text())
    operations = payload["patch"]["operations"]
    assert len(operations) == 2
    assert {operation["op"] for operation in operations} == {
        "replace-experience-bullet",
        "replace-project-summary",
    }


def test_project_ops_fail_fast_on_source_text_drift(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )
    result.patch_path.write_text(
        yaml.safe_dump(
            {
                "patch": {
                    "format": "project-ops",
                    "operations": [
                        {
                            "op": "replace-experience-bullet",
                            "role_id": "role-1",
                            "bullet_id": "bullet-1",
                            "old_text": "Stale source text.",
                            "new_text": "Built platform foundations for regulated delivery.",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )

    try:
        apply_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    except ProjectError as exc:
        assert "source text mismatch" in str(exc)
    else:
        raise AssertionError("Expected apply_project_patch to reject stale source text")


def test_project_ops_fail_fast_on_duplicate_experience_targets(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
                "      - id: bullet-1",
                "        text: Built platform foundations again.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )
    result.patch_path.write_text(
        yaml.safe_dump(
            {
                "patch": {
                    "format": "project-ops",
                    "operations": [
                        {
                            "op": "replace-experience-bullet",
                            "role_id": "role-1",
                            "bullet_id": "bullet-1",
                            "old_text": "Built platform foundations.",
                            "new_text": "Built platform foundations for regulated delivery.",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )

    try:
        load_project_patch(project_dir=result.project_dir, sot_path=sot_path)
    except ProjectError as exc:
        assert "duplicate experience bullet target" in str(exc)
    else:
        raise AssertionError("Expected duplicate project-op target detection")
