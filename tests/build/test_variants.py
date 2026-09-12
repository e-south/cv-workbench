"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_variants.py

Tests variant loading and tag normalization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvworkbench.variants import load_variant


@pytest.mark.parametrize("field", ["id", "output_name"])
@pytest.mark.parametrize(
    "value",
    [
        "../outside",
        "/absolute",
        "nested/name",
        "nested\\name",
        ".",
        "..",
        "bad\nname",
        True,
        123,
        "",
    ],
)
def test_variant_rejects_unsafe_artifact_names(tmp_path, field, value):
    import yaml

    path = tmp_path / "variant.yaml"
    data = {"id": "base", "output_name": "cv", "outputs": ["md"]}
    data[field] = value
    path.write_text(yaml.safe_dump({"variant": data}))
    with pytest.raises(ValueError, match=field):
        load_variant(path)


@pytest.mark.parametrize("field", ["id", "output_name"])
def test_direct_variant_construction_rejects_path_values(tmp_path, field):
    from dataclasses import replace

    path = tmp_path / "variant.yaml"
    path.write_text("variant:\n  id: base\n  outputs: [md]\n")
    variant = load_variant(path)
    with pytest.raises(ValueError, match=field):
        replace(variant, **{field: "../outside"})


def test_variant_retains_human_readable_output_stems(tmp_path):
    path = tmp_path / "variant.yaml"
    path.write_text(
        "variant:\n  id: research.cv-v2\n  output_name: Example Person CV\n  outputs: [md]\n"
    )
    variant = load_variant(path)
    assert variant.id == "research.cv-v2"
    assert variant.output_name == "Example Person CV"


def test_variant_normalizes_tags(tmp_path: Path) -> None:
    variant_path = tmp_path / "variant.yaml"
    variant_path.write_text(
        "\n".join(
            [
                "variant:",
                "  id: tagged",
                "  include_tags:",
                "    - Domain:Synthetic Biology",
                "  exclude_tags:",
                "    - internal-only",
                "  outputs:",
                "    - md",
            ]
        )
        + "\n"
    )

    variant = load_variant(variant_path)

    assert variant.include_tags == ["domain-synthetic-biology"]
    assert variant.exclude_tags == ["internal-only"]


def test_variant_rejects_unknown_contact_fields(tmp_path: Path) -> None:
    variant_path = tmp_path / "variant.yaml"
    variant_path.write_text(
        "\n".join(
            [
                "variant:",
                "  id: public",
                "  contact_fields: [email, social_security_number]",
                "  outputs: [pdf]",
            ]
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="Unknown contact fields"):
        load_variant(variant_path)
