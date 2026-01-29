"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_markdown.py

Tests canonical markdown materialization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.markdown import build_markdown
from cvworkbench.sot import load_sot
from cvworkbench.variants import load_variant


def test_markdown_includes_role_divs_and_tags() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "::: {#role-" in content
    assert ".tag-infra" in content
    assert "## Experience" in content


def test_markdown_formats_year_dates() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "2014 — 2018" in content


def test_markdown_includes_namespaced_tags() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert ".tag-domain" in content
    assert ".tag-domain-synthetic-biology" in content


def test_markdown_includes_author_role_classes() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "[Alex Example]{.author .role-self .role-co-first}" in content
