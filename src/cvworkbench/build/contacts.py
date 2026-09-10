"""Format selected contact facts as literal labels and explicit document links."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

_MARKDOWN_PUNCTUATION = frozenset("\\`*_{}[]<>!|#$~^&")


def build_contact_line(person: dict[str, Any], contact_fields: list[str]) -> str:
    parts: list[str] = []
    label = person.get("label")
    if "label" in contact_fields and isinstance(label, str) and label.strip():
        parts.append(_literal(label))

    email = person.get("email")
    if "email" in contact_fields and isinstance(email, str) and email.strip():
        parts.append(_link(email, _email_destination(email.strip())))

    phone = person.get("phone")
    if "phone" in contact_fields and isinstance(phone, str) and phone.strip():
        parts.append(_literal(phone))

    location = person.get("location")
    if "location" in contact_fields and isinstance(location, dict):
        bits = [location.get(key) for key in ("city", "region", "country")]
        values = [value.strip() for value in bits if isinstance(value, str) and value.strip()]
        if values:
            parts.append(_literal(", ".join(values)))

    links = person.get("links")
    if "links" in contact_fields and isinstance(links, list):
        for index, link in enumerate(links, start=1):
            if not isinstance(link, dict):
                continue
            label_text, url = link.get("label"), link.get("url")
            if isinstance(label_text, str) and isinstance(url, str):
                if not label_text.strip():
                    raise ValueError(f"Contact profile {index} requires a visible label")
                parts.append(_link(label_text, _profile_destination(url.strip(), index)))

    return " | ".join(parts)


def _literal(value: str) -> str:
    return "".join(
        f"\\{char}" if char in _MARKDOWN_PUNCTUATION else char for char in " ".join(value.split())
    )


def _link(label: str, destination: str) -> str:
    return f"[{_literal(label)}](<{destination}>)"


def _has_uri_whitespace(value: str) -> bool:
    return any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)


def _email_destination(address: str) -> str:
    local, separator, domain = address.rpartition("@")
    if (
        not separator
        or not local
        or not domain
        or "@" in local
        or _has_uri_whitespace(address)
        or any(char in local for char in '\\<>[]():;,"')
        or any(char in domain for char in '/?#\\<>[]():;,"%&=')
    ):
        raise ValueError("Contact email requires a bare address without URI headers or whitespace")
    return "mailto:" + quote(address, safe="@.-_~")


def _profile_destination(url: str, index: int) -> str:
    message = f"Contact profile {index} requires an absolute HTTP(S) URL without credentials or whitespace"
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not _has_uri_whitespace(url)
            and "\\" not in url
        )
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(message) from exc
    if not valid:
        raise ValueError(message)
    return quote(url, safe=":/?#[]@!$&'()*+,;=%-._~")
