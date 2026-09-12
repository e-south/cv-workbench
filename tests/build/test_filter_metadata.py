"""Exclusion lists must remain effective across Pandoc metadata representations."""

import subprocess
from pathlib import Path


def test_each_excluded_tag_is_honored_by_the_native_filter():
    content = """---
exclude_tags: [restricted, unreviewed]
---
::: {.section .tag-restricted}
Restricted canary
:::

::: {.section .tag-unreviewed}
Unreviewed canary
:::

::: {.section .tag-public}
Approved text
:::
"""
    selector = Path(__file__).resolve().parents[2] / "build/filters/select.lua"
    result = subprocess.run(
        ["pandoc", "--lua-filter", str(selector), "-t", "plain"],
        input=content,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "Approved text"
