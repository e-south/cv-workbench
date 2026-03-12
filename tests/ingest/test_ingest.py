"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ingest/test_ingest.py

Tests URL intake validation behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import ipaddress

import pytest

from cvworkbench.ingestion.ingest import IngestError, validate_public_https_url


def test_validate_public_https_url_accepts_public_https_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvworkbench.ingestion.ingest._resolve_host_ips",
        lambda hostname, port: (ipaddress.ip_address("93.184.216.34"),),
    )

    assert validate_public_https_url("https://example.com/jobs/1") == "https://example.com/jobs/1"


def test_validate_public_https_url_rejects_non_https() -> None:
    with pytest.raises(IngestError, match="https"):
        validate_public_https_url("http://example.com/jobs/1")


def test_validate_public_https_url_rejects_non_default_port() -> None:
    with pytest.raises(IngestError, match="non-default port"):
        validate_public_https_url("https://example.com:8443/jobs/1")


def test_validate_public_https_url_rejects_private_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvworkbench.ingestion.ingest._resolve_host_ips",
        lambda hostname, port: (ipaddress.ip_address("127.0.0.1"),),
    )

    with pytest.raises(IngestError, match="non-public address"):
        validate_public_https_url("https://example.com/jobs/1")
