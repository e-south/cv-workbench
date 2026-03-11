"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_preview_session.py

Tests preview session parsing for fail-fast behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvworkbench.dev.preview import (
    PreviewError,
    _parse_render_payload,
    load_preview_session,
    preview_session_path,
)


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  runs: ../var/runs\n")
    return config_path


def test_load_preview_session_requires_fields(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    session_path = preview_session_path(config_path)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "pid": 123,
                "host": "127.0.0.1",
                "port": 8765,
                "url": "http://127.0.0.1:8765/",
            }
        )
    )

    with pytest.raises(PreviewError, match="Preview session file is invalid"):
        load_preview_session(config_path)


def test_load_preview_session_accepts_null_style_preset(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    session_path = preview_session_path(config_path)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "pid": 123,
                "host": "127.0.0.1",
                "port": 8765,
                "url": "http://127.0.0.1:8765/",
                "variant": "base",
                "theme": "default",
                "style_preset": None,
                "started_at": "2026-01-31T00:00:00+00:00",
            }
        )
    )

    session = load_preview_session(config_path)

    assert session.variant_id == "base"
    assert session.style_preset is None


def test_parse_render_payload_requires_json_object() -> None:
    with pytest.raises(PreviewError, match="JSON object"):
        _parse_render_payload('["base"]')


def test_parse_render_payload_rejects_invalid_json() -> None:
    with pytest.raises(PreviewError, match="Invalid JSON"):
        _parse_render_payload("{")


def test_parse_render_payload_rejects_non_boolean_auto_pdf() -> None:
    with pytest.raises(PreviewError, match="auto_pdf must be a boolean"):
        _parse_render_payload('{"auto_pdf": "yes"}')


def test_parse_render_payload_accepts_valid_body() -> None:
    payload = _parse_render_payload('{"variant": "base", "auto_pdf": true}')

    assert payload == {"variant": "base", "auto_pdf": True}
