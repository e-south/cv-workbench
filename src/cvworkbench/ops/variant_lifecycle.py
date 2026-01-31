"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/variant_lifecycle.py

Tracks ephemeral variants and enforces keep/discard decisions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import resolve_project_root, resolve_var_root, resolve_variant_ttl_days
from cvworkbench.ops.variant_promote import PromoteError, promote_variant


class VariantLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class VariantRegistryEntry:
    variant_id: str
    variant_path: Path
    cleanup_path: Path
    source: str
    status: str
    created_at: str
    expires_at: str
    label: str | None
    kept_path: Path | None
    kept_at: str | None
    discarded_at: str | None
    expired_at: str | None
    source_pruned_at: str | None


@dataclass(frozen=True)
class VariantRegistry:
    entries: list[VariantRegistryEntry]


@dataclass(frozen=True)
class VariantKeepResult:
    variant_id: str
    variant_path: Path
    status: str


@dataclass(frozen=True)
class VariantDiscardResult:
    variant_path: Path
    status: str


@dataclass(frozen=True)
class VariantGcSummary:
    expired: int
    kept_pruned: int
    status: str


_REGISTRY_VERSION = 1
_ALLOWED_SOURCES = {"draft", "project", "manual"}
_ALLOWED_STATUSES = {"ephemeral", "kept", "discarded", "expired"}


def load_variant_registry(config_path: Path) -> VariantRegistry:
    raw = _load_registry_raw(config_path)
    entries = [_parse_entry(entry, config_path) for entry in raw["entries"]]
    return VariantRegistry(entries=entries)


def register_variant(
    *,
    variant_path: Path,
    cleanup_path: Path,
    source: str,
    config_path: Path,
    label: str | None,
) -> VariantRegistryEntry:
    if source not in _ALLOWED_SOURCES:
        raise VariantLifecycleError(f"Variant source is not supported: {source}")
    variant_path = variant_path.resolve()
    cleanup_path = cleanup_path.resolve()
    if not variant_path.exists():
        raise VariantLifecycleError(f"Variant file not found: {variant_path}")
    if not cleanup_path.exists():
        raise VariantLifecycleError(f"Cleanup path not found: {cleanup_path}")
    _require_var_path(cleanup_path, config_path)

    variant_id = _load_variant_id(variant_path)
    ttl_days = resolve_variant_ttl_days(config_path)
    now = _now()
    expires_at = (now + timedelta(days=ttl_days)).isoformat()

    registry = _load_registry_raw(config_path)
    key = _path_for_registry(variant_path, config_path)
    cleanup_key = _path_for_registry(cleanup_path, config_path)
    existing = _find_entry(registry["entries"], key)
    if existing:
        if existing["status"] != "ephemeral":
            raise VariantLifecycleError(f"Variant is not eligible for registration: {variant_path}")
        existing["variant_id"] = variant_id
        existing["cleanup_path"] = cleanup_key
        existing["source"] = source
        existing["label"] = label
        existing["created_at"] = now.isoformat()
        existing["expires_at"] = expires_at
    else:
        registry["entries"].append(
            {
                "variant_id": variant_id,
                "variant_path": key,
                "cleanup_path": cleanup_key,
                "source": source,
                "status": "ephemeral",
                "created_at": now.isoformat(),
                "expires_at": expires_at,
                "label": label,
                "kept_path": None,
                "kept_at": None,
                "discarded_at": None,
                "expired_at": None,
                "source_pruned_at": None,
            }
        )
    _write_registry(config_path, registry)
    return _parse_entry(_find_entry(registry["entries"], key), config_path)


def keep_variant(
    *,
    variant_path: Path,
    config_path: Path,
    variant_id: str | None,
    label: str | None,
) -> VariantKeepResult:
    registry = _load_registry_raw(config_path)
    key = _path_for_registry(variant_path, config_path)
    entry = _find_entry(registry["entries"], key)
    if not entry:
        raise VariantLifecycleError(f"Variant is not registered: {variant_path}")
    if entry["status"] != "ephemeral":
        raise VariantLifecycleError(f"Variant is not eligible to keep: {variant_path}")
    if Path(variant_path).name != "variant.yaml":
        raise VariantLifecycleError("Variant keep requires a variant.yaml file")

    try:
        result = promote_variant(
            draft_dir=Path(variant_path).parent,
            config_path=config_path,
            variant_id=variant_id,
        )
    except PromoteError as exc:
        raise VariantLifecycleError(str(exc)) from exc

    entry["status"] = "kept"
    entry["kept_path"] = _path_for_registry(result.variant_path, config_path)
    entry["kept_at"] = _now().isoformat()
    if label is not None:
        entry["label"] = label
    _write_registry(config_path, registry)
    return VariantKeepResult(
        variant_id=result.variant_id,
        variant_path=result.variant_path,
        status="kept",
    )


def discard_variant(
    *,
    variant_path: Path,
    config_path: Path,
    confirm: bool,
) -> VariantDiscardResult:
    registry = _load_registry_raw(config_path)
    key = _path_for_registry(variant_path, config_path)
    entry = _find_entry(registry["entries"], key)
    if not entry:
        raise VariantLifecycleError(f"Variant is not registered: {variant_path}")
    if entry["status"] in {"discarded", "expired"}:
        raise VariantLifecycleError(f"Variant is already discarded: {variant_path}")

    cleanup_path = _path_from_registry(entry["cleanup_path"], config_path)
    if not cleanup_path.exists():
        raise VariantLifecycleError(f"Cleanup path not found: {cleanup_path}")
    if not confirm:
        return VariantDiscardResult(variant_path=cleanup_path, status="dry_run")
    _remove_path(cleanup_path, config_path)
    entry["status"] = "discarded"
    entry["discarded_at"] = _now().isoformat()
    _write_registry(config_path, registry)
    return VariantDiscardResult(variant_path=cleanup_path, status="discarded")


def gc_variants(*, config_path: Path, confirm: bool) -> VariantGcSummary:
    registry = _load_registry_raw(config_path)
    now = _now()
    expired = 0
    kept_pruned = 0
    candidates: list[tuple[dict[str, Any], Path]] = []
    for entry in registry["entries"]:
        if entry["status"] not in {"ephemeral", "kept"}:
            continue
        expires_at = _parse_time(entry.get("expires_at"))
        if expires_at is None or expires_at > now:
            continue
        cleanup_path = _path_from_registry(entry["cleanup_path"], config_path)
        if not cleanup_path.exists():
            raise VariantLifecycleError(f"Cleanup path not found: {cleanup_path}")
        candidates.append((entry, cleanup_path))
    for entry, cleanup_path in candidates:
        if entry["status"] == "kept":
            kept_pruned += 1
        else:
            expired += 1
        if confirm:
            _remove_path(cleanup_path, config_path)
            if entry["status"] == "kept":
                entry["source_pruned_at"] = now.isoformat()
            else:
                entry["status"] = "expired"
                entry["expired_at"] = now.isoformat()
    if confirm:
        _write_registry(config_path, registry)
    return VariantGcSummary(
        expired=expired,
        kept_pruned=kept_pruned,
        status="cleaned" if confirm else "dry_run",
    )


def list_variant_inbox(config_path: Path) -> list[VariantRegistryEntry]:
    registry = load_variant_registry(config_path)
    entries = [entry for entry in registry.entries if entry.status == "ephemeral"]
    return sorted(entries, key=lambda entry: entry.expires_at)


def _registry_path(config_path: Path) -> Path:
    return resolve_var_root(config_path) / "variants" / "registry.json"


def _load_registry_raw(config_path: Path) -> dict[str, Any]:
    path = _registry_path(config_path)
    if not path.exists():
        return {"version": _REGISTRY_VERSION, "entries": []}
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise VariantLifecycleError("Variant registry is invalid")
    version = raw.get("version")
    if version != _REGISTRY_VERSION:
        raise VariantLifecycleError("Variant registry version is invalid")
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise VariantLifecycleError("Variant registry is invalid")
    for entry in entries:
        _validate_entry(entry)
    return raw


def _write_registry(config_path: Path, payload: dict[str, Any]) -> None:
    path = _registry_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temp_path.replace(path)


def _validate_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise VariantLifecycleError("Variant registry entry is invalid")
    for key in ("variant_id", "variant_path", "cleanup_path", "source", "status", "created_at", "expires_at"):
        if key not in entry:
            raise VariantLifecycleError("Variant registry entry is invalid")
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise VariantLifecycleError("Variant registry entry is invalid")
    if entry["source"] not in _ALLOWED_SOURCES:
        raise VariantLifecycleError("Variant registry entry is invalid")
    if entry["status"] not in _ALLOWED_STATUSES:
        raise VariantLifecycleError("Variant registry entry is invalid")
    for key in ("label", "kept_path", "kept_at", "discarded_at", "expired_at", "source_pruned_at"):
        value = entry.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise VariantLifecycleError("Variant registry entry is invalid")
    if entry["status"] == "kept":
        if not entry.get("kept_path") or not entry.get("kept_at"):
            raise VariantLifecycleError("Variant registry entry is invalid")
    if entry["status"] == "discarded" and not entry.get("discarded_at"):
        raise VariantLifecycleError("Variant registry entry is invalid")


def _parse_entry(entry: dict[str, Any], config_path: Path) -> VariantRegistryEntry:
    return VariantRegistryEntry(
        variant_id=entry["variant_id"],
        variant_path=_path_from_registry(entry["variant_path"], config_path),
        cleanup_path=_path_from_registry(entry["cleanup_path"], config_path),
        source=entry["source"],
        status=entry["status"],
        created_at=entry["created_at"],
        expires_at=entry["expires_at"],
        label=entry.get("label"),
        kept_path=_path_from_registry(entry["kept_path"], config_path)
        if entry.get("kept_path")
        else None,
        kept_at=entry.get("kept_at"),
        discarded_at=entry.get("discarded_at"),
        expired_at=entry.get("expired_at"),
        source_pruned_at=entry.get("source_pruned_at"),
    )


def _find_entry(entries: list[dict[str, Any]], variant_key: str) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("variant_path") == variant_key:
            return entry
    return None


def _load_variant_id(path: Path) -> str:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise VariantLifecycleError("Variant file is invalid")
    variant_section = raw.get("variant")
    if not isinstance(variant_section, dict):
        raise VariantLifecycleError("Variant file is invalid")
    value = variant_section.get("id")
    if not isinstance(value, str) or not value.strip():
        raise VariantLifecycleError("Variant id is required")
    return value.strip()


def _remove_path(path: Path, config_path: Path) -> None:
    _require_var_path(path, config_path)
    if not path.exists():
        raise VariantLifecycleError(f"Cleanup path not found: {path}")
    if path.is_dir():
        shutil.rmtree(path)
        return
    if path.is_file() or path.is_symlink():
        path.unlink()
        return
    raise VariantLifecycleError(f"Cleanup path is not removable: {path}")


def _require_var_path(path: Path, config_path: Path) -> None:
    var_root = resolve_var_root(config_path).resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(var_root)
    except ValueError as exc:
        raise VariantLifecycleError(f"Cleanup path is outside var: {resolved}") from exc


def _path_for_registry(path: Path, config_path: Path) -> str:
    root = resolve_project_root(config_path)
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _path_from_registry(value: str, config_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    root = resolve_project_root(config_path)
    return (root / candidate).resolve()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)
