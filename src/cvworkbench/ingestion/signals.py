"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ingestion/signals.py

Builds deterministic signals from context text.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any


def build_signals(text: str, source: dict[str, Any], limit: int = 25) -> dict[str, Any]:
    tokens = _tokenize(text)
    keywords = _keywords(tokens, limit=limit)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "word_count": len(tokens),
        "keywords": keywords,
    }


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def _keywords(tokens: list[str], limit: int) -> list[str]:
    filtered = [token for token in tokens if len(token) >= 3]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(limit)]
