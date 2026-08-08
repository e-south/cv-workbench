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
