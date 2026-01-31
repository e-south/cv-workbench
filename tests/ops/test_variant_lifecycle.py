"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_variant_lifecycle.py

Tests variant lifecycle registration and cleanup behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from cvworkbench.ops.variant_lifecycle import (
    discard_variant,
    gc_variants,
    keep_variant,
    load_variant_registry,
    register_variant,
)


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
    raw["entries"][0]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    registry_path.write_text(json.dumps(raw, indent=2))

    summary = gc_variants(config_path=config_path, confirm=True)

    assert summary.expired == 1
    assert not cleanup_path.exists()
