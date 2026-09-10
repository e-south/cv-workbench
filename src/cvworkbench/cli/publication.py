"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/publication.py

Adapts authored publication operations to CLI arguments and operator output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.build.rendering import RenderError
from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_publication_variant,
    resolve_sot_path,
    resolve_sync_mode,
)
from cvworkbench.ops.publication.pdf import PublicPdfError, PublicPdfResult
from cvworkbench.ops.publication.pdf import prepare_public_pdf as prepare_authored_public_pdf
from cvworkbench.ops.publication.policy import PublishError
from cvworkbench.ops.publication.record import hash_file
from cvworkbench.ops.publication.state import (
    PublicationState,
    inspect_publication,
    record_publication_review,
)
from cvworkbench.ops.syncing import SyncError, SyncResult, sync_site

publication_app = typer.Typer(no_args_is_help=True)


def _print_publication_state(command: str, state: PublicationState) -> None:
    if get_output_mode() == OutputMode.JSON:
        typer.echo(
            json.dumps({"command": command, "publication": asdict(state)}, indent=2, sort_keys=True)
        )
        return
    print_summary(
        command,
        [(key, str(value)) for key, value in asdict(state).items() if value and key != "reasons"]
        + [("reasons", "; ".join(state.reasons) or "none")],
    )


@publication_app.command("status")
def publication_status(
    config: Annotated[Path, typer.Option("--config")] = Path("config/workbench.yaml"),
    variant: Annotated[str | None, typer.Option("--variant")] = None,
    sot_path: Annotated[Path | None, typer.Option("--sot-path")] = None,
    publish_config: Annotated[Path | None, typer.Option("--publish-config")] = None,
    plain: Annotated[bool, typer.Option("--plain")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect authored source, export, prepared PDF and recorded review without writes."""
    configure_output_mode(plain, json_output)
    try:
        resolved = resolve_config_path(config)
        state = inspect_publication(
            resolved,
            variant or resolve_publication_variant(resolved),
            publish_config_path=publish_config,
            sot_path=sot_path,
        )
    except (ValueError, OSError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_publication_state("publication.status", state)


@publication_app.command("review")
def publication_review(
    pdf_sha256: Annotated[
        str, typer.Option("--pdf-sha256", help="Hash of the exact public PDF you reviewed")
    ],
    config: Annotated[Path, typer.Option("--config")] = Path("config/workbench.yaml"),
    variant: Annotated[str | None, typer.Option("--variant")] = None,
    sot_path: Annotated[Path | None, typer.Option("--sot-path")] = None,
    publish_config: Annotated[Path | None, typer.Option("--publish-config")] = None,
    plain: Annotated[bool, typer.Option("--plain")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Declare review of the public PDF after checking every page in its visual packet."""
    configure_output_mode(plain, json_output)
    try:
        resolved = resolve_config_path(config)
        state = record_publication_review(
            resolved,
            variant or resolve_publication_variant(resolved),
            pdf_sha256,
            publish_config_path=publish_config,
            sot_path=sot_path,
        )
    except (ValueError, OSError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_publication_state("publication.review", state)


def _print_sync_summary(result: SyncResult) -> None:
    plan = result.plan
    changed_files = len(plan.copy_ops)
    if plan.frontmatter_content:
        changed_files += 1
    if plan.manifest_content:
        changed_files += 1
    status = "no_changes"
    if plan.has_changes():
        status = "pr_created" if result.mode == "pr" else "applied"

    rows: list[tuple[str, str | Path]] = [
        ("sync_mode", result.mode),
        ("sync_status", status),
        ("site_repo", result.site.repo_path),
        ("pdf_url", plan.pdf_url),
        ("files_updated", str(changed_files)),
    ]
    if result.branch:
        rows.append(("branch", result.branch))
    print_summary("sync", rows)


def _print_public_pdf_summary(result: PublicPdfResult) -> None:
    print_summary(
        "prepare-public-pdf",
        [
            ("status", "prepared"),
            ("output_pdf", result.output_pdf),
            ("manifest", result.manifest_path),
            ("preparation", result.output_pdf.parent / "preparation.json"),
            ("pdf_sha256", hash_file(result.output_pdf)),
            ("redactions", str(result.redaction_count)),
            ("review", result.review_path),
        ],
    )


def prepare_public_pdf_command(
    authored_source: Annotated[
        Path,
        typer.Option(
            "--authored-source",
            help="Canonical editable DOCX used to create the exported PDF",
        ),
    ],
    source_pdf: Annotated[
        Path,
        typer.Option(
            "--source-pdf",
            help="Faithful PDF exported from the authored CV source",
        ),
    ],
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Publish variant id (defaults to site.publish_variant)",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    publish_config: Annotated[
        Path | None,
        typer.Option(
            "--publish-config",
            help="Path to public publication policy",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to private Source of Truth data",
        ),
    ] = None,
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
    """Prepare a faithful authored PDF for fail-closed public distribution."""

    configure_output_mode(plain, json_output)
    try:
        resolved_config = resolve_config_path(config)
        resolved_variant = variant or resolve_publication_variant(resolved_config)
        resolved_sot = resolve_sot_path(sot_path, resolved_config)
        resolved_publish = publish_config or resolved_config.parent / "publish.yaml"
        result = prepare_authored_public_pdf(
            authored_source=authored_source.expanduser().resolve(),
            source_pdf=source_pdf.expanduser().resolve(),
            config_path=resolved_config,
            variant_id=resolved_variant,
            publish_config_path=resolved_publish,
            sot_path=resolved_sot,
        )
    except (FileNotFoundError, PublicPdfError, PublishError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_public_pdf_summary(result)


def sync(
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Sync mode: pr or local",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    site_config: Annotated[
        Path,
        typer.Option(
            "--site-config",
            help="Path to site sync config",
        ),
    ] = Path("config/site-sync.yaml"),
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
        resolved_config = resolve_config_path(config)
        resolved_site = resolve_config_path(site_config)
        selected_mode = mode or resolve_sync_mode(resolved_config)
        result = sync_site(
            config_path=resolved_config,
            site_config_path=resolved_site,
            mode=selected_mode,
            publish_config_path=resolved_config.parent / "publish.yaml",
        )
    except (FileNotFoundError, SyncError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_sync_summary(result)
