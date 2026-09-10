"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_selection.py

Tests selection metadata and explain command.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.selection import build_selection
from cvworkbench.cli import app
from cvworkbench.inputs.sot import load_sot
from cvworkbench.variants import load_variant

pytestmark = pytest.mark.usefixtures("sample_workspace")


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


def test_build_writes_selection() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--plain", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )
    assert result.exit_code == 0
    selection_path = Path("var/dist/base/selection.json")
    payload = json.loads(selection_path.read_text())
    assert isinstance(payload.get("items"), list)


def test_explain_outputs_selection_item() -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        ["build", "--plain", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )
    result = runner.invoke(
        app,
        ["explain", "--variant", "base", "--id", "acme-01", "--plain"],
    )
    assert result.exit_code == 0
    assert "acme-01" in result.stdout


def test_dist_selection_is_deterministic_across_repeated_builds(tmp_path: Path) -> None:
    config_path = _write_build_config(tmp_path)
    runner = CliRunner()

    first = runner.invoke(
        app,
        [
            "build",
            "--plain",
            "--variant",
            "base",
            "--format",
            "md",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
        ],
    )
    assert first.exit_code == 0
    selection_path = tmp_path / "var" / "dist" / "base" / "selection.json"
    first_selection = selection_path.read_text()

    second = runner.invoke(
        app,
        [
            "build",
            "--plain",
            "--variant",
            "base",
            "--format",
            "md",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
        ],
    )
    assert second.exit_code == 0
    second_selection = selection_path.read_text()

    assert first_selection == second_selection
    assert "created_at" not in json.loads(second_selection)


@pytest.mark.parametrize(
    ("include", "exclude", "opening_reasons", "impact_reasons"),
    [
        ([], [], [], []),
        (["general"], [], [], ["missing_include"]),
        ([], ["leadership"], ["exclude_tag:leadership"], []),
        (["general"], ["general"], ["exclude_tag:general"], ["missing_include"]),
    ],
)
def test_cover_letter_selection_explains_rendered_sections(
    include: list[str],
    exclude: list[str],
    opening_reasons: list[str],
    impact_reasons: list[str],
) -> None:
    variant_path = Path("config/variants/cover-letter.yaml")
    variant = yaml.safe_load(variant_path.read_text())
    variant["variant"].update(include_tags=include, exclude_tags=exclude)
    variant_path.write_text(yaml.safe_dump(variant))
    letters_path = Path("sot.sample/letters.yaml")
    letters = yaml.safe_load(letters_path.read_text())
    letters["letters"].insert(
        0,
        {
            "id": "other-letter",
            "title": "Other letter",
            "salutation": "Hello,",
            "closing": "Thanks,",
            "sections": [{"id": "opening", "text": "Unselected letter text.", "tags": ["general"]}],
        },
    )
    letters_path.write_text(yaml.safe_dump(letters))

    runner = CliRunner()
    built = runner.invoke(app, ["build", "--variant", "cover-letter", "--format", "md", "--json"])
    assert built.exit_code == 0, built.stdout
    output_dir = Path("var/dist/cover-letter")
    payload = json.loads((output_dir / "selection.json").read_text())
    assert payload["document_type"] == "cover-letter"
    assert payload["letter_id"] == "default-cover-letter"
    assert [item["id"] for item in payload["items"]] == ["opening", "impact"]
    markdown = " ".join((output_dir / "cover-letter.md").read_text().split())
    for item, reasons in zip(payload["items"], [opening_reasons, impact_reasons], strict=True):
        assert item["type"] == "section"
        assert item["section"] == "letters"
        assert item["letter_id"] == "default-cover-letter"
        assert item["reasons"] == reasons
        assert item["included"] is (not reasons)
        assert (item["text"] in markdown) is (not reasons)
    assert "Unselected letter text." not in markdown

    explained = runner.invoke(
        app,
        ["explain", "--variant", "cover-letter", "--id", "opening", "--type", "section", "--plain"],
    )
    assert explained.exit_code == 0, explained.stdout
    assert "letter_id: default-cover-letter" in explained.stdout
    assert "Systems with clear ownership" in explained.stdout


@pytest.mark.parametrize("letter_id", [None, "missing-letter"])
def test_letter_selection_and_rendering_reject_missing_authority(letter_id: str | None) -> None:
    variant = replace(load_variant(Path("config/variants/cover-letter.yaml")), letter_id=letter_id)
    sot = load_sot(Path("sot.sample"))
    message = "must define letter_id" if letter_id is None else "Letter not found: missing-letter"
    for operation in (build_selection, build_markdown):
        with pytest.raises(ValueError, match=message):
            operation(sot, variant)


def test_cover_letter_review_checklist_tracks_selected_sections() -> None:
    runner = CliRunner()
    built = runner.invoke(
        app, ["build", "--variant", "cover-letter-focused", "--format", "md,pdf,docx", "--json"]
    )
    assert built.exit_code == 0, built.stdout
    packed = runner.invoke(app, ["reviewpack", "--variant", "cover-letter-focused", "--json"])
    assert packed.exit_code == 0, packed.stdout
    checklist = Path("var/reviews/cover-letter-focused/review.md").read_text()
    assert checklist.count("- [ ]") == 1
    assert "opening (default-cover-letter)" in checklist
    assert "Systems with clear ownership" in checklist
    assert "Hands-on incident response" not in checklist
