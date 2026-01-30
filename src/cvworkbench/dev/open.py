"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/open.py

Opens preview URLs using explicit platform-aware strategies.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path


class OpenMode(str, Enum):
    LAUNCHSERVICES = "launchservices"
    APPLESCRIPT = "applescript"
    NONE = "none"


class PreviewViewer(str, Enum):
    BROWSER = "browser"
    QUICKLOOK_PDF = "quicklook-pdf"
    PREVIEW_APP = "preview-app"
    NONE = "none"


@dataclass(frozen=True)
class OpenResult:
    opened: bool
    error: str | None
    mode: OpenMode
    note: str | None = None


def resolve_preview_viewer(requested: PreviewViewer | None) -> PreviewViewer:
    if requested is not None:
        return requested
    env_value = os.environ.get("CVW_PREVIEW_VIEWER")
    if env_value:
        try:
            return PreviewViewer(env_value)
        except ValueError as exc:
            raise ValueError(f"Invalid preview viewer: {env_value}") from exc
    if sys.platform == "darwin":
        return PreviewViewer.PREVIEW_APP
    return PreviewViewer.BROWSER


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
            if ok:
                return OpenResult(opened=True, error=None, mode=mode)
            if not browser and error and _launchservices_missing_handler(error):
                fallback_errors: list[str] = []
                for name, path in _macos_browser_candidates():
                    args = ["/usr/bin/open", "-a", name, url]
                    ok_fallback, error_fallback = _run_command(args)
                    if ok_fallback:
                        return OpenResult(
                            opened=True,
                            error=None,
                            mode=mode,
                            note=(
                                f"Opened with detected browser {name} ({path}) after "
                                "LaunchServices failed to resolve a handler."
                            ),
                        )
                    if error_fallback:
                        fallback_errors.append(f"{name}: {error_fallback}")
                default_bundle = _macos_default_handler_for_scheme("http")
                if default_bundle:
                    ok_fallback, error_fallback = _run_command(
                        _launchservices_bundle_args(url, default_bundle)
                    )
                    if ok_fallback:
                        return OpenResult(
                            opened=True,
                            error=None,
                            mode=mode,
                            note=(
                                f"Opened with fallback bundle {default_bundle} after "
                                "LaunchServices failed to resolve a handler."
                            ),
                        )
                    if error_fallback:
                        fallback_errors.append(f"bundle {default_bundle}: {error_fallback}")
                if fallback_errors:
                    error = f"{error}; fallback failed: {'; '.join(fallback_errors)}"
            if error and "No application knows how to open URL" in error:
                error = (
                    f'{error} (hint: set --browser "Google Chrome" or configure a '
                    "default app for .html files in macOS)"
                )
            return OpenResult(opened=False, error=error, mode=mode)
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


def open_pdf(path: Path) -> OpenResult:
    if sys.platform != "darwin":
        return OpenResult(
            opened=False,
            error="quicklook-pdf viewer is only supported on macOS",
            mode=OpenMode.LAUNCHSERVICES,
        )

    ok, error = _spawn_quicklook(path)
    if ok:
        return OpenResult(
            opened=True,
            error=None,
            mode=OpenMode.LAUNCHSERVICES,
            note="Opened PDF via Quick Look.",
        )

    quicklook_error = error
    ok, error = _run_command(["/usr/bin/open", str(path)])
    if ok:
        note = "Opened PDF via default handler."
        if quicklook_error:
            note = f"{note} Quick Look failed."
        return OpenResult(opened=True, error=None, mode=OpenMode.LAUNCHSERVICES, note=note)
    if error and _launchservices_missing_handler(error):
        fallback_errors: list[str] = []
        for name, app_path in _macos_pdf_viewer_candidates():
            ok_fallback, error_fallback = _run_command(
                ["/usr/bin/open", "-a", name, str(path)]
            )
            if ok_fallback:
                return OpenResult(
                    opened=True,
                    error=None,
                    mode=OpenMode.LAUNCHSERVICES,
                    note=f"Opened PDF with {name}.",
                )
            if error_fallback:
                fallback_errors.append(f"{name}: {error_fallback}")
        for name, app_path in _macos_pdf_viewer_candidates():
            exec_path = _app_executable_path(app_path)
            if exec_path is None:
                continue
            ok_exec, error_exec = _spawn_command([str(exec_path), str(path)])
            if ok_exec:
                return OpenResult(
                    opened=True,
                    error=None,
                    mode=OpenMode.LAUNCHSERVICES,
                    note=f"Opened PDF with {name} executable.",
                )
            if error_exec:
                fallback_errors.append(f"{name} exec: {error_exec}")
        if fallback_errors:
            error = f"{error}; fallback failed: {'; '.join(fallback_errors)}"
    if quicklook_error:
        error = f"Quick Look failed: {quicklook_error}. {error}" if error else quicklook_error
    return OpenResult(opened=False, error=error, mode=OpenMode.LAUNCHSERVICES)


def open_pdf_in_preview(path: Path) -> OpenResult:
    if sys.platform != "darwin":
        return OpenResult(
            opened=False,
            error="preview-app viewer is only supported on macOS",
            mode=OpenMode.LAUNCHSERVICES,
        )

    errors: list[str] = []
    ok, error = _run_command(["/usr/bin/open", "-a", "Preview", str(path)])
    if ok:
        time.sleep(0.2)
        if _preview_process_running():
            return OpenResult(
                opened=True,
                error=None,
                mode=OpenMode.LAUNCHSERVICES,
                note="Opened PDF with Preview.",
            )
        errors.append("Preview did not appear to start")
    elif error:
        errors.append(error)

    preview_app = _preview_app_path()
    if preview_app:
        exec_path = _app_executable_path(preview_app)
        if exec_path:
            ok_exec, error_exec = _spawn_command([str(exec_path), str(path)])
            if ok_exec:
                return OpenResult(
                    opened=True,
                    error=None,
                    mode=OpenMode.LAUNCHSERVICES,
                    note="Opened PDF with Preview executable.",
                )
            if error_exec:
                errors.append(error_exec)
        else:
            errors.append(f"Preview executable not found in {preview_app}")
    else:
        errors.append("Preview.app not found")

    return OpenResult(
        opened=False,
        error="; ".join(errors) if errors else "Preview open failed",
        mode=OpenMode.LAUNCHSERVICES,
    )


def _launchservices_args(url: str, browser: str | None) -> list[str]:
    if browser and browser != "default":
        return ["/usr/bin/open", "-a", browser, url]
    return ["/usr/bin/open", url]


def _launchservices_bundle_args(url: str, bundle_id: str) -> list[str]:
    return ["/usr/bin/open", "-b", bundle_id, url]


@lru_cache(maxsize=1)
def _macos_browser_candidates() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, list[Path]]] = [
        ("Safari", [Path("/System/Applications/Safari.app"), Path("/Applications/Safari.app")]),
        (
            "Google Chrome",
            [
                Path("/Applications/Google Chrome.app"),
                Path.home() / "Applications" / "Google Chrome.app",
            ],
        ),
        (
            "Microsoft Edge",
            [
                Path("/Applications/Microsoft Edge.app"),
                Path.home() / "Applications" / "Microsoft Edge.app",
            ],
        ),
        (
            "Brave Browser",
            [
                Path("/Applications/Brave Browser.app"),
                Path.home() / "Applications" / "Brave Browser.app",
            ],
        ),
        (
            "Firefox",
            [
                Path("/Applications/Firefox.app"),
                Path.home() / "Applications" / "Firefox.app",
            ],
        ),
        (
            "Arc",
            [
                Path("/Applications/Arc.app"),
                Path.home() / "Applications" / "Arc.app",
            ],
        ),
    ]
    available: list[tuple[str, Path]] = []
    for name, paths in candidates:
        for path in paths:
            if path.exists():
                available.append((name, path))
    return available


@lru_cache(maxsize=1)
def _macos_pdf_viewer_candidates() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, list[Path]]] = [
        ("Preview", [Path("/System/Applications/Preview.app"), Path("/Applications/Preview.app")]),
        ("Skim", [Path("/Applications/Skim.app"), Path.home() / "Applications" / "Skim.app"]),
        (
            "Adobe Acrobat Reader",
            [
                Path("/Applications/Adobe Acrobat Reader.app"),
                Path.home() / "Applications" / "Adobe Acrobat Reader.app",
            ],
        ),
        (
            "Adobe Acrobat",
            [
                Path("/Applications/Adobe Acrobat.app"),
                Path.home() / "Applications" / "Adobe Acrobat.app",
            ],
        ),
        (
            "PDF Expert",
            [
                Path("/Applications/PDF Expert.app"),
                Path.home() / "Applications" / "PDF Expert.app",
            ],
        ),
    ]
    available: list[tuple[str, Path]] = []
    for name, paths in candidates:
        for path in paths:
            if path.exists():
                available.append((name, path))
    return available


def _launchservices_missing_handler(message: str) -> bool:
    lowered = message.lower()
    return (
        "no application knows how to open url" in lowered
        or "klsnoexecutabler" in lowered
        or "klsnoexecutableerr" in lowered
        or "klsexecutableincorrectformat" in lowered
    )


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


@lru_cache(maxsize=16)
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


@lru_cache(maxsize=16)
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


@lru_cache(maxsize=32)
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


@lru_cache(maxsize=32)
def _app_executable_path(app_path: Path) -> Path | None:
    info_path = app_path / "Contents" / "Info.plist"
    if not info_path.exists():
        return None
    try:
        with info_path.open("rb") as handle:
            import plistlib

            payload = plistlib.load(handle)
    except Exception:
        return None
    executable = payload.get("CFBundleExecutable")
    if not isinstance(executable, str) or not executable.strip():
        return None
    exec_path = app_path / "Contents" / "MacOS" / executable
    if exec_path.exists() and os.access(exec_path, os.X_OK):
        return exec_path
    return None


def _run_command(args: list[str]) -> tuple[bool, str | None]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return False, message or "Browser open failed"
    return True, None


def _spawn_command(args: list[str]) -> tuple[bool, str | None]:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc)
    return True, None


def _spawn_quicklook(path: Path) -> tuple[bool, str | None]:
    try:
        proc = subprocess.Popen(
            ["/usr/bin/qlmanage", "-p", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc)

    try:
        stdout, stderr = proc.communicate(timeout=1.5)
    except subprocess.TimeoutExpired:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        return True, None

    message = (stderr or stdout or "").strip()
    return False, message or "Quick Look exited unexpectedly"


def _preview_process_running() -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-x", "Preview"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _preview_app_path() -> Path | None:
    candidates = [Path("/System/Applications/Preview.app"), Path("/Applications/Preview.app")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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
    if (
        "(-1728)" in lowered
        or "can't get application" in lowered
        or "cant get application" in lowered
    ):
        return (
            f'Browser automation failed for "{app_name}". Check Automation permissions '
            "and retry, or use --open-mode launchservices."
        )
    return message
