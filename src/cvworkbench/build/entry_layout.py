"""Compose record metadata and narrative as distinct Markdown paragraphs."""

from __future__ import annotations

from collections.abc import Sequence


def entry_metadata(
    *details: str, role: str = "", issuer: str = "", location: str = "", dates: str = ""
) -> tuple[str, ...]:
    """Keep metadata roles through Pandoc without embedding format-specific spacing."""
    parts = [(role, "role"), *((value, "detail") for value in details)]
    parts.extend(((issuer, "issuer"), (location, "location"), (dates, "date")))
    return tuple(f"[{value}]{{.entry-{kind}}}" for value, kind in parts if value)


def append_entry_text(
    lines: list[str],
    *,
    metadata: Sequence[str] = (),
    paragraphs: Sequence[str] = (),
) -> None:
    """Emit one compact metadata row, followed by each nonempty prose block."""
    blocks = (" | ".join(value for value in metadata if value), *paragraphs)
    for block in blocks:
        if not block:
            continue
        if lines and lines[-1]:
            lines.append("")
        lines.extend((block, ""))
