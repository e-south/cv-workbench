"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/preview.py

Serves a live HTML preview with auto-rebuild and simple theme toggles.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from cvworkbench.build.pipeline import build_documents
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.config import (
    resolve_dist_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.themes import ThemeError, list_themes, resolve_theme


class PreviewError(RuntimeError):
    pass


@dataclass
class PreviewState:
    variant_id: str
    theme_id: str
    style_preset: str | None
    dist_dir: Path
    html_path: Path
    build_id: int
    last_error: str | None = None


@dataclass
class PreviewCatalog:
    themes: list[str]
    presets: dict[str, list[str]]


class PreviewController:
    def __init__(
        self,
        *,
        sot_base: Path,
        config_path: Path,
        variant_id: str,
        theme_id: str,
        style_preset: str | None,
    ) -> None:
        self._lock = threading.Lock()
        self._sot_base = sot_base
        self._config_path = config_path
        self._variant_id = variant_id
        self._theme_id = theme_id
        self._style_preset = style_preset
        self._catalog = self._load_catalog()
        self._state: PreviewState | None = None

    def state(self) -> PreviewState:
        if self._state is None:
            raise PreviewError("Preview state has not been initialized")
        return self._state

    def catalog(self) -> PreviewCatalog:
        return self._catalog

    def rebuild(self, theme_id: str | None = None, style_preset: str | None = None) -> PreviewState:
        with self._lock:
            if theme_id is not None:
                self._theme_id = theme_id
            if style_preset is not None:
                self._style_preset = style_preset

            self._catalog = self._load_catalog()
            self._validate_theme_and_preset(self._theme_id, self._style_preset)

            try:
                sot_path = resolve_sot_path(self._sot_base, self._config_path)
            except (FileNotFoundError, ValueError) as exc:
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

            run_dir = resolve_runs_path(self._config_path) / "preview" / self._variant_id
            try:
                result = build_documents(
                    sot_path=sot_path,
                    config_path=self._config_path,
                    variant_id=self._variant_id,
                    formats=["html"],
                    theme=self._theme_id,
                    style_preset=self._style_preset,
                    run_dir=run_dir,
                )
            except (ValueError, ThemeError) as exc:
                message = str(exc)
                self._state = self._state or self._new_state()
                self._state.last_error = message
                raise PreviewError(message) from exc

            html_path = output_path(result.dist_dir, result.variant, "html")
            build_id = 1 if self._state is None else self._state.build_id + 1
            self._state = PreviewState(
                variant_id=result.variant.id,
                theme_id=result.theme_id or self._theme_id,
                style_preset=result.style_preset or self._style_preset,
                dist_dir=result.dist_dir,
                html_path=html_path,
                build_id=build_id,
                last_error=None,
            )
            return self._state

    def build_once(self) -> PreviewState:
        return self.rebuild()

    def resolve_watch_paths(self) -> list[Path]:
        paths: list[Path] = []
        paths.append(self._config_path)
        try:
            variant_path = resolve_variant_path(self._variant_id, self._config_path)
            paths.append(variant_path)
        except (ValueError, FileNotFoundError):
            pass

        try:
            theme_root = resolve_themes_dir(self._config_path)
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
            "build_id": state.build_id,
            "last_error": state.last_error,
            "output_html": str(state.html_path),
        }

    def _load_catalog(self) -> PreviewCatalog:
        try:
            themes_dir = resolve_themes_dir(self._config_path)
            themes = list_themes(themes_dir)
        except (ThemeError, ValueError, FileNotFoundError) as exc:
            raise PreviewError(str(exc)) from exc
        preset_map: dict[str, list[str]] = {}
        for theme in themes:
            styles_dir = theme.root / "styles" / "html"
            presets = []
            if styles_dir.exists():
                presets = sorted(path.stem for path in styles_dir.glob("*.css"))
            preset_map[theme.id] = presets
        return PreviewCatalog(
            themes=[theme.id for theme in themes],
            presets=preset_map,
        )

    def _validate_theme_and_preset(self, theme_id: str, preset: str | None) -> None:
        if theme_id not in self._catalog.themes:
            raise PreviewError(f"Theme not found: {theme_id}")
        if preset is None:
            return
        presets = self._catalog.presets.get(theme_id, [])
        if preset not in presets:
            raise PreviewError(f"Style preset not found for theme '{theme_id}': {preset}")

    def _new_state(self) -> PreviewState:
        dist_dir = resolve_dist_path(self._config_path) / self._variant_id
        html_path = dist_dir / "cv.html"
        return PreviewState(
            variant_id=self._variant_id,
            theme_id=self._theme_id,
            style_preset=self._style_preset,
            dist_dir=dist_dir,
            html_path=html_path,
            build_id=0,
            last_error=None,
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


def serve_preview(
    *,
    controller: PreviewController,
    host: str,
    port: int,
    on_start: Callable[[str, Path], None],
) -> None:
    controller.build_once()
    state = controller.state()
    handler = _make_handler(controller, state.dist_dir)
    server = ThreadingHTTPServer((host, port), handler)
    preview_url = f"http://{host}:{port}/"
    try:
        on_start(preview_url, state.html_path)
    except Exception:
        server.server_close()
        raise
    stop_event = threading.Event()
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


def _make_handler(controller: PreviewController, dist_dir: Path) -> type[SimpleHTTPRequestHandler]:
    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(dist_dir), **kwargs)

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
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            theme = payload.get("theme")
            preset = payload.get("style_preset")
            try:
                controller.rebuild(theme_id=theme, style_preset=preset)
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

    return PreviewHandler


def _preview_page_html() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>cv-workbench preview</title>
    <style>
      html, body { margin: 0; padding: 0; height: 100%; }
      #overlay {
        position: fixed;
        top: 16px;
        left: 16px;
        background: rgba(20, 26, 34, 0.92);
        color: #f2f5f7;
        font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        border-radius: 12px;
        padding: 12px 14px;
        z-index: 1000;
        box-shadow: 0 10px 30px rgba(0,0,0,0.25);
      }
      #overlay small { color: #9fb4c5; display: block; }
      #overlay kbd {
        background: #1e2a35;
        border-radius: 6px;
        padding: 2px 6px;
        margin-left: 6px;
        font: 12px/1.4 "SFMono-Regular", Menlo, monospace;
      }
      #status { color: #7bdff2; }
      #error { color: #ff9b9b; display: none; margin-top: 6px; }
      #preview {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        border: none;
      }
    </style>
  </head>
  <body>
    <div id="overlay">
      <div><strong>Preview</strong></div>
      <small>Theme: <span id="theme"></span> · Preset: <span id="preset"></span></small>
      <small id="status">Listening for changes…</small>
      <small>Toggle: <kbd>t</kbd> theme <kbd>p</kbd> preset <kbd>r</kbd> rebuild</small>
      <div id="error"></div>
    </div>
    <iframe id="preview" src="/cv.html"></iframe>
    <script>
      const state = { data: null };
      const iframe = document.getElementById('preview');
      const themeEl = document.getElementById('theme');
      const presetEl = document.getElementById('preset');
      const errorEl = document.getElementById('error');

      async function fetchState() {
        const res = await fetch('/api/state');
        if (!res.ok) return null;
        return res.json();
      }

      function renderOverlay(data) {
        themeEl.textContent = data.theme || 'default';
        presetEl.textContent = data.style_preset || 'none';
        if (data.last_error) {
          errorEl.textContent = data.last_error;
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

      async function requestRender(theme, preset) {
        const res = await fetch('/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme, style_preset: preset }),
        });
        const payload = await res.json();
        if (!res.ok) {
          errorEl.textContent = payload.error || 'Build failed';
          errorEl.style.display = 'block';
          return;
        }
        state.data = payload;
        renderOverlay(payload);
        iframe.contentWindow.location.reload();
      }

      async function refresh() {
        const data = await fetchState();
        if (!data) return;
        if (!state.data || state.data.build_id !== data.build_id) {
          iframe.contentWindow.location.reload();
        }
        state.data = data;
        renderOverlay(data);
      }

      document.addEventListener('keydown', async (event) => {
        if (!state.data) return;
        if (event.key === 't') {
          const nextTheme = nextOption(state.data.themes, state.data.theme);
          const presets = state.data.presets[nextTheme] || [];
          const nextPreset = presets.includes(state.data.style_preset)
            ? state.data.style_preset
            : (presets[0] || null);
          await requestRender(nextTheme, nextPreset);
        } else if (event.key === 'p') {
          const presets = state.data.presets[state.data.theme] || [];
          const nextPreset = nextOption(presets, state.data.style_preset);
          await requestRender(state.data.theme, nextPreset);
        } else if (event.key === 'r') {
          await requestRender(state.data.theme, state.data.style_preset);
        }
      });

      refresh();
      setInterval(refresh, 1000);
    </script>
  </body>
</html>
"""
