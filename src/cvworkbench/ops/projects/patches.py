"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/patches.py

Author, compile, and apply guarded project content edits.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from contextlib import contextmanager
from difflib import unified_diff
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from cvworkbench.ops.patches import PatchError, apply_patch_text
from cvworkbench.ops.projects.records import (
    _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
    _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
    _PROJECT_PATCH_FORMAT_OPS,
    ProjectError,
    ProjectPatch,
    _now_iso,
)
from cvworkbench.text import slugify

_PROJECT_PATCH_MUTEXES: dict[str, Lock] = {}


_PROJECT_PATCH_MUTEXES_GUARD = Lock()


def load_project_patch(project_dir: Path, *, sot_path: Path | None = None) -> str:
    patch = _load_project_patch_model(project_dir)
    return compile_project_patch(patch=patch, sot_path=sot_path)


def _load_project_patch_model(project_dir: Path) -> ProjectPatch:
    patch_path = project_dir / "proposals" / "patch.yaml"
    return load_project_patch_payload(patch_path)


def load_project_patch_payload(patch_path: Path) -> ProjectPatch:
    if not patch_path.exists():
        raise ProjectError(f"Project patch not found: {patch_path}")
    raw = yaml.safe_load(patch_path.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project patch file must be a mapping")
    patch_data = raw.get("patch")
    if not isinstance(patch_data, dict):
        raise ProjectError("Project patch file is invalid")
    fmt = patch_data.get("format")
    if fmt == _PROJECT_PATCH_FORMAT_OPS:
        operations = patch_data.get("operations")
        if not isinstance(operations, list):
            raise ProjectError("Project patch operations must be a list")
        if not all(isinstance(item, dict) for item in operations):
            raise ProjectError("Project patch operations must be mappings")
        return ProjectPatch(
            format=fmt,
            diff="",
            operations=tuple(dict(item) for item in operations),
        )
    raise ProjectError("Project patch format must be project-ops")


def compile_project_patch(*, patch: ProjectPatch, sot_path: Path | None = None) -> str:
    if len(patch.operations) == 0:
        return ""
    if sot_path is None:
        raise ProjectError("SoT path is required to compile project patch operations")
    return _compile_project_operations(operations=patch.operations, sot_path=sot_path)


def apply_project_patch(*, project_dir: Path, sot_path: Path) -> None:
    diff = load_project_patch(project_dir, sot_path=sot_path)
    try:
        apply_patch_text(patch_text=diff, cwd=sot_path)
    except PatchError as exc:
        raise ProjectError(str(exc)) from exc


def prepare_project_sot(*, project_dir: Path, sot_path: Path, target_dir: Path) -> Path:
    diff = load_project_patch(project_dir, sot_path=sot_path)
    if diff.strip() == "":
        return sot_path
    if target_dir.exists():
        import shutil

        shutil.rmtree(target_dir)
    import shutil

    shutil.copytree(sot_path, target_dir)
    try:
        apply_patch_text(patch_text=diff, cwd=target_dir)
    except PatchError as exc:
        raise ProjectError(str(exc)) from exc
    return target_dir


def append_replace_experience_bullet_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    role_id: str,
    bullet_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_role_id = _require_project_text(role_id, field_name="role_id", slug=True)
    resolved_bullet_id = _require_project_text(bullet_id, field_name="bullet_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = _read_experience_bullet_text(
        sot_path=sot_path,
        role_id=resolved_role_id,
        bullet_id=resolved_bullet_id,
    )
    resolved_old_text = (
        current_text if old_text is None else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_experience_bullet_operation(
            role_id=resolved_role_id,
            bullet_id=resolved_bullet_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def append_replace_project_summary_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    project_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_project_id = _require_project_text(project_id, field_name="project_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = _read_project_summary_text(
        sot_path=sot_path,
        project_id=resolved_project_id,
    )
    resolved_old_text = (
        current_text if old_text is None else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_project_summary_operation(
            project_id=resolved_project_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def _compile_project_operations(
    *,
    operations: tuple[dict[str, Any], ...],
    sot_path: Path,
) -> str:
    experience: tuple[str, dict[str, Any], list[Any]] | None = None
    projects: tuple[str, dict[str, Any], list[Any]] | None = None
    bullet_index: dict[tuple[str, str], dict[str, Any]] | None = None
    duplicate_bullets: set[tuple[str, str]] = set()
    seen_bullet_targets: set[tuple[str, str]] = set()
    project_index: dict[str, dict[str, Any]] | None = None
    duplicate_projects: set[str] = set()
    seen_project_targets: set[str] = set()

    for index, operation in enumerate(operations, start=1):
        op_name = _require_operation_text(operation, "op", index=index)
        if op_name == _PROJECT_OP_REPLACE_EXPERIENCE_BULLET:
            if experience is None:
                experience = _load_project_ops_document(
                    sot_path=sot_path,
                    filename="experience.yaml",
                    root_key="roles",
                )
                bullet_index, duplicate_bullets = _index_experience_bullets(experience[2])
            assert bullet_index is not None
            role_id = _require_operation_slug(operation, "role_id", index=index)
            bullet_id = _require_operation_slug(operation, "bullet_id", index=index)
            old_text = _require_operation_text(operation, "old_text", index=index)
            new_text = _require_operation_text(operation, "new_text", index=index)
            target = (role_id, bullet_id)
            if target in seen_bullet_targets:
                raise ProjectError(
                    "Duplicate project op target for experience bullet: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            seen_bullet_targets.add(target)
            if target in duplicate_bullets:
                raise ProjectError(
                    "Project op target resolves to a duplicate experience bullet target: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            bullet = bullet_index.get(target)
            if bullet is None:
                raise ProjectError(
                    "Project op target not found in experience.yaml: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            current_text = bullet.get("text")
            if not isinstance(current_text, str) or not current_text.strip():
                raise ProjectError(
                    "Experience bullet text is invalid for project op target: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            if current_text != old_text:
                raise ProjectError(
                    "Project op source text mismatch for experience bullet: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            bullet["text"] = new_text
            continue

        if op_name == _PROJECT_OP_REPLACE_PROJECT_SUMMARY:
            if projects is None:
                projects = _load_project_ops_document(
                    sot_path=sot_path,
                    filename="projects.yaml",
                    root_key="projects",
                )
                project_index, duplicate_projects = _index_projects(projects[2])
            assert project_index is not None
            project_id = _require_operation_slug(operation, "project_id", index=index)
            old_text = _require_operation_text(operation, "old_text", index=index)
            new_text = _require_operation_text(operation, "new_text", index=index)
            if project_id in seen_project_targets:
                raise ProjectError(
                    f"Duplicate project op target for project summary: project_id={project_id}"
                )
            seen_project_targets.add(project_id)
            if project_id in duplicate_projects:
                raise ProjectError(
                    "Project op target resolves to a duplicate project summary target: "
                    f"project_id={project_id}"
                )
            project_entry = project_index.get(project_id)
            if project_entry is None:
                raise ProjectError(
                    f"Project op target not found in projects.yaml: project_id={project_id}"
                )
            current_summary = project_entry.get("summary")
            if not isinstance(current_summary, str) or not current_summary.strip():
                raise ProjectError(
                    "Project summary text is invalid for project op target: "
                    f"project_id={project_id}"
                )
            if current_summary != old_text:
                raise ProjectError(
                    f"Project op source text mismatch for project summary: project_id={project_id}"
                )
            project_entry["summary"] = new_text
            continue

        raise ProjectError(f"Unsupported project operation: {op_name}")

    diffs: list[str] = []
    if experience is not None:
        diffs.append(
            _project_ops_diff(
                filename="experience.yaml",
                original_text=experience[0],
                updated_text=yaml.safe_dump(experience[1], sort_keys=False),
            )
        )
    if projects is not None:
        diffs.append(
            _project_ops_diff(
                filename="projects.yaml",
                original_text=projects[0],
                updated_text=yaml.safe_dump(projects[1], sort_keys=False),
            )
        )
    return "".join(diff for diff in diffs if diff)


def _index_experience_bullets(
    roles: list[Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[tuple[str, str]]]:
    bullets: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str]] = set()
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
        if not role_id:
            continue
        raw_bullets = role.get("bullets")
        if not isinstance(raw_bullets, list):
            continue
        for bullet in raw_bullets:
            if not isinstance(bullet, dict):
                continue
            bullet_id = slugify(bullet.get("id", ""))
            if not bullet_id:
                continue
            target = (role_id, bullet_id)
            if target in bullets:
                duplicates.add(target)
                continue
            bullets[target] = bullet
    return bullets, duplicates


def _experience_bullet_operation(
    *,
    role_id: str,
    bullet_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
        "role_id": role_id,
        "bullet_id": bullet_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _project_summary_operation(
    *,
    project_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
        "project_id": project_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _read_experience_bullet_text(
    *,
    sot_path: Path,
    role_id: str,
    bullet_id: str,
) -> str:
    _, _, roles = _load_project_ops_document(
        sot_path=sot_path,
        filename="experience.yaml",
        root_key="roles",
    )
    bullet_index, duplicate_targets = _index_experience_bullets(roles)
    target = (role_id, bullet_id)
    if target in duplicate_targets:
        raise ProjectError(
            "Project op target resolves to a duplicate experience bullet target: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    bullet = bullet_index.get(target)
    if bullet is None:
        raise ProjectError(
            "Project op target not found in experience.yaml: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    current_text = bullet.get("text")
    if not isinstance(current_text, str) or not current_text.strip():
        raise ProjectError(
            "Experience bullet text is invalid for project op target: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    return current_text.strip()


def _read_project_summary_text(
    *,
    sot_path: Path,
    project_id: str,
) -> str:
    _, _, items = _load_project_ops_document(
        sot_path=sot_path,
        filename="projects.yaml",
        root_key="projects",
    )
    project_index, duplicate_targets = _index_projects(items)
    if project_id in duplicate_targets:
        raise ProjectError(
            "Project op target resolves to a duplicate project summary target: "
            f"project_id={project_id}"
        )
    project_entry = project_index.get(project_id)
    if project_entry is None:
        raise ProjectError(f"Project op target not found in projects.yaml: project_id={project_id}")
    current_summary = project_entry.get("summary")
    if not isinstance(current_summary, str) or not current_summary.strip():
        raise ProjectError(
            f"Project summary text is invalid for project op target: project_id={project_id}"
        )
    return current_summary.strip()


def _load_project_ops_document(
    *,
    sot_path: Path,
    filename: str,
    root_key: str,
) -> tuple[str, dict[str, Any], list[Any]]:
    target_path = sot_path / filename
    if not target_path.exists():
        raise ProjectError(f"Project ops target file not found: {target_path}")
    original_text = target_path.read_text()
    raw = yaml.safe_load(original_text)
    if not isinstance(raw, dict):
        raise ProjectError(f"{filename} must be a mapping")
    items = raw.get(root_key)
    if not isinstance(items, list):
        raise ProjectError(f"{filename} must contain a {root_key} list")
    return original_text, raw, items


def _append_project_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    operation: dict[str, str],
) -> ProjectPatch:
    patch_path = project_dir / "proposals" / "patch.yaml"
    with _project_patch_authoring_lock(patch_path):
        patch_path, raw, patch_data, operations = _load_project_patch_authoring_state(project_dir)
        candidate_operations = tuple([*operations, operation])
        _compile_project_operations(operations=candidate_operations, sot_path=sot_path)

        patch_data["operations"] = list(candidate_operations)
        raw.setdefault("created_at", _now_iso())
        raw["updated_at"] = _now_iso()
        patch_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return ProjectPatch(
        format=_PROJECT_PATCH_FORMAT_OPS,
        diff="",
        operations=candidate_operations,
    )


@contextmanager
def _project_patch_authoring_lock(patch_path: Path):
    path_key = str(patch_path.resolve())
    with _PROJECT_PATCH_MUTEXES_GUARD:
        mutex = _PROJECT_PATCH_MUTEXES.setdefault(path_key, Lock())

    with mutex:
        lock_path = patch_path.with_name(f"{patch_path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            _lock_project_patch_handle(handle)
            try:
                yield
            finally:
                _unlock_project_patch_handle(handle)


def _lock_project_patch_handle(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_project_patch_handle(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_project_patch_authoring_state(
    project_dir: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    patch_path = project_dir / "proposals" / "patch.yaml"
    raw = yaml.safe_load(patch_path.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project patch file must be a mapping")
    patch_data = raw.get("patch")
    if not isinstance(patch_data, dict):
        raise ProjectError("Project patch file is invalid")
    if patch_data.get("format") != _PROJECT_PATCH_FORMAT_OPS:
        raise ProjectError(
            "Project patch authoring requires format=project-ops in proposals/patch.yaml"
        )
    operations = patch_data.get("operations")
    if not isinstance(operations, list):
        raise ProjectError("Project patch operations must be a list")
    if not all(isinstance(item, dict) for item in operations):
        raise ProjectError("Project patch operations must be mappings")
    return patch_path, raw, patch_data, [dict(item) for item in operations]


def _index_projects(items: list[Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    projects: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        project_id = slugify(item.get("id", ""))
        if not project_id:
            continue
        if project_id in projects:
            duplicates.add(project_id)
            continue
        projects[project_id] = item
    return projects, duplicates


def _project_ops_diff(*, filename: str, original_text: str, updated_text: str) -> str:
    diff = unified_diff(
        original_text.splitlines(),
        updated_text.splitlines(),
        fromfile=filename,
        tofile=filename,
        lineterm="",
    )
    return "\n".join(diff) + ("\n" if original_text or updated_text else "")


def _require_project_text(value: str, *, field_name: str, slug: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project op field '{field_name}' must be a non-empty string")
    normalized = value.strip()
    if not slug:
        return normalized
    resolved = slugify(normalized)
    if not resolved:
        raise ProjectError(f"Project op field '{field_name}' must resolve to a stable id")
    return resolved


def _require_operation_text(
    operation: dict[str, Any],
    key: str,
    *,
    index: int,
) -> str:
    value = operation.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project op #{index} field '{key}' must be a non-empty string")
    return value.strip()


def _require_operation_slug(
    operation: dict[str, Any],
    key: str,
    *,
    index: int,
) -> str:
    value = _require_operation_text(operation, key, index=index)
    normalized = slugify(value)
    if not normalized:
        raise ProjectError(f"Project op #{index} field '{key}' must resolve to a stable id")
    return normalized
