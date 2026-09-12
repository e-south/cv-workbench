"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_variant_lifecycle.py

Tests variant lifecycle registration and cleanup behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from cvworkbench.ops.variant_lifecycle import (
    VariantLifecycleError,
    discard_variant,
    gc_variants,
    keep_variant,
    load_variant_registry,
    register_variant,
)


def _expired_entry(root: Path, config_path: Path, name: str) -> Path:
    variant = root / "var" / "drafts" / name / "variant.yaml"
    _write_variant(variant, name)
    register_variant(
        variant_path=variant,
        cleanup_path=variant.parent,
        source="draft",
        config_path=config_path,
        label=None,
    )
    registry_path = root / "var" / "variants" / "registry.json"
    raw = json.loads(registry_path.read_text())
    raw["entries"][-1]["expires_at"] = "2020-01-01T00:00:00+00:00"
    registry_path.write_text(json.dumps(raw))
    return variant


def test_gc_variants_plans_missing_record_reconciliation(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    missing = _expired_entry(tmp_path, config_path, "missing")
    present = _expired_entry(tmp_path, config_path, "present")
    missing.unlink()
    missing.parent.rmdir()
    registry = tmp_path / "var" / "variants" / "registry.json"
    before = registry.read_bytes()

    preview = gc_variants(config_path=config_path, confirm=False)

    assert preview.status == "dry_run"
    assert preview.reconciled == 1
    assert {item.variant_id: item.action for item in preview.candidates} == {
        "missing": "reconcile",
        "present": "remove",
    }
    assert registry.read_bytes() == before
    assert present.is_file()

    result = gc_variants(config_path=config_path, confirm=True)
    assert result.expired == 2
    assert result.reconciled == 1
    assert not present.parent.exists()
    assert {entry.status for entry in load_variant_registry(config_path).entries} == {"expired"}
    assert gc_variants(config_path=config_path, confirm=True).status == "empty"


@pytest.mark.parametrize("confirm", [False, True])
@pytest.mark.parametrize("unsafe_path", ["var", "outside", "outside/missing"])
def test_gc_variants_preflights_all_paths_before_changes(
    tmp_path: Path, confirm: bool, unsafe_path: str
) -> None:
    config_path = _write_config(tmp_path)
    first = _expired_entry(tmp_path, config_path, "first")
    _expired_entry(tmp_path, config_path, "unsafe")
    (tmp_path / "outside").mkdir()
    registry = tmp_path / "var" / "variants" / "registry.json"
    raw = json.loads(registry.read_text())
    raw["entries"][-1]["cleanup_path"] = unsafe_path
    registry.write_text(json.dumps(raw))
    before = registry.read_bytes()

    with pytest.raises(VariantLifecycleError, match="Cleanup path"):
        gc_variants(config_path=config_path, confirm=confirm)

    assert first.is_file()
    assert registry.read_bytes() == before


def test_gc_variants_kept_sources_are_pruned_once(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    variant = _expired_entry(tmp_path, config_path, "demo")
    kept = keep_variant(
        variant_path=variant, config_path=config_path, variant_id="kept", label=None
    )

    first = gc_variants(config_path=config_path, confirm=True)
    second = gc_variants(config_path=config_path, confirm=True)

    assert first.kept_pruned == 1
    assert second.status == "empty"
    assert second.kept_pruned == 0
    assert kept.variant_path.is_file()


def test_gc_variants_rejects_shared_container_cleanup(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    variant = _expired_entry(tmp_path, config_path, "demo")
    sibling = tmp_path / "var" / "drafts" / "retained" / "notes.md"
    sibling.parent.mkdir()
    sibling.write_text("Retained work")
    registry = tmp_path / "var" / "variants" / "registry.json"
    raw = json.loads(registry.read_text())
    raw["entries"][0]["cleanup_path"] = "var/drafts"
    registry.write_text(json.dumps(raw))

    with pytest.raises(VariantLifecycleError, match="Cleanup path must own"):
        gc_variants(config_path=config_path, confirm=True)

    assert sibling.is_file()
    assert variant.is_file()


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "variant_lifecycle:",
                "  ttl_days: 7",
            ]
        )
        + "\n"
    )
    return config_path


def _write_variant(path: Path, variant_id: str) -> None:
    payload = {
        "variant": {
            "id": variant_id,
            "outputs": ["md"],
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def test_register_variant_creates_registry_entry(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    variant_path = tmp_path / "var" / "drafts" / "demo" / "variant.yaml"
    cleanup_path = variant_path.parent
    _write_variant(variant_path, "demo")

    entry = register_variant(
        variant_path=variant_path,
        cleanup_path=cleanup_path,
        source="draft",
        config_path=config_path,
        label="demo",
    )

    assert entry.variant_id == "demo"
    assert entry.status == "ephemeral"
    registry = load_variant_registry(config_path)
    assert registry.entries


def test_keep_variant_promotes_and_updates_registry(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / "config" / "variants").mkdir(parents=True, exist_ok=True)
    variant_path = tmp_path / "var" / "drafts" / "demo" / "variant.yaml"
    cleanup_path = variant_path.parent
    _write_variant(variant_path, "demo")

    register_variant(
        variant_path=variant_path,
        cleanup_path=cleanup_path,
        source="draft",
        config_path=config_path,
        label=None,
    )

    result = keep_variant(
        variant_path=variant_path,
        config_path=config_path,
        variant_id="kept",
        label="checkpoint-1",
    )

    kept_variant = tmp_path / "config" / "variants" / "kept.yaml"
    assert kept_variant.exists()
    kept_data = yaml.safe_load(kept_variant.read_text())
    assert kept_data["variant"]["id"] == "kept"
    assert result.status == "kept"


def test_discard_variant_removes_cleanup_path(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    variant_path = tmp_path / "var" / "drafts" / "demo" / "variant.yaml"
    cleanup_path = variant_path.parent
    _write_variant(variant_path, "demo")

    register_variant(
        variant_path=variant_path,
        cleanup_path=cleanup_path,
        source="draft",
        config_path=config_path,
        label=None,
    )

    result = discard_variant(
        variant_path=variant_path,
        config_path=config_path,
        confirm=True,
    )

    assert result.status == "discarded"
    assert not cleanup_path.exists()


def test_gc_variants_expires_ephemeral_entries(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    variant_path = tmp_path / "var" / "drafts" / "demo" / "variant.yaml"
    cleanup_path = variant_path.parent
    _write_variant(variant_path, "demo")

    register_variant(
        variant_path=variant_path,
        cleanup_path=cleanup_path,
        source="draft",
        config_path=config_path,
        label=None,
    )

    registry_path = tmp_path / "var" / "variants" / "registry.json"
    raw = json.loads(registry_path.read_text())
    raw["entries"][0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    registry_path.write_text(json.dumps(raw, indent=2))

    summary = gc_variants(config_path=config_path, confirm=True)

    assert summary.expired == 1
    assert not cleanup_path.exists()


def test_register_variant_serializes_concurrent_writers(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    lifecycle_module = importlib.import_module("cvworkbench.ops.variant_lifecycle")
    original_load_registry_raw = lifecycle_module._load_registry_raw

    def _slow_load_registry_raw(config: Path) -> dict[str, object]:
        raw = original_load_registry_raw(config)
        time.sleep(0.05)
        return raw

    monkeypatch.setattr(lifecycle_module, "_load_registry_raw", _slow_load_registry_raw)

    variant_paths: list[Path] = []
    for idx in range(4):
        variant_path = tmp_path / "var" / "drafts" / f"demo-{idx}" / "variant.yaml"
        _write_variant(variant_path, f"demo-{idx}")
        variant_paths.append(variant_path)

    def _register(variant_path: Path):
        return register_variant(
            variant_path=variant_path,
            cleanup_path=variant_path.parent,
            source="draft",
            config_path=config_path,
            label=variant_path.parent.name,
        )

    with ThreadPoolExecutor(max_workers=len(variant_paths)) as executor:
        results = list(executor.map(_register, variant_paths))

    assert {result.variant_id for result in results} == {f"demo-{idx}" for idx in range(4)}
    registry = load_variant_registry(config_path)
    assert {entry.variant_id for entry in registry.entries} == {f"demo-{idx}" for idx in range(4)}
