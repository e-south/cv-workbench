"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/scaffold.py

Creates local scaffold directories and files for a new workspace.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class ScaffoldError(RuntimeError):
    pass


@dataclass(frozen=True)
class InitResult:
    root: Path
    sot_path: Path
    config_path: Path
    variant_path: Path
    registry_path: Path
    statuses: dict[str, str]


def init_project(root: Path) -> InitResult:
    template_root = resolve_template_root()
    statuses: dict[str, str] = {}

    sot_target = root / "local" / "sot"
    _ensure_dir_from_template(template_root / "sot.sample", sot_target, statuses, "sot")

    config_target = root / "config"
    config_target.mkdir(parents=True, exist_ok=True)

    workbench_target = config_target / "workbench.yaml"
    _copy_file_from_template(
        template_root / "config" / "workbench.yaml",
        workbench_target,
        statuses,
        "workbench_config",
    )

    variants_target = config_target / "variants"
    variants_target.mkdir(parents=True, exist_ok=True)
    base_variant_target = variants_target / "base.yaml"
    _copy_file_from_template(
        template_root / "config" / "variants" / "base.yaml",
        base_variant_target,
        statuses,
        "base_variant",
    )
    publish_target = config_target / "publish.yaml"
    _copy_file_from_template(
        template_root / "config" / "publish.yaml",
        publish_target,
        statuses,
        "publish_config",
    )
    site_sync_target = config_target / "site-sync.yaml"
    _copy_file_from_template(
        template_root / "config" / "site-sync.yaml",
        site_sync_target,
        statuses,
        "site_sync_config",
    )

    build_target = root / "build"
    build_target.mkdir(parents=True, exist_ok=True)
    themes_target = build_target / "themes"
    _ensure_dir_from_template(
        template_root / "build" / "themes",
        themes_target,
        statuses,
        "themes",
    )

    var_root = root / "var"
    var_targets = {
        "dist": var_root / "dist",
        "runs": var_root / "runs",
        "drafts": var_root / "drafts",
        "variants": var_root / "variants",
        "reviews": var_root / "reviews",
    }
    for label, target in var_targets.items():
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            statuses[label] = "created"
        else:
            statuses[label] = "exists"

    registry_target = root / "var" / "registry" / "contexts"
    if not registry_target.exists():
        registry_target.mkdir(parents=True, exist_ok=True)
        statuses["registry"] = "created"
    else:
        statuses["registry"] = "exists"

    projects_target = root / "var" / "projects"
    if not projects_target.exists():
        projects_target.mkdir(parents=True, exist_ok=True)
        statuses["projects"] = "created"
    else:
        statuses["projects"] = "exists"

    return InitResult(
        root=root,
        sot_path=sot_target,
        config_path=workbench_target,
        variant_path=base_variant_target,
        registry_path=registry_target,
        statuses=statuses,
    )


def _resolve_template_root() -> Path:
    env_value = os.environ.get("CVW_TEMPLATE_DIR")
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[3]


def resolve_template_root() -> Path:
    return _resolve_template_root()


def _ensure_dir_from_template(
    template_dir: Path,
    target_dir: Path,
    statuses: dict[str, str],
    label: str,
) -> None:
    if target_dir.exists():
        statuses[label] = "exists"
        return
    if not template_dir.exists():
        raise ScaffoldError(f"Template directory not found: {template_dir}")
    shutil.copytree(template_dir, target_dir)
    statuses[label] = "created"


def _copy_file_from_template(
    template_path: Path,
    target_path: Path,
    statuses: dict[str, str],
    label: str,
) -> None:
    if target_path.exists():
        statuses[label] = "exists"
        return
    if not template_path.exists():
        raise ScaffoldError(f"Template file not found: {template_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_path, target_path)
    statuses[label] = "created"
