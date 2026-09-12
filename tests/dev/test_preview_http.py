"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_preview_http.py

Exercises preview request boundaries against a real local server and sample build.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import http.client
import shutil
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from cvworkbench.dev.preview import ClientActivity, PreviewController, _make_handler

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def preview_server(tmp_path):
    config_dir = tmp_path / "config"
    shutil.copytree(ROOT / "config", config_dir)
    config = config_dir / "workbench.yaml"
    payload = yaml.safe_load(config.read_text())
    payload["render"]["themes_dir"] = str(ROOT / "build/themes")
    config.write_text(yaml.safe_dump(payload))
    controller = PreviewController(
        sot_base=ROOT / "sot.sample",
        config_path=config,
        variant_id="base",
        theme_id="default",
        style_preset="modern",
        auto_pdf=False,
    )
    controller.build_once()
    stopped = threading.Event()
    handler = _make_handler(
        controller, controller.state().dist_dir, stopped, client_activity=ClientActivity()
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, controller, stopped
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(server, method, path, *, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


@pytest.mark.parametrize(
    "method,path,headers",
    [
        ("GET", "/api/state", {"Host": "untrusted.example"}),
        ("HEAD", "/cv.html", {"Host": "untrusted.example"}),
        ("POST", "/api/render", {"Origin": "https://untrusted.example"}),
        ("POST", "/api/stop", {"Origin": "null"}),
        ("POST", "/api/render", {"Sec-Fetch-Site": "cross-site"}),
    ],
)
def test_preview_rejects_foreign_browser_requests(preview_server, method, path, headers):
    server, controller, stopped = preview_server
    build_id = controller.state_payload()["build_id"]
    status, _, _ = _request(server, method, path, headers=headers, body=b"{}")
    assert status == 403
    assert controller.state_payload()["build_id"] == build_id
    assert not stopped.is_set()


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ({"Content-Length": "-1"}, b"", 400),
        ({"Content-Length": "invalid"}, b"", 400),
        ({"Content-Length": "16385"}, b"", 413),
        ({"Content-Type": "application/json"}, b"\xff", 400),
    ],
)
def test_preview_rejects_malformed_bodies(preview_server, headers, body, status):
    server, controller, _ = preview_server
    build_id = controller.state_payload()["build_id"]
    assert _request(server, "POST", "/api/render", headers=headers, body=body)[0] == status
    assert controller.state_payload()["build_id"] == build_id


def test_preview_rejects_truncated_body_even_when_partial_json_is_valid(preview_server):
    server, controller, _ = preview_server
    before = controller.state_payload()["build_id"]
    with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as connection:
        connection.sendall(
            f"POST /api/render HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
            "Content-Length: 4\r\n\r\n{}".encode()
        )
        connection.shutdown(socket.SHUT_WR)
        response = http.client.HTTPResponse(connection)
        response.begin()
        assert response.status == 400
        response.read()
    assert controller.state_payload()["build_id"] == before


def test_preview_keeps_same_origin_build_and_exact_routes(preview_server):
    server, controller, stopped = preview_server
    headers = {
        "Origin": f"http://127.0.0.1:{server.server_port}",
        "Content-Type": "application/json",
    }
    before = controller.state_payload()["build_id"]
    assert _request(server, "POST", "/api/render", headers=headers, body=b"{}")[0] == 200
    assert controller.state_payload()["build_id"] > before
    assert _request(server, "POST", "/api/stop-unrelated")[0] == 404
    assert not stopped.is_set()
    status, body, response_headers = _request(server, "GET", "/cv.html")
    assert status == 200 and b"<html" in body
    assert _request(server, "GET", "/canonical.md")[0] == 404
    assert _request(server, "GET", "/../input/canonical.md")[0] == 404
    assert _request(server, "GET", "/styles/default-modern.css")[0] == 200
    assert response_headers["X-Content-Type-Options"] == "nosniff"
