"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/presentation.py

Assembles the preview presentation from package-owned markup, styles, and script.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from importlib.resources import files
from textwrap import indent


def preview_page_html() -> str:
    """Inline static assets into one response, with no additional browser fetches."""
    assets = files("cvworkbench.dev").joinpath("assets", "preview")
    html = assets.joinpath("index.html").read_text(encoding="utf-8")
    for marker, filename in (
        ("{{CVW_PREVIEW_STYLE}}", "layout.css"),
        ("{{CVW_PREVIEW_SCRIPT}}", "controller.js"),
    ):
        if html.count(marker) != 1:
            raise ValueError(f"Preview template must contain exactly one {marker} marker")
        content = assets.joinpath(filename).read_text(encoding="utf-8")
        html = html.replace(marker, indent(content, "      "))
    return html
