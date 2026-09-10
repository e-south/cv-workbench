"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/preview.py

Serves a live HTML preview with auto-rebuild and simple theme toggles.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import build_documents
from cvworkbench.config import (
    resolve_config_path,
    resolve_dist_path,
    resolve_projects_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.dev.presentation import preview_page_html
from cvworkbench.dev.preview_http import (
    REQUEST_TIMEOUT_SECONDS,
    PreviewRequestError,
    render_body_length,
    validate_request_origin,
)
from cvworkbench.inputs.sot_versions import SotVersionError, resolve_active_sot_path
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects import (
    ProjectError,
    load_project,
    load_project_details,
    load_project_plan,
    prepare_project_sot,
    project_patch_render_warning,
    project_patch_status,
)
from cvworkbench.themes import ThemeError, list_themes, resolve_theme
from cvworkbench.variants import load_variant
from cvworkbench.workspace.project_guidance import (
    proposal_plan_selection_warning,
)


class PreviewError(RuntimeError):
    pass


_CLIENT_DISCONNECT_ERRORS = (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)


@dataclass
class PreviewState:
    variant_id: str
    theme_id: str
    style_preset: str | None
    output_format: str
    auto_pdf: bool
    dist_dir: Path
    output_files: dict[str, Path]
    build_id: int
    project_context: dict[str, Any] | None = None
    last_error: str | None = None


@dataclass
class PreviewCatalog:
    themes: list[str]
    presets: dict[str, list[str]]
    variants: list[str]
    projects: list[str]


@dataclass
class PreviewSession:
    pid: int
    host: str
    port: int
    url: str
    variant_id: str
    theme_id: str
    style_preset: str | None
    started_at: str
    session_id: str | None = None
    project_id: str | None = None


@dataclass
class ClientActivity:
    last_seen_monotonic: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def touch(self) -> None:
        with self._lock:
            self.last_seen_monotonic = time.monotonic()

    def idle_for_seconds(self) -> float | None:
        with self._lock:
            if self.last_seen_monotonic is None:
                return None
        return time.monotonic() - self.last_seen_monotonic


def _project_context_error_payload(project_dir: Path, error: str) -> dict[str, Any]:
    project_id = project_dir.name
    try:
        project_id = load_project(project_dir).project_id
    except ProjectError:
        pass
    return {
        "project_id": project_id,
        "project_context_error": error,
    }


def _load_project_context(project_dir: Path) -> dict[str, Any]:
    try:
        details = load_project_details(project_dir)
    except ProjectError as exc:
        return _project_context_error_payload(project_dir, str(exc))
    patch_warning = project_patch_render_warning(
        proposal_document_type=details.proposal_document_type,
        patch_operations=details.patch_operations,
    )
    patch_status = project_patch_status(
        patch_format=details.patch_format,
        patch_is_empty=details.patch_is_empty,
        patch_line_count=details.patch_line_count,
    )
    proposal_plan, proposal_plan_error = load_project_plan(details)
    payload: dict[str, Any] = {
        "project_id": details.spec.project_id,
        "proposal_document_type": details.proposal_document_type,
        "patch_status": patch_status,
        "patch_operations": list(details.patch_operations),
        "render_warning": patch_warning,
    }
    if proposal_plan is not None:
        payload["recommended_variant"] = proposal_plan.get("selected_variant")
        payload["recommendation_status"] = proposal_plan.get("status")
        payload["recommendation_summary"] = proposal_plan.get("summary")
        missing_values = proposal_plan.get("job_keywords_missing_in_sot")
        if isinstance(missing_values, list):
            payload["job_keywords_missing"] = [
                str(item).strip()
                for item in missing_values
                if isinstance(item, str) and item.strip()
            ]
        step_values = proposal_plan.get("steps")
        if isinstance(step_values, list):
            payload["steps"] = [
                str(item).strip() for item in step_values if isinstance(item, str) and item.strip()
            ]
    if proposal_plan_error is not None:
        payload["proposal_plan_error"] = proposal_plan_error
    plan_warning = proposal_plan_selection_warning(proposal_plan, details.spec.base_variant_id)
    if plan_warning is not None:
        payload["proposal_plan_warning"] = plan_warning
    return payload


class PreviewController:
    def __init__(
        self,
        *,
        sot_base: Path,
        config_path: Path,
        variant_id: str,
        theme_id: str,
        style_preset: str | None,
        output_format: str = "html",
        auto_pdf: bool = True,
        project_dir: Path | None = None,
        project_sot_override: Path | None = None,
        session_id: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._sot_base = sot_base
        self._config_path = config_path
        self._variant_id = variant_id
        self._theme_id = theme_id
        self._style_preset = style_preset
        self._format = output_format
        self._auto_pdf = auto_pdf
        self._project_dir = project_dir
        self._project_sot_override = project_sot_override
        self._project_id: str | None = None
        self._session_id = session_id
        self._catalog = self._load_catalog()
        self._state: PreviewState | None = None

    def state(self) -> PreviewState:
        if self._state is None:
            raise PreviewError("Preview state has not been initialized")
        return self._state

    def catalog(self) -> PreviewCatalog:
        return self._catalog

    def project_id(self) -> str | None:
        return self._project_id

    def rebuild(
        self,
        variant_id: str | None = None,
        theme_id: str | None = None,
        style_preset: str | None = None,
        output_format: str | None = None,
        auto_pdf: bool | None = None,
    ) -> PreviewState:
        with self._lock:
            if variant_id is not None:
                self._variant_id = variant_id
            if theme_id is not None:
                self._theme_id = theme_id
            if style_preset is not None:
                self._style_preset = style_preset
            if output_format is not None:
                self._format = output_format
            if auto_pdf is not None:
                self._auto_pdf = auto_pdf

            self._catalog = self._load_catalog()
            self._validate_variant(self._variant_id)
            self._validate_theme_and_preset(self._theme_id, self._style_preset)
            self._validate_format(self._format)

            variant_path_override = None
            try:
                if self._project_dir is not None:
                    project_spec = load_project(self._project_dir)
                    self._project_id = project_spec.project_id
                    variant_path_override = project_spec.variant_path
                    self._variant_id = load_variant(project_spec.variant_path).id
                    if self._project_sot_override is not None:
                        sot_path = resolve_sot_path(self._project_sot_override, self._config_path)
                    else:
                        sot_path = resolve_active_sot_path(project_spec.sot_path)
                    run_dir = (
                        resolve_runs_path(self._config_path) / "preview" / project_spec.project_id
                    )
                    run_dir.mkdir(parents=True, exist_ok=True)
                    staging_dir = (
                        resolve_runs_path(self._config_path)
                        / "preview-staging"
                        / project_spec.project_id
                        / "sot"
                    )
                    sot_path = prepare_project_sot(
                        project_dir=project_spec.project_dir,
                        sot_path=sot_path,
                        target_dir=staging_dir,
                    )
                else:
                    sot_path = resolve_sot_path(self._sot_base, self._config_path)
                    run_dir = resolve_runs_path(self._config_path) / "preview" / self._variant_id
            except (FileNotFoundError, ValueError, ProjectError, SotVersionError) as exc:
                message = str(exc)
                self._state = self._state or self._new_state()
                self._state.last_error = message
                raise PreviewError(message) from exc

            errors = validate_sot(sot_path)
            if errors:
                message = "; ".join(errors)
                self._state = self._state or self._new_state()
                self._state.last_error = message
                raise PreviewError(message)

            try:
                result = build_documents(
                    sot_path=sot_path,
                    config_path=self._config_path,
                    variant_id=self._variant_id,
                    formats=_resolve_preview_formats(self._format, self._auto_pdf),
                    theme=self._theme_id,
                    style_preset=self._style_preset,
                    variant_path_override=variant_path_override,
                    run_dir=run_dir,
                    dist_dir=run_dir if self._project_dir is not None else None,
                    write_audit_artifacts=False,
                )
            except (ValueError, ThemeError) as exc:
                message = str(exc)
                self._state = self._state or self._new_state()
                self._state.last_error = message
                raise PreviewError(message) from exc

            output_files = {
                fmt: output_path(result.dist_dir, result.variant, fmt) for fmt in result.formats
            }
            build_id = 1 if self._state is None else self._state.build_id + 1
            project_context = None
            if self._project_dir is not None:
                project_context = _load_project_context(self._project_dir)
            self._state = PreviewState(
                variant_id=result.variant.id,
                theme_id=result.theme_id or self._theme_id,
                style_preset=result.style_preset or self._style_preset,
                output_format=self._format,
                auto_pdf=self._auto_pdf,
                dist_dir=result.dist_dir,
                output_files=output_files,
                build_id=build_id,
                project_context=project_context,
                last_error=None,
            )
            return self._state

    def build_once(self) -> PreviewState:
        return self.rebuild()

    def resolve_watch_paths(self) -> list[Path]:
        paths: list[Path] = []
        paths.append(self._config_path)
        resolved_config = resolve_config_path(self._config_path)
        variants_dir = resolved_config.parent / "variants"
        if variants_dir.exists():
            paths.append(variants_dir)
        try:
            variant_path = resolve_variant_path(self._variant_id, self._config_path)
            paths.append(variant_path)
        except (ValueError, FileNotFoundError):
            pass

        if self._project_dir is not None:
            project_file = self._project_dir / "project.yaml"
            if project_file.exists():
                paths.append(project_file)
            patch_path = self._project_dir / "proposals" / "patch.yaml"
            if patch_path.exists():
                paths.append(patch_path)
            project_variant = self._project_dir / "proposals" / "variant.yaml"
            if project_variant.exists():
                paths.append(project_variant)

        try:
            theme_root = resolve_themes_dir(self._config_path)
            if theme_root.exists():
                paths.append(theme_root)
            theme_dir = resolve_theme(theme_root, self._theme_id).root
            paths.append(theme_dir)
        except (ValueError, ThemeError, FileNotFoundError):
            pass

        paths.append(filters_dir())
        sot_path = resolve_sot_path(self._sot_base, self._config_path)
        paths.append(sot_path)
        active_file = self._sot_base / "ACTIVE"
        if active_file.exists():
            paths.append(active_file)
        return paths

    def state_payload(self) -> dict[str, Any]:
        state = self.state()
        return {
            "session_id": self._session_id,
            "variant": state.variant_id,
            "theme": state.theme_id,
            "style_preset": state.style_preset,
            "themes": self._catalog.themes,
            "presets": self._catalog.presets,
            "variants": self._catalog.variants,
            "projects": self._catalog.projects,
            "project": self._project_id,
            "format": state.output_format,
            "auto_pdf": state.auto_pdf,
            "build_id": state.build_id,
            "project_context": state.project_context,
            "last_error": state.last_error,
            "outputs": {fmt: path.name for fmt, path in state.output_files.items()},
        }

    def _load_catalog(self) -> PreviewCatalog:
        try:
            themes_dir = resolve_themes_dir(self._config_path)
            themes = list_themes(themes_dir)
        except (ThemeError, ValueError, FileNotFoundError) as exc:
            raise PreviewError(str(exc)) from exc
        variant_dir = self._config_path.parent / "variants"
        if not variant_dir.exists():
            raise PreviewError(f"Variants directory not found: {variant_dir}")
        variants: list[str] = []
        for path in sorted(variant_dir.glob("*.yaml")):
            try:
                variant = load_variant(path)
            except ValueError as exc:
                raise PreviewError(str(exc)) from exc
            variants.append(variant.id)
        if not variants:
            raise PreviewError("No variants found")
        if self._project_dir is not None:
            try:
                project_spec = load_project(self._project_dir)
            except ProjectError as exc:
                raise PreviewError(str(exc)) from exc
            try:
                variants = [load_variant(project_spec.variant_path).id]
            except ValueError as exc:
                raise PreviewError(str(exc)) from exc
        preset_map: dict[str, list[str]] = {}
        for theme in themes:
            styles_dir = theme.root / "styles" / "html"
            presets = []
            if styles_dir.exists():
                presets = sorted(path.stem for path in styles_dir.glob("*.css"))
            preset_map[theme.id] = presets
        projects: list[str] = []
        try:
            projects_root = resolve_projects_path(self._config_path)
            if projects_root.exists():
                projects = sorted([path.name for path in projects_root.iterdir() if path.is_dir()])
        except (ValueError, FileNotFoundError):
            projects = []
        if self._project_dir is not None:
            try:
                project_id = load_project(self._project_dir).project_id
            except ProjectError as exc:
                raise PreviewError(str(exc)) from exc
            if project_id not in projects:
                projects.append(project_id)
        return PreviewCatalog(
            themes=[theme.id for theme in themes],
            presets=preset_map,
            variants=variants,
            projects=projects,
        )

    def _validate_theme_and_preset(self, theme_id: str, preset: str | None) -> None:
        if theme_id not in self._catalog.themes:
            raise PreviewError(f"Theme not found: {theme_id}")
        if preset is None:
            return
        presets = self._catalog.presets.get(theme_id, [])
        if preset not in presets:
            raise PreviewError(f"Style preset not found for theme '{theme_id}': {preset}")

    def _validate_variant(self, variant_id: str) -> None:
        if variant_id not in self._catalog.variants:
            raise PreviewError(f"Variant not found: {variant_id}")

    def _validate_format(self, output_format: str) -> None:
        allowed = {"html", "pdf", "md", "ats"}
        if output_format not in allowed:
            raise PreviewError(f"Format not supported: {output_format}")

    def _new_state(self) -> PreviewState:
        dist_dir = resolve_dist_path(self._config_path) / self._variant_id
        return PreviewState(
            variant_id=self._variant_id,
            theme_id=self._theme_id,
            style_preset=self._style_preset,
            output_format=self._format,
            auto_pdf=self._auto_pdf,
            dist_dir=dist_dir,
            output_files={},
            build_id=0,
            project_context=None,
            last_error=None,
        )


def preview_session_path(config_path: Path) -> Path:
    return resolve_runs_path(config_path) / "preview" / "session.json"


def write_preview_session(session: PreviewSession, config_path: Path) -> Path:
    path = preview_session_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": session.pid,
        "host": session.host,
        "port": session.port,
        "url": session.url,
        "variant": session.variant_id,
        "theme": session.theme_id,
        "style_preset": session.style_preset,
        "started_at": session.started_at,
        "session_id": session.session_id,
        "project": session.project_id,
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_preview_session(config_path: Path) -> PreviewSession:
    path = preview_session_path(config_path)
    if not path.exists():
        raise PreviewError(f"Preview session file not found: {path}")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise PreviewError("Preview session file is invalid")
    try:
        pid = int(raw["pid"])
        host = raw["host"]
        port = int(raw["port"])
        url = raw["url"]
        variant_id = raw["variant"]
        theme_id = raw["theme"]
        style_preset = raw["style_preset"]
        started_at = raw["started_at"]
        session_id = raw.get("session_id")
        project_id = raw.get("project")
    except (KeyError, ValueError, TypeError) as exc:
        raise PreviewError("Preview session file is invalid") from exc
    if not isinstance(host, str) or not host.strip():
        raise PreviewError("Preview session file is invalid")
    if not isinstance(url, str) or not url.strip():
        raise PreviewError("Preview session file is invalid")
    if not isinstance(variant_id, str) or not variant_id.strip():
        raise PreviewError("Preview session file is invalid")
    if not isinstance(theme_id, str) or not theme_id.strip():
        raise PreviewError("Preview session file is invalid")
    if style_preset is not None:
        if not isinstance(style_preset, str) or not style_preset.strip():
            raise PreviewError("Preview session file is invalid")
        style_preset = style_preset.strip()
    if not isinstance(started_at, str) or not started_at.strip():
        raise PreviewError("Preview session file is invalid")
    if session_id is not None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise PreviewError("Preview session file is invalid")
        session_id = session_id.strip()
    if project_id is not None:
        if not isinstance(project_id, str) or not project_id.strip():
            raise PreviewError("Preview session file is invalid")
        project_id = project_id.strip()
    return PreviewSession(
        pid=pid,
        host=host.strip(),
        port=port,
        url=url.strip(),
        variant_id=variant_id.strip(),
        theme_id=theme_id.strip(),
        style_preset=style_preset,
        started_at=started_at.strip(),
        session_id=session_id,
        project_id=project_id,
    )


def clear_preview_session(config_path: Path) -> None:
    path = preview_session_path(config_path)
    if path.exists():
        path.unlink()


def new_preview_session(
    *,
    host: str,
    port: int,
    url: str,
    state: PreviewState,
    session_id: str | None = None,
    project_id: str | None = None,
) -> PreviewSession:
    return PreviewSession(
        pid=os.getpid(),
        host=host,
        port=port,
        url=url,
        variant_id=state.variant_id,
        theme_id=state.theme_id,
        style_preset=state.style_preset,
        started_at=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        project_id=project_id,
    )


class PreviewWatcher(threading.Thread):
    def __init__(self, controller: PreviewController, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self._controller = controller
        self._stop_event = stop_event
        self._snapshot = FileSnapshot(controller.resolve_watch_paths())

    def run(self) -> None:
        while not self._stop_event.wait(0.5):
            paths = self._controller.resolve_watch_paths()
            next_snapshot = FileSnapshot(paths)
            if next_snapshot.changed(self._snapshot):
                try:
                    self._controller.rebuild()
                except PreviewError:
                    pass
                self._snapshot = FileSnapshot(self._controller.resolve_watch_paths())


class PreviewIdleWatchdog(threading.Thread):
    def __init__(
        self,
        *,
        activity: ClientActivity,
        stop_event: threading.Event,
        server: ThreadingHTTPServer,
        idle_timeout_seconds: float,
    ) -> None:
        super().__init__(daemon=True)
        self._activity = activity
        self._stop_event = stop_event
        self._server = server
        self._idle_timeout_seconds = idle_timeout_seconds

    def run(self) -> None:
        wait_interval = min(1.0, max(0.01, self._idle_timeout_seconds / 4))
        while not self._stop_event.wait(wait_interval):
            idle_for_seconds = self._activity.idle_for_seconds()
            if idle_for_seconds is None:
                continue
            if idle_for_seconds < self._idle_timeout_seconds:
                continue
            self._stop_event.set()
            threading.Thread(target=self._server.shutdown, daemon=True).start()
            return


class FileSnapshot:
    def __init__(self, paths: list[Path]) -> None:
        self._entries = _scan_paths(paths)

    def changed(self, other: "FileSnapshot") -> bool:
        return self._entries != other._entries


def _scan_paths(paths: list[Path]) -> dict[str, float]:
    entries: dict[str, float] = {}
    for path in paths:
        if path.is_dir():
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    entries[str(file_path)] = file_path.stat().st_mtime
        elif path.exists():
            entries[str(path)] = path.stat().st_mtime
    return entries


def _resolve_preview_formats(output_format: str, auto_pdf: bool) -> list[str]:
    formats = ["html"]
    if auto_pdf or output_format == "pdf":
        formats.append("pdf")
    if output_format in {"md", "ats"}:
        formats.append(output_format)
    seen: set[str] = set()
    ordered: list[str] = []
    for fmt in formats:
        if fmt in seen:
            continue
        seen.add(fmt)
        ordered.append(fmt)
    return ordered


def serve_preview(
    *,
    controller: PreviewController,
    host: str,
    port: int,
    idle_timeout_seconds: float,
    on_start: Callable[[str, Path], None],
) -> None:
    controller.build_once()
    state = controller.state()
    stop_event = threading.Event()
    client_activity = ClientActivity()
    server = ThreadingHTTPServer(
        (host, port),
        _make_handler(controller, state.dist_dir, stop_event, client_activity=client_activity),
    )
    preview_url = f"http://{host}:{port}/"
    try:
        html_path = state.output_files.get("html", state.dist_dir / "cv.html")
        on_start(preview_url, html_path)
    except Exception:
        server.server_close()
        raise
    watcher = PreviewWatcher(controller, stop_event)
    watcher.start()
    idle_watchdog: PreviewIdleWatchdog | None = None
    if idle_timeout_seconds > 0:
        idle_watchdog = PreviewIdleWatchdog(
            activity=client_activity,
            stop_event=stop_event,
            server=server,
            idle_timeout_seconds=idle_timeout_seconds,
        )
        idle_watchdog.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()


def _make_handler(
    controller: PreviewController,
    dist_dir: Path,
    stop_event: threading.Event,
    *,
    client_activity: ClientActivity,
) -> type[SimpleHTTPRequestHandler]:
    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(dist_dir), **kwargs)

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "no-referrer")
            super().end_headers()

        def _accept_request(self) -> bool:
            try:
                validate_request_origin(self.headers, self.server.server_port)
            except PreviewRequestError as exc:
                self.send_error(exc.status, str(exc))
                return False
            return True

        def translate_path(self, path: str) -> str:
            self.directory = str(controller.state().dist_dir)
            return super().translate_path(path)

        def do_GET(self) -> None:
            if not self._accept_request():
                return
            client_activity.touch()
            path = urlsplit(self.path).path
            if path in {"/", "/preview"}:
                self._serve_preview_page()
                return
            if path == "/api/state":
                self._send_json(controller.state_payload())
                return
            self._serve_static()

        def do_HEAD(self) -> None:
            if self._accept_request():
                super().do_HEAD()

        def do_POST(self) -> None:
            if not self._accept_request():
                return
            client_activity.touch()
            path = urlsplit(self.path).path
            if path != "/api/render":
                if path == "/api/stop":
                    self._send_json({"status": "stopping"})
                    self._stop_server()
                    return
                self.send_error(404)
                return
            try:
                length = render_body_length(self.headers)
                raw_body = self.rfile.read(length) if length else b""
                if len(raw_body) != length:
                    raise PreviewRequestError("Preview request body is incomplete")
                body = raw_body.decode("utf-8")
                payload = _parse_render_payload(body)
            except PreviewRequestError as exc:
                self._send_json({"error": str(exc)}, status=exc.status)
                return
            except (UnicodeDecodeError, TimeoutError):
                self._send_json(
                    {"error": "Preview request body is incomplete or invalid UTF-8"}, status=400
                )
                return
            except PreviewError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            theme = payload.get("theme") or None
            preset = payload.get("style_preset") or None
            variant = payload.get("variant") or None
            output_format = payload.get("format") or None
            auto_pdf = payload.get("auto_pdf")
            try:
                controller.rebuild(
                    variant_id=variant,
                    theme_id=theme,
                    style_preset=preset,
                    output_format=output_format,
                    auto_pdf=auto_pdf,
                )
            except PreviewError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(controller.state_payload())

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _serve_preview_page(self) -> None:
            content = preview_page_html()
            data = content.encode("utf-8")
            self._write_response(200, "text/html; charset=utf-8", data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload).encode("utf-8")
            self._write_response(status, "application/json", data)

        def _stop_server(self) -> None:
            stop_event.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _serve_static(self) -> None:
            try:
                super().do_GET()
            except _CLIENT_DISCONNECT_ERRORS:
                return

        def _write_response(self, status: int, content_type: str, data: bytes) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except _CLIENT_DISCONNECT_ERRORS:
                return

    return PreviewHandler


def _parse_render_payload(body: str) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PreviewError("Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PreviewError("Render request body must be a JSON object")
    auto_pdf = payload.get("auto_pdf")
    if auto_pdf is not None and not isinstance(auto_pdf, bool):
        raise PreviewError("auto_pdf must be a boolean")
    return payload
