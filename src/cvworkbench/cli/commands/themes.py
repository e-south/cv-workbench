"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/themes.py

Present theme discovery and render-preset information.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import (
    resolve_default_theme,
    resolve_themes_dir,
)
from cvworkbench.themes import (
    ThemeError,
    list_theme_presets,
    list_themes,
    resolve_theme,
)


def _print_theme_list_summary(theme_ids: list[str], default_theme: str) -> None:
    print_summary(
        "theme.list",
        [
            ("themes", ", ".join(theme_ids)),
            ("default", default_theme),
        ],
    )


def _print_theme_info_summary(
    theme_id: str,
    description: str | None,
    routes: list[str],
    presets: list[str],
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("id", theme_id),
        ("routes", ", ".join(routes)),
        ("presets", ", ".join(presets) if presets else "none"),
    ]
    if description:
        rows.append(("description", description))
    print_summary("theme.info", rows)


def theme_list(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        themes_dir = resolve_themes_dir(config)
        default_theme = resolve_default_theme(config)
        themes = list_themes(themes_dir)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    theme_ids = [theme.id for theme in themes]
    _print_theme_list_summary(theme_ids, default_theme)


def theme_info(
    theme: Annotated[
        str,
        typer.Argument(help="Theme id"),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        themes_dir = resolve_themes_dir(config)
        resolved = resolve_theme(themes_dir, theme)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    routes = list(resolved.routes.keys())
    presets = list_theme_presets(resolved)
    _print_theme_info_summary(resolved.id, resolved.description, routes, presets)
