"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/helpers.py

Shared CLI helper functions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from cvworkbench.cli.output import OutputMode, set_output_mode
from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_runs_path,
    resolve_sot_path,
)
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.validation import validate_sot


def configure_output_mode(plain: bool, json_output: bool) -> None:
    if plain and json_output:
        typer.echo("ERROR: choose only one of --plain or --json", err=True)
        raise typer.Exit(code=2)
    if json_output:
        set_output_mode(OutputMode.JSON)
    elif plain:
        set_output_mode(OutputMode.PLAIN)
    else:
        set_output_mode(OutputMode.RICH)


def load_sot_payload(sot_path: Path | None, config: Path) -> dict[str, Any]:
    try:
        resolved = resolve_sot_path(sot_path, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    return load_sot(resolved)


def resolve_selection_path(
    selection: Path | None,
    config: Path,
    variant: str | None,
    run: str | None,
) -> Path:
    if selection is not None:
        return selection
    if run:
        candidate = Path(run)
        if candidate.exists():
            return candidate / "selection.json"
        return resolve_runs_path(config) / run / "selection.json"
    resolved_variant = variant or resolve_default_variant(config)
    return resolve_dist_path(config) / resolved_variant / "selection.json"
