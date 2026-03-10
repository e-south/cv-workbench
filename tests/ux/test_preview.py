"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ux/test_preview.py

Tests preview controller behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request

from cvworkbench.config import resolve_config_path, resolve_themes_dir
from cvworkbench.dev.preview import (
    ClientActivity,
    PreviewController,
    PreviewIdleWatchdog,
    _make_handler,
    _preview_page_html,
)


def test_preview_controller_watch_paths() -> None:
    config_path = Path("config/workbench.yaml")
    controller = PreviewController(
        sot_base=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        theme_id="default",
        style_preset="modern",
    )

    paths = controller.resolve_watch_paths()

    assert paths


def test_preview_watch_paths_include_variants_and_themes_root() -> None:
    config_path = Path("config/workbench.yaml")
    controller = PreviewController(
        sot_base=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        theme_id="default",
        style_preset="modern",
    )

    paths = controller.resolve_watch_paths()
    resolved_config = resolve_config_path(config_path)
    variants_dir = resolved_config.parent / "variants"
    themes_root = resolve_themes_dir(config_path)

    assert variants_dir in paths
    assert themes_root in paths


def test_preview_page_html_contains_controls() -> None:
    html = _preview_page_html()

    assert 'id="sidebar"' in html
    assert 'src="about:blank"' in html
    assert 'id="variant-select"' in html
    assert 'id="theme-select"' in html
    assert 'id="preset-select"' in html
    assert 'id="format-tabs"' in html
    assert 'id="auto-pdf-toggle"' in html
    assert 'id="stop-preview"' in html


def test_preview_page_sidebar_left() -> None:
    html = _preview_page_html()

    assert "left: 0" in html
    assert "width:" in html


def test_preview_keyboard_shortcuts_ignore_interactive_controls() -> None:
    html = _preview_page_html()

    assert "['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A']" in html
    assert "button,select,input,textarea,a,[role=\"button\"],[role=\"tab\"]" in html


class _StubState:
    def __init__(self, dist_dir: Path) -> None:
        self.dist_dir = dist_dir


class _StubController:
    def __init__(self, dist_dir: Path) -> None:
        self._state = _StubState(dist_dir)

    def state(self) -> _StubState:
        return self._state

    def state_payload(self) -> dict[str, object]:
        return {}


def test_preview_handler_serves_current_dist_dir(tmp_path: Path) -> None:
    dist_a = tmp_path / "a"
    dist_b = tmp_path / "b"
    dist_a.mkdir()
    dist_b.mkdir()
    (dist_a / "cv.html").write_text("A")
    (dist_b / "cv.html").write_text("B")

    controller = _StubController(dist_a)
    stop_event = threading.Event()
    handler = _make_handler(
        controller,
        dist_a,
        stop_event,
        client_activity=ClientActivity(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/cv.html"
        content_a = url_request.urlopen(url, timeout=2.0).read().decode("utf-8")
        controller._state = _StubState(dist_b)
        content_b = url_request.urlopen(url, timeout=2.0).read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)

    assert content_a == "A"
    assert content_b == "B"


def test_preview_handler_ignores_client_disconnect_during_static_get(
    monkeypatch, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    controller = _StubController(dist_dir)
    handler_cls = _make_handler(
        controller,
        dist_dir,
        threading.Event(),
        client_activity=ClientActivity(),
    )
    handler = object.__new__(handler_cls)

    def _raise_disconnect(self) -> None:
        raise BrokenPipeError()

    monkeypatch.setattr(SimpleHTTPRequestHandler, "do_GET", _raise_disconnect)

    handler_cls._serve_static(handler)


def test_preview_handler_ignores_client_disconnect_during_response_write(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    controller = _StubController(dist_dir)
    handler_cls = _make_handler(
        controller,
        dist_dir,
        threading.Event(),
        client_activity=ClientActivity(),
    )
    handler = object.__new__(handler_cls)

    class _BrokenWriter:
        def write(self, _data: bytes) -> None:
            raise BrokenPipeError()

    handler.wfile = _BrokenWriter()
    handler.send_response = lambda *_args, **_kwargs: None
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler_cls._write_response(handler, 200, "application/json", b"{}")


class _StubServer:
    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


def test_preview_idle_watchdog_waits_for_first_client_activity() -> None:
    activity = ClientActivity()
    stop_event = threading.Event()
    server = _StubServer()
    watchdog = PreviewIdleWatchdog(
        activity=activity,
        stop_event=stop_event,
        server=server,
        idle_timeout_seconds=0.05,
    )

    watchdog.start()
    time.sleep(0.08)
    stop_event.set()
    watchdog.join(timeout=1.0)

    assert server.shutdown_called is False


def test_preview_idle_watchdog_stops_after_inactivity() -> None:
    activity = ClientActivity()
    activity.touch()
    stop_event = threading.Event()
    server = _StubServer()
    watchdog = PreviewIdleWatchdog(
        activity=activity,
        stop_event=stop_event,
        server=server,
        idle_timeout_seconds=0.05,
    )

    watchdog.start()
    assert stop_event.wait(timeout=1.0)
    watchdog.join(timeout=1.0)

    assert server.shutdown_called is True
