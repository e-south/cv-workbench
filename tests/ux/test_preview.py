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


def test_preview_catalog_uses_project_proposal_variant_id(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, html]",
            ]
        )
        + "\n"
    )
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  projects: ../var/projects",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  base_variant: base",
                f"  sot_path: {sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "variant:\n  id: project-focus\n  output_name: cv\n  outputs: [md, pdf, html]\n"
    )
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

    controller = PreviewController(
        sot_base=sot_path,
        config_path=config_path,
        variant_id="base",
        theme_id="default",
        style_preset="modern",
        project_dir=project_dir,
    )

    assert controller.catalog().variants == ["project-focus"]


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
