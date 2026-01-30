"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_variant_promote.py

Tests variant promotion behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../sot",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
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
    return workbench


def _write_draft_variant(root: Path, draft_id: str) -> Path:
    draft_dir = root / "drafts" / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "variant.yaml").write_text(
        "\n".join(
            [
                "variant:",
                f"  id: {draft_id}",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    return draft_dir


def test_variant_promote_copies_draft_variant(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    draft_dir = _write_draft_variant(tmp_path, "draft")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "variant",
            "promote",
            "--draft",
            str(draft_dir),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    promoted = tmp_path / "config" / "variants" / "draft.yaml"
    assert promoted.exists()
    assert "variant_path:" in result.stdout


def test_variant_promote_refuses_overwrite(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    draft_dir = _write_draft_variant(tmp_path, "draft")
    (tmp_path / "config" / "variants" / "draft.yaml").write_text(
        "variant:\n  id: draft\n  outputs: [md]\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "variant",
            "promote",
            "--draft",
            str(draft_dir),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "already exists" in result.stderr
