"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_manifest.py

Tests build manifest generation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from cvworkbench.build.pipeline import build_documents


def _write_build_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )
    return config_path


def test_manifest_written() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text())
    assert data["variant"]["id"] == "base"
    assert "sot_hashes" in data
    assert data["resume"]["path"] == "resume.json"
    assert "hash" in data["resume"]


def test_manifest_hashes_optional_files() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())
    assert "publications.yaml" in data["sot_hashes"]
    assert "honors.yaml" in data["sot_hashes"]


def test_manifest_hashes_snippet_files() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())

    assert "snippet_hashes" in data
    assert "snippets/summary.md" in data["snippet_hashes"]


def test_build_writes_render_outputs_to_run_dir() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    run_output = result.run_dir / "cv.md"
    dist_output = result.dist_dir / "cv.md"

    assert run_output.exists()
    assert run_output.read_text() == dist_output.read_text()


def test_dist_manifest_is_deterministic_across_repeated_builds(tmp_path: Path) -> None:
    config_path = _write_build_config(tmp_path)
    dist_manifest_path = tmp_path / "var" / "dist" / "base" / "manifest.json"

    build_documents(
        sot_path=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        formats=["md"],
        run_dir=tmp_path / "var" / "runs" / "first",
    )
    first_manifest = dist_manifest_path.read_text()

    build_documents(
        sot_path=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        formats=["md"],
        run_dir=tmp_path / "var" / "runs" / "second",
    )
    second_manifest = dist_manifest_path.read_text()
    run_manifest = json.loads((tmp_path / "var" / "runs" / "second" / "manifest.json").read_text())

    assert first_manifest == second_manifest
    assert "created_at" not in json.loads(second_manifest)
    assert isinstance(run_manifest["created_at"], str)


def test_run_manifest_matches_dist_manifest_except_created_at(tmp_path: Path) -> None:
    config_path = _write_build_config(tmp_path)

    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        formats=["md"],
        run_dir=tmp_path / "var" / "runs" / "single",
    )

    dist_manifest = json.loads((result.dist_dir / "manifest.json").read_text())
    run_manifest = json.loads((result.run_dir / "manifest.json").read_text())

    created_at = run_manifest.pop("created_at", None)

    assert isinstance(created_at, str)
    assert run_manifest == dist_manifest
