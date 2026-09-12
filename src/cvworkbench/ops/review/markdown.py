"""Convert review inputs to a consistent Markdown syntax without changing claims."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cvworkbench.ops.review import ReviewError


def convert_docx_to_markdown(path: Path) -> str:
    return _convert("docx", [str(path)], None)


def normalize_markdown(text: str) -> str:
    return _convert("markdown+fenced_divs", [], text)


def _convert(reader: str, arguments: list[str], input_text: str | None) -> str:
    executable = shutil.which("pandoc")
    if executable is None:
        raise ReviewError("pandoc is required to convert review documents")
    try:
        options = subprocess.run(
            [executable, "--help"], capture_output=True, text=True, check=False
        )
        if options.returncode != 0:
            raise ReviewError("Pandoc review options could not be inspected")
        if "--markdown-headings" in options.stdout:
            heading_option = "--markdown-headings=atx"
        elif "--atx-headers" in options.stdout:
            heading_option = "--atx-headers"
        else:
            raise ReviewError("Pandoc lacks a supported Markdown heading option")
        result = subprocess.run(
            [
                executable,
                "--from",
                reader,
                "--to",
                "markdown",
                heading_option,
                "--wrap=none",
                *arguments,
            ],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ReviewError("Pandoc review conversion could not start") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ReviewError(message or "Pandoc review conversion failed")
    return result.stdout.strip() + "\n"
