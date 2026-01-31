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
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

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
from cvworkbench.inputs.sot_versions import SotVersionError, resolve_active_sot_path
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects import ProjectError, load_project, prepare_project_sot
from cvworkbench.themes import ThemeError, list_themes, resolve_theme
from cvworkbench.variants import load_variant


class PreviewError(RuntimeError):
    pass


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
        self._project_id: str | None = None
        self._catalog = self._load_catalog()
        self._state: PreviewState | None = None

    def state(self) -> PreviewState:
        if self._state is None:
            raise PreviewError("Preview state has not been initialized")
        return self._state

    def catalog(self) -> PreviewCatalog:
        return self._catalog

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
                    sot_path = resolve_active_sot_path(project_spec.sot_path)
                    run_dir = (
                        resolve_runs_path(self._config_path) / "preview" / project_spec.project_id
                    )
                    run_dir.mkdir(parents=True, exist_ok=True)
                    sot_path = prepare_project_sot(
                        project_dir=project_spec.project_dir,
                        sot_path=sot_path,
                        run_dir=run_dir,
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
            self._state = PreviewState(
                variant_id=result.variant.id,
                theme_id=result.theme_id or self._theme_id,
                style_preset=result.style_preset or self._style_preset,
                output_format=self._format,
                auto_pdf=self._auto_pdf,
                dist_dir=result.dist_dir,
                output_files=output_files,
                build_id=build_id,
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
            variant = load_variant(path)
            variants.append(variant.id)
        if not variants:
            raise PreviewError("No variants found")
        if self._project_dir is not None:
            try:
                project_spec = load_project(self._project_dir)
            except ProjectError as exc:
                raise PreviewError(str(exc)) from exc
            variants = [project_spec.base_variant_id]
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
    return PreviewSession(
        pid=pid,
        host=host.strip(),
        port=port,
        url=url.strip(),
        variant_id=variant_id.strip(),
        theme_id=theme_id.strip(),
        style_preset=style_preset,
        started_at=started_at.strip(),
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
    on_start: Callable[[str, Path], None],
) -> None:
    controller.build_once()
    state = controller.state()
    stop_event = threading.Event()
    server = ThreadingHTTPServer(
        (host, port), _make_handler(controller, state.dist_dir, stop_event)
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
) -> type[SimpleHTTPRequestHandler]:
    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(dist_dir), **kwargs)

        def translate_path(self, path: str) -> str:
            self.directory = str(controller.state().dist_dir)
            return super().translate_path(path)

        def do_GET(self) -> None:
            if self.path in {"/", "/preview"}:
                self._serve_preview_page()
                return
            if self.path.startswith("/api/state"):
                self._send_json(controller.state_payload())
                return
            super().do_GET()

        def do_POST(self) -> None:
            if not self.path.startswith("/api/render"):
                if self.path.startswith("/api/stop"):
                    self._send_json({"status": "stopping"})
                    self._stop_server()
                    return
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            theme = payload.get("theme") or None
            preset = payload.get("style_preset") or None
            variant = payload.get("variant") or None
            output_format = payload.get("format") or None
            auto_pdf = payload.get("auto_pdf")
            if auto_pdf is not None and not isinstance(auto_pdf, bool):
                self.send_error(400, "auto_pdf must be a boolean")
                return
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
            content = _preview_page_html()
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _stop_server(self) -> None:
            stop_event.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return PreviewHandler


def _preview_page_html() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>cv-workbench preview</title>
    <style>
      html, body {
        margin: 0;
        padding: 0;
        height: 100%;
        background: #e8edf3;
        font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #0f172a;
      }
      #layout {
        display: flex;
        min-height: 100vh;
      }
      #sidebar {
        position: fixed;
        left: 0;
        top: 0;
        bottom: 0;
        width: 280px;
        background: #0f172a;
        color: #e2e8f0;
        padding: 18px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      #brand {
        font-weight: 600;
        font-size: 16px;
        letter-spacing: 0.3px;
      }
      .section {
        display: grid;
        gap: 10px;
      }
      .section-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #94a3b8;
      }
      label {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      select, button {
        background: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 6px 8px;
        font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      button {
        cursor: pointer;
      }
      button:disabled, select:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
      #stop-preview {
        background: #3f1f2a;
        border-color: #5a2535;
        color: #fda4af;
      }
      #format-tabs {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 6px;
      }
      #format-tabs button {
        padding: 6px 0;
        font-size: 12px;
      }
      #format-tabs button.active {
        background: #0ea5e9;
        border-color: #38bdf8;
        color: #0f172a;
        font-weight: 600;
      }
      .toggle {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .toggle input {
        accent-color: #38bdf8;
      }
      #status {
        color: #7dd3fc;
        font-size: 12px;
      }
      #error {
        color: #fda4af;
        font-size: 12px;
        display: none;
      }
      #run-list {
        display: grid;
        gap: 6px;
        font-size: 12px;
        color: #cbd5f5;
      }
      #shortcuts {
        margin-top: auto;
        font-size: 11px;
        color: #94a3b8;
      }
      #shortcuts kbd {
        background: #1e293b;
        border-radius: 6px;
        padding: 2px 6px;
        margin-left: 6px;
        font: 11px/1.4 "SFMono-Regular", Menlo, monospace;
      }
      #preview-area {
        margin-left: 280px;
        width: calc(100% - 280px);
        display: flex;
        justify-content: center;
        align-items: stretch;
        padding: 24px;
        box-sizing: border-box;
      }
      #preview {
        width: min(900px, 100%);
        height: 100%;
        border: none;
        background: #ffffff;
        border-radius: 10px;
        box-shadow: 0 18px 60px rgba(15, 23, 42, 0.18);
      }
    </style>
  </head>
  <body tabindex="0" data-cvw-build-id="">
    <div id="layout">
      <aside id="sidebar">
        <div id="brand">cv-workbench</div>

        <div class="section">
          <div class="section-title">Workspace</div>
          <label>
            <span>Project</span>
            <select id="project-select" data-cvw-control="project"></select>
          </label>
          <label>
            <span>Variant</span>
            <select id="variant-select" data-cvw-control="variant"></select>
          </label>
        </div>

        <div class="section">
          <div class="section-title">Styling</div>
          <label>
            <span>Theme</span>
            <select id="theme-select" data-cvw-control="theme"></select>
          </label>
          <label>
            <span>Preset</span>
            <select id="preset-select" data-cvw-control="preset"></select>
          </label>
        </div>

        <div class="section">
          <div class="section-title">Format</div>
          <div id="format-tabs" data-cvw-control="format-tabs">
            <button data-format="html" data-cvw-format="html" type="button">HTML</button>
            <button data-format="pdf" data-cvw-format="pdf" type="button">PDF</button>
            <button data-format="md" data-cvw-format="md" type="button">MD</button>
            <button data-format="ats" data-cvw-format="ats" type="button">ATS</button>
          </div>
          <label class="toggle">
            <span>Auto PDF</span>
            <input id="auto-pdf-toggle" data-cvw-control="auto-pdf" type="checkbox" />
          </label>
        </div>

        <div class="section">
          <button id="rebuild" data-cvw-action="rebuild" type="button">Rebuild</button>
          <button id="stop-preview" data-cvw-action="stop" type="button">Stop</button>
          <div id="status" data-cvw-status="status">Listening for changes…</div>
          <div id="error" data-cvw-status="error"></div>
        </div>

        <div class="section">
          <div class="section-title">Runs</div>
          <div id="run-list" data-cvw-status="run-list"></div>
        </div>

        <div id="shortcuts">
          Keys:
          <kbd>t</kbd> theme
          <kbd>p</kbd> preset
          <kbd>v</kbd> variant
          <kbd>f</kbd> format
          <kbd>r</kbd> rebuild
          <kbd>x</kbd> stop
        </div>
      </aside>

      <main id="preview-area">
        <iframe id="preview" data-cvw-view="preview-frame" src="/cv.html"></iframe>
      </main>
    </div>
    <script>
      const DISCONNECTED_MESSAGE = 'Preview disconnected';
      const state = { data: null };
      const history = [];
      let stopped = false;
      let connectionError = null;
      let currentFormat = 'html';
      const iframe = document.getElementById('preview');
      const projectSelect = document.getElementById('project-select');
      const variantSelect = document.getElementById('variant-select');
      const themeSelect = document.getElementById('theme-select');
      const presetSelect = document.getElementById('preset-select');
      const autoPdfToggle = document.getElementById('auto-pdf-toggle');
      const formatTabs = document.getElementById('format-tabs');
      const rebuildButton = document.getElementById('rebuild');
      const stopButton = document.getElementById('stop-preview');
      const statusEl = document.getElementById('status');
      const errorEl = document.getElementById('error');
      const runList = document.getElementById('run-list');
      const formats = ['html', 'pdf', 'md', 'ats'];
      let lastSeenBuildId = document.body.dataset.cvwBuildId || '';
      let lastControlsKey = null;
      let lastOverlayKey = null;
      let currentPreviewSrc = iframe.getAttribute('src') || '';

      async function fetchState() {
        const res = await fetch('/api/state');
        if (!res.ok) {
          throw new Error(DISCONNECTED_MESSAGE);
        }
        return res.json();
      }

      function listSignature(list) {
        if (!list || list.length === 0) return '';
        return list.join('|');
      }

      function presetsSignature(presets) {
        if (!presets) return '';
        const themes = Object.keys(presets).sort();
        return themes
          .map((theme) => theme + ':' + listSignature(presets[theme] || []))
          .join('||');
      }

      function controlsSignature(data) {
        return [
          listSignature(data.projects),
          data.project || '',
          listSignature(data.variants),
          data.variant || '',
          listSignature(data.themes),
          data.theme || '',
          presetsSignature(data.presets || {}),
          data.style_preset || '',
          data.format || '',
          data.auto_pdf ? '1' : '0',
        ].join('::');
      }

      function overlaySignature(data) {
        const lastError = data && data.last_error ? data.last_error : '';
        return [stopped ? 'stopped' : 'live', lastError, connectionError || ''].join('::');
      }

      function renderOverlay(data) {
        const lastError = data && data.last_error ? data.last_error : '';
        if (connectionError) {
          statusEl.textContent = DISCONNECTED_MESSAGE + '.';
          errorEl.textContent = connectionError;
          errorEl.style.display = 'block';
          return;
        }
        statusEl.textContent = stopped ? 'Preview stopped.' : 'Listening for changes…';
        if (lastError) {
          errorEl.textContent = lastError;
          errorEl.style.display = 'block';
        } else {
          errorEl.style.display = 'none';
        }
      }

      function nextOption(list, current) {
        if (!list || list.length === 0) return null;
        const idx = list.indexOf(current);
        return list[(idx + 1) % list.length];
      }

      function syncSelect(selectEl, options, current) {
        selectEl.innerHTML = '';
        if (!options || options.length === 0) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'none';
          selectEl.appendChild(opt);
          selectEl.value = '';
          selectEl.disabled = true;
          return;
        }
        selectEl.disabled = false;
        options.forEach((item) => {
          const opt = document.createElement('option');
          opt.value = item;
          opt.textContent = item;
          selectEl.appendChild(opt);
        });
        selectEl.value = current && options.includes(current) ? current : options[0];
      }

      function renderControls(data) {
        syncSelect(projectSelect, data.projects || [], data.project);
        projectSelect.disabled = true;
        syncSelect(variantSelect, data.variants || [], data.variant);
        syncSelect(themeSelect, data.themes || [], data.theme);
        const presets = (data.presets && data.presets[themeSelect.value]) || [];
        syncSelect(presetSelect, presets, data.style_preset);
        autoPdfToggle.checked = !!data.auto_pdf;
        updateFormatButtons();
      }

      function setControlsEnabled(enabled) {
        projectSelect.disabled = !enabled || projectSelect.disabled;
        variantSelect.disabled = !enabled || variantSelect.disabled;
        themeSelect.disabled = !enabled || themeSelect.disabled;
        presetSelect.disabled = !enabled || presetSelect.disabled;
        autoPdfToggle.disabled = !enabled;
        rebuildButton.disabled = !enabled;
        stopButton.disabled = !enabled;
      }

      function syncPreviewSrc() {
        if (!state.data || !state.data.outputs) return;
        const output = state.data.outputs[currentFormat] || state.data.outputs['html'];
        if (!output) return;
        const bust = state.data.build_id ? ('?v=' + state.data.build_id) : '';
        const nextPreviewSrc = '/' + output + bust;
        if (nextPreviewSrc !== currentPreviewSrc) {
          currentPreviewSrc = nextPreviewSrc;
          iframe.src = nextPreviewSrc;
        }
      }

      function updateFormatButtons() {
        const buttons = formatTabs.querySelectorAll('button');
        buttons.forEach((btn) => {
          const active = btn.dataset.format === currentFormat;
          if (active) {
            btn.classList.add('active');
          } else {
            btn.classList.remove('active');
          }
          btn.setAttribute('aria-pressed', active ? 'true' : 'false');
          btn.setAttribute('data-cvw-active', active ? 'true' : 'false');
        });
      }

      function recordRun(data) {
        if (!data || !data.build_id) return;
        if (history.some((entry) => entry.id === data.build_id)) return;
        history.unshift({ id: data.build_id, time: new Date().toLocaleTimeString() });
        if (history.length > 6) history.pop();
        runList.innerHTML = '';
        history.forEach((entry) => {
          const line = document.createElement('div');
          line.textContent = '#' + entry.id + ' @ ' + entry.time;
          runList.appendChild(line);
        });
      }

      function applyState(data) {
        if (!data) return;
        state.data = data;
        currentFormat = data.format || currentFormat;
        const nextBuildId = data.build_id ? String(data.build_id) : '';
        const buildChanged = nextBuildId !== lastSeenBuildId;
        if (buildChanged) {
          lastSeenBuildId = nextBuildId;
          document.body.dataset.cvwBuildId = nextBuildId;
          recordRun(data);
        }
        const nextControlsKey = controlsSignature(data);
        if (nextControlsKey !== lastControlsKey) {
          lastControlsKey = nextControlsKey;
          renderControls(data);
        }
        const nextOverlayKey = overlaySignature(data);
        if (nextOverlayKey !== lastOverlayKey) {
          lastOverlayKey = nextOverlayKey;
          renderOverlay(data);
        }
        syncPreviewSrc();
      }

      async function requestRender(theme, preset, variant, format, autoPdf) {
        const res = await fetch('/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            theme,
            style_preset: preset || null,
            variant: variant || null,
            format: format || null,
            auto_pdf: autoPdf,
          }),
        });
        const payload = await res.json();
        if (!res.ok) {
          errorEl.textContent = payload.error || 'Build failed';
          errorEl.style.display = 'block';
          return;
        }
        applyState(payload);
      }

      async function requestStop() {
        const res = await fetch('/api/stop', { method: 'POST' });
        if (!res.ok) {
          errorEl.textContent = 'Failed to stop preview';
          errorEl.style.display = 'block';
          return;
        }
        stopped = true;
        connectionError = null;
        setControlsEnabled(false);
        const data = state.data || {};
        renderOverlay(data);
        lastOverlayKey = overlaySignature(data);
      }

      async function refresh() {
        if (stopped) return;
        try {
          const data = await fetchState();
          connectionError = null;
          applyState(data);
        } catch (_) {
          connectionError = DISCONNECTED_MESSAGE;
          const data = state.data || {};
          const nextOverlayKey = overlaySignature(data);
          if (nextOverlayKey !== lastOverlayKey) {
            lastOverlayKey = nextOverlayKey;
            renderOverlay(data);
          }
        }
      }

      async function handleKey(event) {
        if (stopped) return;
        if (!state.data) return;
        const active = document.activeElement;
        if (active && ['INPUT', 'SELECT', 'TEXTAREA'].includes(active.tagName)) return;
        if (event.key === 't') {
          const nextTheme = nextOption(state.data.themes, state.data.theme);
          const presets = state.data.presets[nextTheme] || [];
          const nextPreset = presets.includes(state.data.style_preset)
            ? state.data.style_preset
            : (presets[0] || null);
          await requestRender(nextTheme, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
        } else if (event.key === 'p') {
          const presets = state.data.presets[state.data.theme] || [];
          const nextPreset = nextOption(presets, state.data.style_preset);
          await requestRender(state.data.theme, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
        } else if (event.key === 'v') {
          const nextVariant = nextOption(state.data.variants, state.data.variant);
          await requestRender(state.data.theme, state.data.style_preset, nextVariant, currentFormat, autoPdfToggle.checked);
        } else if (event.key === 'f') {
          const nextFormat = nextOption(formats, currentFormat);
          currentFormat = nextFormat || currentFormat;
          await requestRender(state.data.theme, state.data.style_preset, state.data.variant, currentFormat, autoPdfToggle.checked);
        } else if (event.key === 'r') {
          await requestRender(state.data.theme, state.data.style_preset, state.data.variant, currentFormat, autoPdfToggle.checked);
        } else if (event.key === 'x') {
          await requestStop();
        }
      }

      document.addEventListener('keydown', handleKey);
      iframe.addEventListener('load', () => {
        try {
          iframe.contentWindow.addEventListener('keydown', handleKey);
        } catch (_) {
          // ignore cross-origin or access errors
        }
      });

      themeSelect.addEventListener('change', async () => {
        if (!state.data) return;
        const presets = state.data.presets[themeSelect.value] || [];
        const nextPreset = presets[0] || null;
        await requestRender(themeSelect.value, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
      });

      presetSelect.addEventListener('change', async () => {
        if (!state.data) return;
        const value = presetSelect.value || null;
        await requestRender(themeSelect.value, value, state.data.variant, currentFormat, autoPdfToggle.checked);
      });

      variantSelect.addEventListener('change', async () => {
        if (!state.data) return;
        await requestRender(themeSelect.value, presetSelect.value || null, variantSelect.value, currentFormat, autoPdfToggle.checked);
      });

      projectSelect.addEventListener('change', async () => {
        return;
      });

      formatTabs.addEventListener('click', async (event) => {
        if (!state.data) return;
        const target = event.target;
        if (!target || !target.dataset) return;
        const nextFormat = target.dataset.format;
        if (!nextFormat) return;
        currentFormat = nextFormat;
        await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, currentFormat, autoPdfToggle.checked);
      });

      autoPdfToggle.addEventListener('change', async () => {
        if (!state.data) return;
        await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, currentFormat, autoPdfToggle.checked);
      });

      rebuildButton.addEventListener('click', async () => {
        if (!state.data) return;
        await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, currentFormat, autoPdfToggle.checked);
      });

      stopButton.addEventListener('click', async () => {
        await requestStop();
      });

      refresh();
      setInterval(refresh, 1000);
    </script>
  </body>
</html>
"""
