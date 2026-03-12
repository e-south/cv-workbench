"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ingestion/ingest.py

Fetches and extracts text from URLs for context ingestion.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlsplit


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractResult:
    text: str
    extractor: str
    extractor_version: str | None
    raw_html: str | None = None


def validate_public_https_url(url: str) -> str:
    candidate = url.strip()
    if not candidate:
        raise IngestError("URL is required")

    parts = urlsplit(candidate)
    if parts.scheme != "https":
        raise IngestError("URL must use https")
    if parts.username or parts.password:
        raise IngestError("URL must not include embedded credentials")
    if not parts.hostname:
        raise IngestError("URL must include a hostname")
    try:
        port = parts.port
    except ValueError as exc:
        raise IngestError("URL port is invalid") from exc
    if port not in (None, 443):
        raise IngestError("URL must not use a non-default port")

    addresses = _resolve_host_ips(parts.hostname, port or 443)
    if not addresses:
        raise IngestError("URL host did not resolve to any addresses")
    for address in addresses:
        if not address.is_global:
            raise IngestError(
                f"URL host resolves to a non-public address: {parts.hostname}"
            )
    return candidate


def _resolve_host_ips(hostname: str, port: int) -> tuple[ipaddress._BaseAddress, ...]:
    try:
        addrinfo = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise IngestError(f"URL host could not be resolved: {hostname}") from exc

    resolved: list[ipaddress._BaseAddress] = []
    seen: set[str] = set()
    for family, _, _, _, sockaddr in addrinfo:
        if family == socket.AF_INET:
            host = sockaddr[0]
        elif family == socket.AF_INET6:
            host = sockaddr[0]
        else:
            continue
        if host in seen:
            continue
        seen.add(host)
        try:
            resolved.append(ipaddress.ip_address(host))
        except ValueError as exc:
            raise IngestError(f"URL host resolved to an invalid address: {host}") from exc
    return tuple(resolved)


def fetch_and_extract(url: str, user_agent: str | None) -> ExtractResult:
    validated_url = validate_public_https_url(url)
    try:
        import copy

        import trafilatura
        import trafilatura.settings as settings
    except ImportError as exc:
        raise IngestError("trafilatura is required for URL ingestion") from exc

    config = settings.DEFAULT_CONFIG
    if user_agent:
        config = copy.deepcopy(settings.DEFAULT_CONFIG)
        config["DEFAULT"]["USER_AGENTS"] = user_agent

    html = trafilatura.fetch_url(validated_url, config=config)
    if not html:
        raise IngestError("Failed to fetch URL content")

    text = trafilatura.extract(html, output_format="markdown")
    if not text or not text.strip():
        raise IngestError("Extracted text was empty")

    version = getattr(trafilatura, "__version__", None)
    return ExtractResult(
        text=text.strip(),
        extractor="trafilatura",
        extractor_version=version,
        raw_html=html,
    )
