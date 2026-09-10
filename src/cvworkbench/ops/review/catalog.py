"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/catalog.py

Discovers content review packs and public PDF review packets.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path
from typing import TypedDict

from cvworkbench.config import resolve_reviews_path


class ReviewSummary(TypedDict):
    review_id: str
    kind: str
    path: str
    docx: str | None
    pdf: str | None
    review: str | None
    missing_files: list[str]


def list_review_summaries(config_path: Path) -> list[ReviewSummary]:
    root = resolve_reviews_path(config_path)
    directories = sorted(
        {
            path.parent
            for pattern in ("review.md", "cv.docx", "cv.pdf", "publication/*/review.html")
            for path in root.glob(f"**/{pattern}" if "/" not in pattern else pattern)
            if path.is_file()
        }
    )
    summaries: list[ReviewSummary] = []
    for directory in directories:
        relative = directory.relative_to(root)
        is_publication = relative.parts[0] == "publication" if relative.parts else False
        review = directory / ("review.html" if is_publication else "review.md")
        required = (
            ("cv.pdf", "review.json", "review.html")
            if is_publication
            else ("cv.pdf", "cv.docx", "review.md")
        )
        summaries.append(
            {
                "review_id": relative.as_posix(),
                "kind": "publication" if is_publication else "content",
                "path": str(directory),
                "docx": str(directory / "cv.docx") if (directory / "cv.docx").is_file() else None,
                "pdf": str(directory / "cv.pdf") if (directory / "cv.pdf").is_file() else None,
                "review": str(review) if review.is_file() else None,
                "missing_files": [name for name in required if not (directory / name).is_file()],
            }
        )
    return summaries
