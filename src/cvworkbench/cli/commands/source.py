"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/source.py

Adapt source-version and tag-inspection commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.helpers import configure_output_mode, load_sot_payload
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_sot_path,
)
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_versioned_root,
)
from cvworkbench.inputs.tags import extract_tags, lint_tags, tag_counts
from cvworkbench.ops.sot_versions import (
    SotPackError,
    activate_version,
    create_version,
    diff_versions,
    initialize_pack,
    list_versions,
)


def _resolve_sot_root(sot_path: Path | None, config: Path) -> Path:
    try:
        resolved = resolve_sot_path(sot_path, config)
        return resolve_versioned_root(resolved)
    except (FileNotFoundError, ValueError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def sot_init(
    source: Annotated[
        Path, typer.Option("--source", help="Source directory or version pack to copy")
    ],
    destination: Annotated[
        Path, typer.Option("--destination", help="Fresh destination for the new pack")
    ],
    name: Annotated[str, typer.Option("--name", help="Initial version name")] = "base",
    plain: Annotated[bool, typer.Option("--plain", help="Use plain text output")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Use JSON output for summaries")
    ] = False,
) -> None:
    """Create a separate version pack from a chosen source; leave config unchanged."""
    configure_output_mode(plain, json_output)
    try:
        result = initialize_pack(source=source, destination=destination, name=name)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.init",
        [
            ("source", result.source),
            ("root", result.root),
            ("active", result.active),
            ("version", result.version),
        ],
    )


def sot_list(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
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
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.list",
        [
            ("root", state.root),
            ("active", state.active),
            ("versions", ", ".join(state.versions)),
        ],
    )


def sot_new(
    name: Annotated[
        str,
        typer.Argument(help="Name for the new SoT version"),
    ],
    from_version: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Base SoT version to copy from",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
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
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
        base = from_version or state.active
        target = create_version(root, name, base)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.new",
        [
            ("name", name),
            ("from", base),
            ("path", target),
        ],
    )


def sot_activate(
    name: Annotated[
        str,
        typer.Argument(help="SoT version to activate"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
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
    root = _resolve_sot_root(sot_path, config)
    try:
        activate_version(root, name)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.activate",
        [
            ("root", root),
            ("active", name),
        ],
    )


def sot_diff(
    left: Annotated[
        str,
        typer.Argument(help="Left-hand SoT version"),
    ],
    right: Annotated[
        str,
        typer.Argument(help="Right-hand SoT version"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
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
    root = _resolve_sot_root(sot_path, config)
    try:
        diff_text = diff_versions(root, left, right)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if get_output_mode() == OutputMode.JSON:
        print_summary(
            "sot.diff",
            [("root", root), ("left", left), ("right", right), ("diff", diff_text)],
        )
        return
    if diff_text:
        typer.echo(diff_text)
        return
    typer.echo("No differences found.")


def tags_list(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    values = sorted({info.normalized for info in tags if info.normalized})

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"tags": values}, indent=2, sort_keys=True))
        return

    for tag in values:
        typer.echo(tag)


def tags_stats(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    counts = tag_counts(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"counts": counts}, indent=2, sort_keys=True))
        return

    for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        typer.echo(f"{tag}: {count}")


def tags_lint(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    issues = lint_tags(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"issues": issues}, indent=2, sort_keys=True))
    else:
        if issues:
            for issue in issues:
                typer.echo(issue)
        else:
            typer.echo("ok")

    if issues:
        raise typer.Exit(code=1)
