"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli_output.py

Renders Rich panels for CLI summaries.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class OutputMode(str, Enum):
    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"


_console = Console(force_terminal=True, soft_wrap=True, width=120)
_output_mode = OutputMode.RICH


def set_output_mode(mode: OutputMode) -> None:
    global _output_mode
    _output_mode = mode


def get_output_mode() -> OutputMode:
    return _output_mode


def summary_payload(title: str, rows: list[tuple[str, str | Path]]) -> dict[str, Any]:
    data = {key: str(value) for key, value in rows}
    return {"command": title, "data": data}


def print_summary(title: str, rows: list[tuple[str, str | Path]]) -> None:
    payload = summary_payload(title, rows)
    if _output_mode == OutputMode.JSON:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if _output_mode == OutputMode.PLAIN:
        for key, value in rows:
            print(f"{key}: {value}")
        return

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="cyan", no_wrap=True)
    table.add_column(style="white", overflow="fold")

    for key, value in rows:
        table.add_row(f"{key}:", str(value))

    panel = Panel(
        table,
        title=title,
        border_style="cyan",
        box=box.ROUNDED,
    )
    _console.print(panel)
