"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_dev_serve_open.py

Tests preview open behavior for dev serve.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
from cvworkbench.dev.open import OpenMode, OpenResult


def test_open_preview_warning_on_error(capsys) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _fake_open(*_args, **_kwargs) -> OpenResult:
        return OpenResult(opened=False, error="blocked", mode=OpenMode.LAUNCHSERVICES)

    app_module._open_url = _fake_open  # type: ignore[attr-defined]

    result = app_module._open_preview_url("http://localhost:1234", OpenMode.LAUNCHSERVICES, None)

    assert result.opened is False
    assert result.error == "blocked"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "open http://localhost:1234" in captured.err
