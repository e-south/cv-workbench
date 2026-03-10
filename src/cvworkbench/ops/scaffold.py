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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


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


def init_project(root: Path, *, sample_default: bool = False) -> InitResult:
    template_root = resolve_template_root()
    statuses: dict[str, str] = {}

    if sample_default:
        sot_target = root / "sot.sample"
    else:
        sot_target = root / "local" / "sot"
    _ensure_dir_from_template(template_root / "sot.sample", sot_target, statuses, "sot")
    statuses["sot_profile"] = "sample-default" if sample_default else "local-copy"

    config_target = root / "config"
    config_target.mkdir(parents=True, exist_ok=True)

    workbench_target = config_target / "workbench.yaml"
    _copy_file_from_template(
        template_root / "config" / "workbench.yaml",
        workbench_target,
        statuses,
        "workbench_config",
    )
    if sample_default:
        _set_workbench_sot_path(workbench_target, sot_target)

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

    _ensure_precommit_hooks(root, statuses)

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


def _ensure_precommit_hooks(root: Path, statuses: dict[str, str]) -> None:
    config_path = root / ".pre-commit-config.yaml"
    if not config_path.exists():
        statuses["pre_commit_hooks"] = "missing"
        return

    hooks_dir = _resolve_git_hooks_dir(root)
    if hooks_dir is None:
        statuses["pre_commit_hooks"] = "no_git"
        return

    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists():
        statuses["pre_commit_hooks"] = "exists"
        return

    returncode, output = _run_precommit_install(root)
    if returncode != 0:
        statuses["pre_commit_hooks"] = "error"
        if output:
            statuses["pre_commit_hooks_detail"] = output
        return

    if hook_path.exists():
        statuses["pre_commit_hooks"] = "installed"
        return

    statuses["pre_commit_hooks"] = "error"
    statuses["pre_commit_hooks_detail"] = "pre-commit install exited successfully but did not create .git/hooks/pre-commit"


def _resolve_git_hooks_dir(root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    if not value:
        return None

    hooks_path = Path(value)
    if hooks_path.is_absolute():
        return hooks_path
    return (root / hooks_path).resolve()


def _run_precommit_install(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pre_commit", "install"],
        check=False,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = (result.stdout or "").strip()
    return result.returncode, output


def _set_workbench_sot_path(config_path: Path, sot_target: Path) -> None:
    if not config_path.exists():
        raise ScaffoldError(f"Workbench config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ScaffoldError(f"Workbench config must be a YAML mapping: {config_path}")

    paths = raw.get("paths")
    if paths is None:
        paths = {}
    if not isinstance(paths, dict):
        raise ScaffoldError(f"Workbench config field paths must be a mapping: {config_path}")

    relative = Path(os.path.relpath(sot_target, start=config_path.parent)).as_posix()
    paths["sot"] = relative
    raw["paths"] = paths
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False))


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
