"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/preview.py

Adapt local preview and server lifecycle commands to terminal inputs and output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import ipaddress
import os
import signal
import socket
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib import error as url_error
from urllib import request as url_request

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_theme,
    resolve_default_variant,
    resolve_sot_path,
    resolve_style_preset,
    resolve_variant_path,
)
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_active_sot_path,
    resolve_versioned_root,
)
from cvworkbench.ops.projects import (
    ProjectError,
    load_project,
    resolve_project_dir,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.commands import shell_command

if TYPE_CHECKING:
    from cvworkbench.dev.preview import PreviewSession


def _preview_runtime():
    from cvworkbench.dev import preview as preview_runtime

    return preview_runtime


def serve_preview(*args, **kwargs):
    return _preview_runtime().serve_preview(*args, **kwargs)


def _print_serve_summary(
    output_path: Path,
    preview_url: str,
    watching: bool,
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("output_html", output_path),
        ("watching", str(watching).lower()),
        ("controls", "t=theme p=preset v=variant f=format r=rebuild x=stop"),
    ]
    if watching:
        rows.insert(1, ("preview_url", preview_url))
    else:
        rows.insert(1, ("preview_file", output_path))
    print_summary("serve", rows)


def _reject_legacy_preview_env() -> None:
    legacy_vars = [
        "CVW_SKIP_OPEN",
        "CVW_PREVIEW_VIEWER",
        "CVW_OPEN_MODE",
        "CVW_BROWSER",
    ]
    for key in legacy_vars:
        if os.environ.get(key):
            typer.echo(
                f"ERROR: legacy preview environment variable is not supported: {key}",
                err=True,
            )
            raise typer.Exit(code=2)


def _validate_preview_host(host: str) -> str:
    normalized = host.strip()
    if not normalized:
        raise ValueError("CVW_DEV_HOST must not be empty")
    if normalized.lower() == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "CVW_DEV_HOST must be localhost or a loopback address; non-local preview binding is not supported"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            "CVW_DEV_HOST must be localhost or a loopback address; non-local preview binding is not supported"
        )
    return normalized


def _post_preview_stop(url: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    endpoint = url.rstrip("/") + "/api/stop"
    try:
        req = url_request.Request(endpoint, method="POST")
        with url_request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"Preview stop failed with HTTP {response.status}"
    except (url_error.URLError, ValueError) as exc:
        return False, str(exc)


def _preview_api_reachable(url: str, timeout: float = 1.0) -> tuple[bool, str | None]:
    endpoint = url.rstrip("/") + "/api/state"
    try:
        with url_request.urlopen(endpoint, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"Preview state probe failed with HTTP {response.status}"
    except (url_error.URLError, ValueError) as exc:
        return False, str(exc)


def _port_is_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port_close(host: str, port: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_is_open(host, port, timeout=0.2):
            return True
        time.sleep(0.1)
    return False


def _preview_pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _preview_session_conflict(session: PreviewSession) -> tuple[bool, str]:
    api_ok, api_error = _preview_api_reachable(session.url)
    if api_ok:
        detail = f"Preview session already running at {session.url}"
        if session.project_id:
            detail += f" (project={session.project_id})"
        return True, detail
    port_open = _port_is_open(session.host, session.port)
    if _preview_pid_is_live(session.pid) and port_open:
        return True, (
            "Preview session file points to a running process, but the preview API "
            f"is not responding yet ({api_error or 'unknown error'})."
        )
    if port_open:
        return True, (
            "Preview port is still in use even though the recorded preview process is "
            f"not live ({session.host}:{session.port})."
        )
    return False, api_error or "Recorded preview session is stale"


def _terminate_preview_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        typer.echo(f"ERROR: Failed to terminate preview process: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def dev_serve(
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
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build for preview",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Build once and exit without starting the preview server",
        ),
    ] = False,
    with_pdf: Annotated[
        bool,
        typer.Option(
            "--with-pdf",
            help="With --once, also render a PDF alongside HTML",
        ),
    ] = False,
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
    _reject_legacy_preview_env()
    preview = _preview_runtime()
    config_path = resolve_config_path(config)
    project_spec = None
    try:
        if project:
            project_dir = resolve_project_dir(project, config_path)
            project_spec = load_project(project_dir)
            if variant:
                typer.echo("ERROR: --variant cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            resolved_variant_obj = load_variant(project_spec.variant_path)
            resolved_variant = resolved_variant_obj.id
            resolved = resolve_active_sot_path(project_spec.sot_path)
            if sot_path is not None:
                resolved = resolve_sot_path(sot_path, config_path)
        else:
            resolved = resolve_sot_path(sot_path, config_path)
            resolved_variant = variant or resolve_default_variant(config_path)
            variant_path = resolve_variant_path(resolved_variant, config_path)
            resolved_variant_obj = load_variant(variant_path)
        resolved_theme = (
            theme or resolved_variant_obj.render_theme or resolve_default_theme(config_path)
        )
        resolved_preset = (
            style_preset
            or resolved_variant_obj.render_style_preset
            or resolve_style_preset(config_path)
        )
    except (FileNotFoundError, ValueError, SotVersionError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if sot_path is not None:
        sot_base = resolved
    else:
        try:
            sot_base = resolve_versioned_root(resolved)
        except SotVersionError:
            sot_base = resolved

    one_shot = once or os.environ.get("CVW_DEV_ONCE") == "1"
    session_id = uuid.uuid4().hex
    try:
        controller = preview.PreviewController(
            sot_base=sot_base,
            config_path=config_path,
            variant_id=resolved_variant,
            theme_id=resolved_theme,
            style_preset=resolved_preset,
            auto_pdf=(not one_shot) or with_pdf,
            project_dir=project_spec.project_dir if project_spec else None,
            project_sot_override=sot_base if project_spec and sot_path is not None else None,
            session_id=session_id,
        )
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    host = os.environ.get("CVW_DEV_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CVW_DEV_PORT", "8765"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_PORT must be an integer", err=True)
        raise typer.Exit(code=1) from exc
    try:
        idle_timeout_seconds = float(os.environ.get("CVW_DEV_IDLE_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_IDLE_TIMEOUT_SECONDS must be numeric", err=True)
        raise typer.Exit(code=1) from exc
    if idle_timeout_seconds < 0:
        typer.echo("ERROR: CVW_DEV_IDLE_TIMEOUT_SECONDS must be >= 0", err=True)
        raise typer.Exit(code=1)
    if one_shot:
        try:
            state = controller.build_once()
        except preview.PreviewError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        html_path = state.output_files.get("html", state.dist_dir / "cv.html")
        _print_serve_summary(
            html_path,
            str(html_path),
            False,
        )
        return

    try:
        host = _validate_preview_host(host)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    session_path = preview.preview_session_path(config_path)
    if session_path.exists():
        try:
            existing_session = preview.load_preview_session(config_path)
        except preview.PreviewError:
            preview.clear_preview_session(config_path)
        else:
            has_conflict, detail = _preview_session_conflict(existing_session)
            if has_conflict:
                typer.echo(f"ERROR: {detail}", err=True)
                typer.echo(
                    (
                        "HINT: reuse the existing preview URL or run "
                        f"`{shell_command('dev stop')}` before starting a new session."
                    ),
                    err=True,
                )
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)

    def _on_start(url: str, html_path: Path) -> None:
        session = preview.new_preview_session(
            host=host,
            port=port,
            url=url,
            state=controller.state(),
            session_id=session_id,
            project_id=controller.project_id(),
        )
        preview.write_preview_session(session, config_path)
        _print_serve_summary(
            html_path,
            url,
            True,
        )

    try:
        serve_preview(
            controller=controller,
            host=host,
            port=port,
            idle_timeout_seconds=idle_timeout_seconds,
            on_start=_on_start,
        )
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        if exc.errno in {48, 98, 10048}:
            typer.echo(f"ERROR: {exc}", err=True)
            typer.echo(
                (
                    "HINT: preview port is already in use. Run "
                    f"`{shell_command('dev stop')}` or set CVW_DEV_PORT."
                ),
                err=True,
            )
            raise typer.Exit(code=1) from exc
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        preview.clear_preview_session(config_path)


def dev_stop(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Force stop by terminating the preview process",
        ),
    ] = False,
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
    preview = _preview_runtime()
    config_path = resolve_config_path(config)
    try:
        session = preview.load_preview_session(config_path)
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    ok, error = _post_preview_stop(session.url)
    if not ok:
        if force:
            if _preview_pid_is_live(session.pid):
                _terminate_preview_process(session.pid)
        else:
            has_conflict, _detail = _preview_session_conflict(session)
            if has_conflict:
                typer.echo(f"ERROR: {error}", err=True)
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)
            print_summary(
                "dev.stop",
                [
                    ("status", "cleared-stale-session"),
                    ("host", session.host),
                    ("port", session.port),
                ],
            )
            return

    if not _wait_for_port_close(session.host, session.port):
        if force:
            if not _preview_pid_is_live(session.pid):
                typer.echo(
                    f"ERROR: Preview port is still in use at {session.host}:{session.port}",
                    err=True,
                )
                raise typer.Exit(code=1)
            _terminate_preview_process(session.pid)
            if not _wait_for_port_close(session.host, session.port):
                typer.echo("ERROR: Preview server still running", err=True)
                raise typer.Exit(code=1)
        else:
            has_conflict, _detail = _preview_session_conflict(session)
            if has_conflict:
                typer.echo("ERROR: Preview server still running", err=True)
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)
            print_summary(
                "dev.stop",
                [
                    ("status", "cleared-stale-session"),
                    ("host", session.host),
                    ("port", session.port),
                ],
            )
            return

    preview.clear_preview_session(config_path)
    print_summary(
        "dev.stop",
        [
            ("status", "stopped"),
            ("host", session.host),
            ("port", session.port),
        ],
    )


def preview(
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
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build for preview; cannot be combined with --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path; cannot be combined with --variant",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Build once and exit without starting the preview server",
        ),
    ] = False,
    with_pdf: Annotated[
        bool,
        typer.Option(
            "--with-pdf",
            help="With --once, also render a PDF alongside HTML",
        ),
    ] = False,
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
    dev_serve(
        sot_path=sot_path,
        config=config,
        variant=variant,
        project=project,
        theme=theme,
        style_preset=style_preset,
        once=once,
        with_pdf=with_pdf,
        plain=plain,
        json_output=json_output,
    )
