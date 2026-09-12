"""Adapt local library inspection and explicit document promotion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import resolve_documents_root
from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
from cvworkbench.ops.documents.records import DocumentError
from cvworkbench.storage import AtomicWriteError
from cvworkbench.workspace.documents import inspect_documents

documents_app = typer.Typer(no_args_is_help=True)


@documents_app.command("list")
def documents_list(
    root: Annotated[
        Path | None, typer.Option("--root", help="Explicit private document library")
    ] = None,
    path: Annotated[
        list[Path] | None, typer.Option("--path", help="Limit inspection to these library paths")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    plain: Annotated[bool, typer.Option("--plain")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List current and working files; manual documents need no native project."""
    configure_output_mode(plain, json_output)
    try:
        result = inspect_documents(root=root, config_path=config, paths=path)
    except (OSError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(json.dumps({"command": "documents.list", "documents": result}, indent=2))
    else:
        print_summary(
            "documents.list",
            [("root", result["root"])]
            + [(item["state"], item["path"]) for item in result["items"]]
            + [("issue", issue) for issue in result["issues"]],
        )
    if result["issues"]:
        raise typer.Exit(2)


@documents_app.command("promote")
def documents_promote(
    request: Annotated[
        Path, typer.Option("--request", help="Explicit JSON source/destination request")
    ],
    root: Annotated[Path | None, typer.Option("--root")] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    apply: Annotated[bool, typer.Option("--apply", help="Apply the reviewed plan")] = False,
    reviewed_sha256: Annotated[str | None, typer.Option("--reviewed-sha256")] = None,
    plain: Annotated[bool, typer.Option("--plain")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Preview by default; preserve predecessors and receipt an exact local promotion."""
    configure_output_mode(plain, json_output)
    try:
        selected = root or (resolve_documents_root(config) if config else None)
        if selected is None:
            raise DocumentError("Choose --root or configure documents.root")
        if apply != (reviewed_sha256 is not None):
            raise DocumentError("--apply requires --reviewed-sha256 from the inspected plan")
        plan = plan_promotion(request_path=request, root=selected)
        receipt = apply_promotion(plan, reviewed_sha256=reviewed_sha256) if apply else None
        result = {
            "command": "documents.promote",
            "status": "promoted" if receipt else "planned",
            "plan_sha256": plan.sha256,
            "plan": plan.payload,
            "receipt": str(receipt) if receipt else None,
        }
    except (OSError, ValueError, AtomicWriteError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        print_summary(
            "documents.promote",
            [("status", result["status"]), ("plan_sha256", plan.sha256)]
            + [
                ("file", f"{item['source']} -> {item['destination']}")
                for item in plan.payload["files"]
            ]
            + ([("receipt", str(receipt))] if receipt else []),
        )
