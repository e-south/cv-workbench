"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/doctor.py

Checks runtime dependencies for cv-workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cvworkbench.config import resolve_pdf_engine


@dataclass(frozen=True)
class DependencyCheck:
    name: str
    ok: bool
    version: str | None
    message: str | None


def run_doctor(config_path: Path) -> list[DependencyCheck]:
    pdf_engine = resolve_pdf_engine(config_path) or "xelatex"
    return [
        _check_binary("pandoc", ["pandoc", "--version"]),
        _check_binary(pdf_engine, [pdf_engine, "--version"]),
    ]


def _check_binary(name: str, args: Sequence[str]) -> DependencyCheck:
    try:
        returncode, output = _run_command(args[0], args)
    except FileNotFoundError:
        return DependencyCheck(
            name=name,
            ok=False,
            version=None,
            message=_install_hint(name),
        )

    if returncode != 0:
        return DependencyCheck(
            name=name,
            ok=False,
            version=None,
            message=f"exit code {returncode}",
        )

    version = _first_line(output)
    return DependencyCheck(
        name=name,
        ok=True,
        version=version,
        message=None,
    )


def _run_command(command: str, args: Sequence[str]) -> tuple[int, str]:
    import subprocess

    result = subprocess.run(
        args,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def _first_line(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[0]


def _install_hint(name: str) -> str | None:
    hints = {
        "pandoc": "brew install pandoc",
        "xelatex": "brew install mactex-no-gui",
    }
    return hints.get(name)
