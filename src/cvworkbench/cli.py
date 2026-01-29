"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.config import resolve_sot_path
from cvworkbench.validation import validate_sot

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet", err=True)
    raise typer.Exit(code=2)


@app.command()
def validate(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
) -> None:
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


@app.command()
def build() -> None:
    _not_implemented("build")


@app.command()
def render() -> None:
    _not_implemented("render")


@app.command()
def tailor() -> None:
    _not_implemented("tailor")


@app.command()
def diff() -> None:
    _not_implemented("diff")


@app.command()
def sync() -> None:
    _not_implemented("sync")
