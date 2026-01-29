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


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractResult:
    text: str
    extractor: str
    extractor_version: str | None


def fetch_and_extract(url: str, user_agent: str | None) -> ExtractResult:
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

    html = trafilatura.fetch_url(url, config=config)
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
    )
