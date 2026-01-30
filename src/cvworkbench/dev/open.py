"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/open.py

Opens preview URLs using explicit platform-aware strategies.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any


class OpenMode(str, Enum):
    LAUNCHSERVICES = "launchservices"
    APPLESCRIPT = "applescript"
    NONE = "none"


@dataclass(frozen=True)
class OpenResult:
    opened: bool
    error: str | None
    mode: OpenMode


def resolve_open_mode(requested: OpenMode | None) -> OpenMode:
    if os.environ.get("CVW_SKIP_OPEN") == "1":
        return OpenMode.NONE
    if requested is not None:
        return requested
    return OpenMode.LAUNCHSERVICES


def open_url(url: str, *, mode: OpenMode, browser: str | None) -> OpenResult:
    if mode == OpenMode.NONE:
        return OpenResult(opened=False, error=None, mode=mode)

    if sys.platform == "darwin":
        if mode == OpenMode.LAUNCHSERVICES:
            args = _launchservices_args(url, browser)
            ok, error = _run_command(args)
            return OpenResult(opened=ok, error=error, mode=mode)
        if mode == OpenMode.APPLESCRIPT:
            app_name = browser
            if not app_name or app_name == "default":
                app_name = _resolve_default_browser_name("http")
                if not app_name:
                    return OpenResult(
                        opened=False,
                        error="Default web browser could not be resolved",
                        mode=mode,
                    )
            args = _applescript_args(app_name, url)
            ok, error = _run_command(args)
            if error:
                error = _format_applescript_error(app_name, error)
            return OpenResult(opened=ok, error=error, mode=mode)
        return OpenResult(opened=False, error=f"Unsupported open mode: {mode}", mode=mode)

    if mode == OpenMode.APPLESCRIPT:
        return OpenResult(opened=False, error="AppleScript open is macOS-only", mode=mode)

    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
        except OSError as exc:
            return OpenResult(opened=False, error=str(exc), mode=mode)
        return OpenResult(opened=True, error=None, mode=mode)

    if browser:
        args = shlex.split(browser)
        if not args:
            return OpenResult(opened=False, error="Browser command is empty", mode=mode)
        ok, error = _run_command([*args, url])
        return OpenResult(opened=ok, error=error, mode=mode)

    ok, error = _run_command(["xdg-open", url])
    return OpenResult(opened=ok, error=error, mode=mode)


def _launchservices_args(url: str, browser: str | None) -> list[str]:
    if browser and browser != "default":
        return ["/usr/bin/open", "-a", browser, url]
    return ["/usr/bin/open", url]


def _applescript_args(app_name: str, url: str) -> list[str]:
    escaped_name = app_name.replace('"', '\\"')
    escaped_target = url.replace('"', '\\"')
    script = f'tell application "{escaped_name}" to open location "{escaped_target}"'
    return ["/usr/bin/osascript", "-e", script]


def _resolve_default_browser_name(scheme: str) -> str | None:
    handler = _macos_default_handler_for_scheme(scheme)
    if not handler:
        return None
    app_path = _macos_browser_app_path(handler)
    if not app_path:
        return None
    return _macos_browser_app_name(app_path)


def _macos_default_handler_for_scheme(scheme: str) -> str | None:
    if not scheme.strip():
        raise ValueError("Scheme is required")

    override = os.environ.get("CVW_LAUNCHSERVICES_PLIST")
    plist_path = (
        Path(override)
        if override
        else Path.home()
        / "Library"
        / "Preferences"
        / "com.apple.LaunchServices"
        / "com.apple.launchservices.secure.plist"
    )
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as handle:
            import plistlib

            payload = plistlib.load(handle)
    except Exception as exc:
        raise OSError(f"Failed to read LaunchServices plist: {exc}") from exc
    handlers = payload.get("LSHandlers", [])
    if not isinstance(handlers, list):
        return None
    for entry in handlers:
        if not isinstance(entry, dict):
            continue
        if entry.get("LSHandlerURLScheme") != scheme:
            continue
        bundle_id = entry.get("LSHandlerRoleAll")
        if isinstance(bundle_id, str) and bundle_id.strip():
            return bundle_id
    return None


def _macos_browser_app_path(bundle_id: str) -> Path | None:
    if not bundle_id.strip():
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/mdfind", f"kMDItemCFBundleIdentifier == '{bundle_id}'"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise OSError(f"Failed to resolve default web browser: {exc}") from exc
    if result.returncode != 0:
        return None
    paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    if not paths:
        return None
    return paths[0]


def _macos_browser_app_name(app_path: Path) -> str | None:
    info_path = app_path / "Contents" / "Info.plist"
    if not info_path.exists():
        return None
    try:
        with info_path.open("rb") as handle:
            import plistlib

            payload = plistlib.load(handle)
    except Exception:
        return None
    name = payload.get("CFBundleDisplayName") or payload.get("CFBundleName")
    if isinstance(name, str) and name.strip():
        return name
    return None


def _run_command(args: list[str]) -> tuple[bool, str | None]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return False, message or "Browser open failed"
    return True, None


def _format_applescript_error(app_name: str, message: str) -> str:
    if not message:
        return "Browser open failed"
    lowered = message.lower()
    if "(-1743)" in lowered or "not authorized" in lowered:
        return (
            f'Browser automation blocked for "{app_name}". Allow your terminal app '
            "under System Settings > Privacy & Security > Automation. "
            "You can also use --open-mode launchservices. "
            'Open settings: open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"'
        )
    if "(-1728)" in lowered or "can't get application" in lowered or "cant get application" in lowered:
        return (
            f'Browser automation failed for "{app_name}". Check Automation permissions '
            "and retry, or use --open-mode launchservices."
        )
    return message
