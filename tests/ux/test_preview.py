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
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request

from cvworkbench.dev.preview import PreviewController, _make_handler, _preview_page_html


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


def test_preview_page_html_contains_controls() -> None:
    html = _preview_page_html()

    assert 'id="sidebar"' in html
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
    handler = _make_handler(controller, dist_a, stop_event)
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
