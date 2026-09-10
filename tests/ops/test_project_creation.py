"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_creation.py

Tests project creation preflight, directory ownership, and failure recovery.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import errno
import json
import os
from pathlib import Path

import pytest
import yaml

from cvworkbench.ops.projects import (
    ProjectError,
    create_project_from_file,
    create_project_from_url,
    creation,
)
from cvworkbench.ops.scaffold import init_project


def _workspace(root: Path) -> tuple[Path, Path, Path]:
    init_project(root, sample_default=True)
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    return root / "config/workbench.yaml", root / "sot.sample", job


@pytest.mark.parametrize(
    "invalid_input",
    [
        "job_directory",
        "job_utf8",
        "source_file",
        "missing_variant",
        "invalid_variant",
        "invalid_project_id",
        "invalid_ttl",
        "external_projects",
        "invalid_registry",
    ],
)
def test_file_creation_preflights_before_directory_writes(
    tmp_path: Path, monkeypatch, invalid_input: str
) -> None:
    config, source, job = _workspace(tmp_path)
    variant = config.parent / "variants/base.yaml"
    slug = "job"
    if invalid_input == "job_directory":
        job = tmp_path
    elif invalid_input == "job_utf8":
        job.write_bytes(b"\xff")
    elif invalid_input == "source_file":
        source = job
    elif invalid_input == "missing_variant":
        variant.unlink()
    elif invalid_input == "invalid_variant":
        payload = yaml.safe_load(variant.read_text())
        payload["variant"]["output_name"] = "../outside"
        variant.write_text(yaml.safe_dump(payload))
    elif invalid_input == "invalid_project_id":
        slug = "\u00e9quipe"
    elif invalid_input in {"invalid_ttl", "external_projects"}:
        payload = yaml.safe_load(config.read_text())
        if invalid_input == "invalid_ttl":
            payload["variant_lifecycle"]["ttl_days"] = True
        else:
            payload["paths"]["projects"] = "../outside-var"
        config.write_text(yaml.safe_dump(payload))
    else:
        registry = tmp_path / "var/variants/registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("invalid registry\n")

    mkdir_calls = []
    original_mkdir = Path.mkdir

    def record_mkdir(path, *args, **kwargs):
        mkdir_calls.append(path)
        return original_mkdir(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", record_mkdir)
        with pytest.raises((ProjectError, OSError, ValueError)):
            create_project_from_file(
                job_path=job,
                slug=slug,
                base_variant_id="base",
                config_path=config,
                sot_path=source,
                store_raw=False,
            )

    assert mkdir_calls == []


def test_url_creation_preflights_before_fetch(tmp_path: Path, monkeypatch) -> None:
    config, source, _ = _workspace(tmp_path)
    (config.parent / "variants/base.yaml").unlink()
    fetched = []

    def refuse_fetch(url, user_agent):
        fetched.append(url)
        raise OSError("fixture forbids external requests")

    with monkeypatch.context() as patch:
        patch.setattr(creation, "fetch_and_extract", refuse_fetch)
        with pytest.raises((ProjectError, OSError, ValueError)):
            create_project_from_url(
                url="https://example.test/jobs/scientist",
                slug="job",
                base_variant_id="base",
                config_path=config,
                sot_path=source,
                store_raw=False,
            )

    assert fetched == []


@pytest.mark.parametrize("slug", ["", " ", False, 0, []])
def test_creation_rejects_explicit_invalid_slug(tmp_path: Path, slug) -> None:
    config, source, job = _workspace(tmp_path)
    with pytest.raises(ProjectError, match="Project (id|slug)"):
        create_project_from_file(
            job_path=job,
            slug=slug,
            base_variant_id="base",
            config_path=config,
            sot_path=source,
            store_raw=False,
        )
    assert list((tmp_path / "var/projects").iterdir()) == []


def test_creation_does_not_echo_malformed_variant_contents(tmp_path: Path) -> None:
    config, source, job = _workspace(tmp_path)
    variant = config.parent / "variants/base.yaml"
    variant.write_text("variant: [private-fixture-content\n")
    with pytest.raises(ProjectError) as caught:
        create_project_from_file(
            job_path=job,
            slug="job",
            base_variant_id="base",
            config_path=config,
            sot_path=source,
            store_raw=False,
        )
    assert "private-fixture-content" not in str(caught.value)
    assert str(variant) in str(caught.value)
    assert list((tmp_path / "var/projects").iterdir()) == []


def test_creation_uses_captured_job_and_variant_after_staging_starts(
    tmp_path: Path, monkeypatch
) -> None:
    config, source, job = _workspace(tmp_path)
    variant = config.parent / "variants/base.yaml"
    payload = yaml.safe_load(variant.read_text())
    payload["authoring_note"] = "Preserve extension metadata."
    variant.write_text(yaml.safe_dump(payload))
    original_mkdir = Path.mkdir
    replaced = False

    def replace_inputs_on_staging(path, *args, **kwargs):
        nonlocal replaced
        if path == tmp_path / "var/projects" and not replaced:
            replaced = True
            variant.write_text("invalid later variant\n")
            job.write_text("Different later job.\n")
        return original_mkdir(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", replace_inputs_on_staging)
        result = create_project_from_file(
            job_path=job,
            slug="job",
            base_variant_id="base",
            config_path=config,
            sot_path=source,
            store_raw=False,
        )

    assert replaced
    assert result.extracted_path.read_text() == "Research scientist with Python experience.\n"
    assert job.read_text() == "Different later job.\n"
    proposal = yaml.safe_load(result.variant_path.read_text())
    assert proposal["variant"]["id"] == "proposal-job"
    assert proposal["authoring_note"] == "Preserve extension metadata."


def test_creation_preserves_a_destination_that_appears_before_publish(
    tmp_path: Path, monkeypatch
) -> None:
    config, source, job = _workspace(tmp_path)
    destination = tmp_path / "var/projects/job"
    sentinel = destination / "owned-by-another-operation.txt"
    original_rename = Path.rename

    def occupy_destination(path, target):
        if Path(target) == destination:
            destination.mkdir()
            sentinel.write_text("Retain this project.\n")
        return original_rename(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", occupy_destination)
        with pytest.raises(OSError):
            create_project_from_file(
                job_path=job,
                slug="job",
                base_variant_id="base",
                config_path=config,
                sot_path=source,
                store_raw=False,
            )

    assert sentinel.read_text() == "Retain this project.\n"
    assert list(destination.iterdir()) == [sentinel]
    assert not list(destination.parent.glob(".job.tmp-*"))


def test_creation_preserves_a_replaced_destination_during_registration(
    tmp_path: Path, monkeypatch
) -> None:
    config, source, job = _workspace(tmp_path)
    destination = tmp_path / "var/projects/job"
    moved_project = tmp_path / "var/projects/retained-project"
    sentinel = destination / "owned-by-another-operation.txt"
    original_register = creation.register_variant

    def replace_before_registration(**kwargs):
        destination.rename(moved_project)
        destination.mkdir()
        sentinel.write_text("Retain this replacement.\n")
        return original_register(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(creation, "register_variant", replace_before_registration)
        with pytest.raises(ProjectError, match="Variant file not found") as caught:
            create_project_from_file(
                job_path=job,
                slug="job",
                base_variant_id="base",
                config_path=config,
                sot_path=source,
                store_raw=False,
            )

    assert "Project directory was replaced; left intact" in str(caught.value)
    assert sentinel.read_text() == "Retain this replacement.\n"
    assert list(destination.iterdir()) == [sentinel]
    assert (moved_project / "project.yaml").is_file()


def test_creation_reports_registration_and_cleanup_failures(tmp_path: Path, monkeypatch) -> None:
    config, source, job = _workspace(tmp_path)
    destination = tmp_path / "var/projects/job"
    original_register = creation.register_variant
    original_unlink = os.unlink

    def invalidate_registry_before_registration(**kwargs):
        registry = tmp_path / "var/variants/registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("invalid registry\n")
        return original_register(**kwargs)

    def refuse_variant_removal(path, *args, **kwargs):
        if Path(path).name == "variant.yaml":
            raise PermissionError(errno.EACCES, "fixture deletion denied", path)
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(creation, "register_variant", invalidate_registry_before_registration)
        patch.setattr(os, "unlink", refuse_variant_removal)
        with pytest.raises(ProjectError, match="cleanup failed") as caught:
            create_project_from_file(
                job_path=job,
                slug="job",
                base_variant_id="base",
                config_path=config,
                sot_path=source,
                store_raw=False,
            )

    assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    assert "fixture deletion denied" in str(caught.value)
    assert str(destination) in str(caught.value)
    assert (destination / "proposals/variant.yaml").is_file()
