"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/links.py

Builds literal text links with validated public web destinations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from collections.abc import Sequence
from urllib.parse import quote, urlsplit

from cvworkbench.text import title_italic_spans

_MARKDOWN_PUNCTUATION = frozenset("\\`*_{}[]<>!|#$~^&")


def literal_text(value: str) -> str:
    return "".join(
        f"\\{char}" if char in _MARKDOWN_PUNCTUATION else char for char in " ".join(value.split())
    )


def title_text(value: str, italics: Sequence[str] = ()) -> str:
    spans = title_italic_spans(value, italics)

    def escape(part: str) -> str:
        return "".join(f"\\{char}" if char in _MARKDOWN_PUNCTUATION else char for char in part)

    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.extend((escape(value[cursor:start]), f"*{escape(value[start:end])}*"))
        cursor = end
    parts.append(escape(value[cursor:]))
    return " ".join("".join(parts).split())


def has_uri_whitespace(value: str) -> bool:
    return any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)


def http_link(label: str, url: str, *, field: str, italics: Sequence[str] = ()) -> str:
    message = f"{field} requires an absolute HTTP(S) URL without credentials or whitespace"
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not has_uri_whitespace(url)
            and "\\" not in url
        )
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(message) from exc
    if not valid:
        raise ValueError(message)
    destination = quote(url, safe=":/?#[]@!$&'()*+,;=%-._~")
    return f"[{title_text(label, italics)}](<{destination}>)"
