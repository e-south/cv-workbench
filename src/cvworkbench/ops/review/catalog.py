"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/catalog.py

Discovers content review packs and public PDF review packets.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path
from typing import Literal, TypedDict

from cvworkbench.config import ConfigSource, resolve_reviews_path
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.record import (
    SOURCE_RECORD_NAME,
    ReviewSource,
    SourceArtifactError,
    load_source_record,
    validate_source_artifacts,
)


class ReviewSourceSummary(TypedDict):
    state: Literal["untracked", "ready", "missing", "changed", "invalid"]
    record: str
    run_id: str | None
    run_path: str | None
    docx_name: str | None
    pdf_name: str | None
    issues: list[str]


class ReviewSummary(TypedDict):
    review_id: str
    kind: str
    path: str
    docx: str | None
    pdf: str | None
    review: str | None
    missing_files: list[str]
    source: ReviewSourceSummary | None


def load_review_sources(config_path: ConfigSource) -> dict[Path, ReviewSource]:
    root = resolve_reviews_path(config_path)
    return {
        path.parent: load_source_record(path) for path in sorted(root.rglob(SOURCE_RECORD_NAME))
    }


def inspect_review_source(directory: Path) -> ReviewSourceSummary:
    path = directory / SOURCE_RECORD_NAME
    result: ReviewSourceSummary = {
        "state": "untracked",
        "record": str(path),
        "run_id": None,
        "run_path": None,
        "docx_name": None,
        "pdf_name": None,
        "issues": [],
    }
    if not path.exists():
        result["issues"] = ["No review source record; import requires an explicit --run."]
        return result
    try:
        source = load_source_record(path)
        result.update(
            run_id=source.run_id,
            run_path=source.run_path,
            docx_name=source.docx_name,
            pdf_name=source.pdf_name,
        )
        validate_source_artifacts(source)
    except SourceArtifactError as exc:
        result.update(state=exc.state, issues=[str(exc)])
    except (ReviewError, OSError) as exc:
        result.update(state="invalid", issues=[str(exc)])
    else:
        result["state"] = "ready"
    return result


def list_review_summaries(config_path: ConfigSource) -> list[ReviewSummary]:
    root = resolve_reviews_path(config_path)
    directories = sorted(
        {
            path.parent
            for pattern in (
                "review.md",
                "cv.docx",
                "cv.pdf",
                SOURCE_RECORD_NAME,
                "publication/*/review.html",
            )
            for path in root.glob(f"**/{pattern}" if "/" not in pattern else pattern)
            if path.is_file()
        }
    )
    summaries: list[ReviewSummary] = []
    for directory in directories:
        relative = directory.relative_to(root)
        is_publication = relative.parts[0] == "publication" if relative.parts else False
        source = None if is_publication else inspect_review_source(directory)
        docx_name = source["docx_name"] if source and source["docx_name"] else "cv.docx"
        pdf_name = source["pdf_name"] if source and source["pdf_name"] else "cv.pdf"
        review = directory / ("review.html" if is_publication else "review.md")
        required = (
            ("cv.pdf", "review.json", "review.html")
            if is_publication
            else (pdf_name, docx_name, "review.md")
        )
        summaries.append(
            {
                "review_id": relative.as_posix(),
                "kind": "publication" if is_publication else "content",
                "path": str(directory),
                "docx": str(directory / docx_name) if (directory / docx_name).is_file() else None,
                "pdf": str(directory / pdf_name) if (directory / pdf_name).is_file() else None,
                "review": str(review) if review.is_file() else None,
                "missing_files": [name for name in required if not (directory / name).is_file()],
                "source": source,
            }
        )
    return summaries
