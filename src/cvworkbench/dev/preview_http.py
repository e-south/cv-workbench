"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/preview_http.py

Defines the loopback preview HTTP request boundary.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from http.client import HTTPMessage

MAX_RENDER_BODY_BYTES = 16_384
REQUEST_TIMEOUT_SECONDS = 10


class PreviewRequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def validate_request_origin(headers: HTTPMessage, port: int) -> None:
    hosts = headers.get_all("Host", [])
    allowed = {f"{host}:{port}" for host in ("localhost", "127.0.0.1", "[::1]")}
    if len(hosts) != 1 or hosts[0] not in allowed:
        raise PreviewRequestError("Preview requests require the local server Host", 403)
    origins = headers.get_all("Origin", [])
    if origins and origins != [f"http://{hosts[0]}"]:
        raise PreviewRequestError("Preview requests require the same origin", 403)
    if headers.get("Sec-Fetch-Site") == "cross-site":
        raise PreviewRequestError("Cross-site preview requests are not allowed", 403)


def render_body_length(headers: HTTPMessage) -> int:
    values = headers.get_all("Content-Length", [])
    if headers.get("Transfer-Encoding") or len(values) > 1:
        raise PreviewRequestError("Preview requests require a single Content-Length")
    value = values[0] if values else "0"
    if not value.isascii() or not value.isdecimal():
        raise PreviewRequestError("Content-Length must be a non-negative integer")
    if len(value) > 5 or int(value) > MAX_RENDER_BODY_BYTES:
        raise PreviewRequestError("Preview request body exceeds 16384 bytes", 413)
    return int(value)
