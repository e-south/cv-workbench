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

from cvworkbench.ops.projects import ProjectError, create_project_from_file, creation
from cvworkbench.ops.scaffold import init_project


def _workspace(root: Path) -> tuple[Path, Path, Path]:
    init_project(root, sample_default=True)
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    return root / "config/workbench.yaml", root / "sot.sample", job


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
