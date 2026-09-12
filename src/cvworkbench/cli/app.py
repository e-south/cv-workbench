"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/app.py

Register workbench command adapters and their public command groups.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import typer

from cvworkbench.cli.commands.documents.build import (
    build,
    render,
)
from cvworkbench.cli.commands.documents.compare import (
    compare,
    diff,
)
from cvworkbench.cli.commands.documents.review import (
    explain,
    import_docx,
    reviewpack,
)
from cvworkbench.cli.commands.library import documents_app
from cvworkbench.cli.commands.maintenance import (
    clean_dist,
    clean_drafts,
    clean_projects,
    clean_registry,
    clean_reviews,
    clean_runs,
    runs_gc,
)
from cvworkbench.cli.commands.preview import (
    dev_serve,
    dev_stop,
    preview,
)
from cvworkbench.cli.commands.projects.guide import project_guide
from cvworkbench.cli.commands.projects.patch import (
    project_patch_replace_experience_bullet,
    project_patch_replace_project_summary,
)
from cvworkbench.cli.commands.projects.workflow import project_apply, project_new, project_show
from cvworkbench.cli.commands.publication import prepare_public_pdf_command, publication_app, sync
from cvworkbench.cli.commands.setup import (
    doctor,
    init,
    quickstart,
    validate,
)
from cvworkbench.cli.commands.source import (
    sot_activate,
    sot_diff,
    sot_init,
    sot_list,
    sot_new,
    tags_lint,
    tags_list,
    tags_stats,
)
from cvworkbench.cli.commands.tailoring import (
    apply,
    job_add,
    tailor,
)
from cvworkbench.cli.commands.themes import (
    theme_info,
    theme_list,
)
from cvworkbench.cli.commands.variants import (
    variant_discard,
    variant_gc,
    variant_inbox,
    variant_keep,
    variant_list,
    variant_promote,
)
from cvworkbench.cli.commands.workspace import (
    bootstrap,
    context,
    status,
    workflow,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(
    documents_app,
    name="documents",
    help="Find career documents and promote reviewed files locally.",
)
app.add_typer(
    publication_app,
    name="publication",
    help="Inspect authored publication freshness and record exact-PDF review.",
)
app.command("prepare-public-pdf")(prepare_public_pdf_command)
app.command("sync")(sync)
job_app = typer.Typer(no_args_is_help=True)
tags_app = typer.Typer(no_args_is_help=True)
theme_app = typer.Typer(no_args_is_help=True)
dev_app = typer.Typer(no_args_is_help=True)
variant_app = typer.Typer(no_args_is_help=True)
clean_app = typer.Typer(no_args_is_help=True)
sot_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
project_patch_app = typer.Typer(no_args_is_help=True)
runs_app = typer.Typer(no_args_is_help=True)
app.add_typer(job_app, name="job", help="Ingest and inspect job-posting context sources.")
app.add_typer(tags_app, name="tags", help="List, lint, and summarize SoT tags.")
app.add_typer(theme_app, name="theme", help="Inspect available render themes and presets.")
app.add_typer(dev_app, name="dev", help="Control the local preview server lifecycle.")
app.add_typer(
    variant_app,
    name="variant",
    help="Inspect configured variants and manage ephemeral draft/project proposals.",
)
app.add_typer(runs_app, name="runs", help="Inspect or prune build runs.")
app.add_typer(clean_app, name="clean", help="Remove generated workspace artifacts.")
app.add_typer(sot_app, name="sot", help="Inspect and manage SoT version packs.")
app.add_typer(
    project_app,
    name="project",
    help="Create, inspect, and apply job-tailoring project workspaces.",
)
project_app.add_typer(
    project_patch_app,
    name="patch",
    help="Author validated project-op edits without hand-editing patch.yaml.",
)


app.command(help="Validate the configured SoT and fail fast on schema or file errors.")(validate)


app.command(help="Check local toolchain dependencies and workspace prerequisites.")(doctor)


app.command(help="Summarize the current SoT, variants, runs, projects, and reviews.")(status)


app.command(
    help=(
        "Scan workspace state and recommend the next 1-3 workflows. "
        "Use --json --compact for bootstrap, logs, and agent handoff."
    )
)(bootstrap)


app.command(
    help=(
        "Scan workspace state and recommend the next 1-3 workflows. "
        "Use --json --compact for bootstrap, logs, and agent handoff."
    )
)(context)


app.command(
    help=(
        "Inspect workflow recipes from context. Use --json --compact when you want "
        "recipe-focused retrieval instead of the full workspace summary."
    )
)(workflow)


app.command(
    help=(
        "Create or repair local workspace scaffolding, default config, and sample/private "
        "SoT layout."
    )
)(init)


app.command(
    help=(
        "Initialize the sample workspace and build the base variant once. "
        "Use build/preview directly when you want explicit control."
    )
)(quickstart)


theme_app.command("list")(theme_list)


theme_app.command("info")(theme_info)


variant_app.command(
    "promote",
    help="Legacy draft promotion path. Prefer `variant keep` for lifecycle-aware promotion.",
)(variant_promote)


variant_app.command("list", help="Show configured variants alongside lifecycle inbox entries.")(
    variant_list
)


variant_app.command(
    "inbox",
    help="List pending draft/project proposals and flag entries that are expired pending garbage collection.",
)(variant_inbox)


variant_app.command(
    "keep", help="Promote an ephemeral draft or project proposal into config/variants."
)(variant_keep)


variant_app.command(
    "discard", help="Discard an ephemeral draft or project proposal after explicit approval."
)(variant_discard)


variant_app.command("gc", help="Preview or remove expired draft/project proposal artifacts.")(
    variant_gc
)


runs_app.command("gc")(runs_gc)


clean_app.command("runs")(clean_runs)


clean_app.command("dist")(clean_dist)


clean_app.command("drafts")(clean_drafts)


clean_app.command("registry")(clean_registry)


clean_app.command("reviews")(clean_reviews)


clean_app.command("projects")(clean_projects)


sot_app.command("init")(sot_init)


sot_app.command("list")(sot_list)


sot_app.command("new")(sot_new)


sot_app.command("activate")(sot_activate)


sot_app.command("diff")(sot_diff)


job_app.command("add")(job_add)


project_app.command(
    "new",
    help=(
        "Create a project workspace directly from a chosen base variant, with a "
        "project-local proposal variant and patch scaffold. Use `project guide` "
        "if you want ranked recommendations first. `--open` cannot be combined "
        "with `--json`."
    ),
)(project_new)


project_app.command(
    "guide",
    help=(
        "Ingest a job posting, rank candidate variants, and scaffold a "
        "project-local proposal workspace from the selected base variant. "
        "This produces recommendations and editable project artifacts; it does "
        "not rewrite the SoT. `--open` cannot be combined with `--json`."
    ),
)(project_guide)


project_app.command(
    "show",
    help=(
        "Inspect a project proposal, patch status, latest project run, review readiness, "
        "and ready-to-run next commands without mutating the SoT."
    ),
)(project_show)


project_patch_app.command(
    "replace-experience-bullet",
    help=(
        "Append a validated replace-experience-bullet project-op to "
        "proposals/patch.yaml. If --old-text is omitted, the current SoT bullet "
        "text is snapshotted automatically."
    ),
)(project_patch_replace_experience_bullet)


project_patch_app.command(
    "replace-project-summary",
    help=(
        "Append a validated replace-project-summary project-op to "
        "proposals/patch.yaml. If --old-text is omitted, the current SoT project "
        "summary is snapshotted automatically."
    ),
)(project_patch_replace_project_summary)


project_app.command("apply")(project_apply)


tags_app.command("list")(tags_list)


tags_app.command("stats")(tags_stats)


tags_app.command("lint")(tags_lint)


app.command()(explain)


app.command(
    help=(
        "Package a built run for human review. Requires an existing run plus "
        "immutable cv.docx, cv.pdf, and selection.json artifacts for the selected run, "
        "project, or variant. `--run` may be combined with `--project` to pin a "
        "specific project-scoped run."
    )
)(reviewpack)


app.command(
    "import-docx",
    help=(
        "Convert a reviewed DOCX into an import draft. The adjacent review-source.json "
        "pins its baseline. A standalone DOCX requires an explicit `--run`; "
        "variant/project selectors must agree with a recorded source. "
        "When the edited DOCX is a resume "
        "whose Experience bullet or Projects summary text edits map cleanly to "
        "supported source fields, import-docx writes patch.yaml using "
        "structured project-ops; otherwise it falls back to patch.diff against "
        "canonical.md."
    ),
)(import_docx)


app.command(
    help=(
        "Build deterministic artifacts for a configured variant or a project proposal. "
        "Use exactly one of `--variant` or `--project`; --variant cannot be combined "
        "with --project, and --project cannot be combined with --variant."
    )
)(build)


app.command()(render)


dev_app.command("serve")(dev_serve)


dev_app.command("stop")(dev_stop)


app.command(
    help=(
        "Start the local preview server or build one-shot preview output. "
        "Use exactly one of `--variant` or `--project`; --variant cannot be combined "
        "with --project, and --project cannot be combined with --variant. "
        "non-local bind addresses are not supported."
    )
)(preview)


app.command()(tailor)


app.command()(apply)


app.command()(diff)


app.command()(compare)
