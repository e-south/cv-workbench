"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ingestion/registry.py

Manages local context registry entries for ingested sources.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from cvworkbench.config import load_config, resolve_registry_path
from cvworkbench.ingestion.ingest import ExtractResult, IngestError, fetch_and_extract
from cvworkbench.ingestion.signals import build_signals
from cvworkbench.ingestion.strategy import build_strategy


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegistrySettings:
    root: Path
    user_agent: str | None


@dataclass(frozen=True)
class RegistryEntry:
    context_id: str
    path: Path
    source_path: Path
    extracted_path: Path
    signals_path: Path
    strategy_path: Path


def context_id_from_url(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"context-{digest[:8]}"


def load_registry_settings(config_path: Path) -> RegistrySettings:
    root = resolve_registry_path(config_path)
    config = load_config(config_path)
    registry = config.get("registry", {})
    if registry is not None and not isinstance(registry, dict):
        raise RegistryError("Config field registry must be a mapping")
    user_agent = "cv-workbench/0.1"
    if isinstance(registry, dict):
        value = registry.get("user_agent")
        if value is not None and not isinstance(value, str):
            raise RegistryError("Config field registry.user_agent must be a string")
        if value is not None:
            user_agent = value
    return RegistrySettings(root=root, user_agent=user_agent)


def add_url_context(url: str, config_path: Path) -> RegistryEntry:
    settings = load_registry_settings(config_path)
    context_id = context_id_from_url(url)
    context_dir = settings.root / "contexts" / context_id
    if context_dir.exists():
        raise RegistryError(f"Context already exists: {context_dir}")

    extract = _extract_url(url, settings.user_agent)
    context_dir.mkdir(parents=True, exist_ok=False)

    source_path = context_dir / "source.json"
    extracted_path = context_dir / "extracted.md"
    signals_path = context_dir / "signals.json"
    strategy_path = context_dir / "strategy.yaml"

    _write_source(source_path, url, extract)
    extracted_path.write_text(extract.text.strip() + "\n")

    signals = build_signals(
        extract.text,
        {
            "url": url,
            "retrieved_at": _now_iso(),
        },
    )
    signals_path.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n")

    strategy = build_strategy(context_id, signals)
    strategy_path.write_text(yaml.safe_dump(strategy, sort_keys=False))

    return RegistryEntry(
        context_id=context_id,
        path=context_dir,
        source_path=source_path,
        extracted_path=extracted_path,
        signals_path=signals_path,
        strategy_path=strategy_path,
    )


def _extract_url(url: str, user_agent: str | None) -> ExtractResult:
    try:
        return fetch_and_extract(url, user_agent)
    except IngestError as exc:
        raise RegistryError(str(exc)) from exc


def _write_source(path: Path, url: str, extract: ExtractResult) -> None:
    payload = {
        "url": url,
        "retrieved_at": _now_iso(),
        "extractor": extract.extractor,
        "extractor_version": extract.extractor_version,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
