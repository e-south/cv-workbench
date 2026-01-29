"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli_output.py

Renders Rich panels for CLI summaries.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_console = Console(force_terminal=True, soft_wrap=True, width=120)


def print_summary(title: str, rows: list[tuple[str, str | Path]]) -> None:
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
