"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/packet.py

Renders local review evidence from an already validated public PDF.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import math

import pymupdf

REVIEW_DPI = 96
MAX_REVIEW_PIXELS = 40_000_000
MAX_REVIEW_PAGES = 50


class PublicationReviewError(RuntimeError):
    pass


def publication_review_files(
    pdf_bytes: bytes, *, reading_html: bytes | None = None
) -> dict[str, bytes]:
    """Return a self-contained review packet without private source metadata."""

    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    files = {"cv.pdf": pdf_bytes}
    reading_link = ""
    if reading_html is not None:
        files["reading.html"] = reading_html
        reading_link = ' · <a href="reading.html">Read native HTML</a>'
    pages = []
    figures = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        pixel_count = sum(
            math.ceil(page.rect.width * REVIEW_DPI / 72)
            * math.ceil(page.rect.height * REVIEW_DPI / 72)
            for page in document
        )
        if document.page_count > MAX_REVIEW_PAGES or pixel_count > MAX_REVIEW_PIXELS:
            raise PublicationReviewError("Public PDF exceeds the local visual review size limit")
        for page in document:
            number = page.number + 1
            image_name = f"page-{number:04d}.png"
            pixmap = page.get_pixmap(dpi=REVIEW_DPI, alpha=False)
            files[image_name] = pixmap.tobytes("png")
            words = page.get_text("words")
            bounds = None
            if words:
                bounds = [
                    min(word[0] for word in words),
                    min(word[1] for word in words),
                    max(word[2] for word in words),
                    max(word[3] for word in words),
                ]
            pages.append(
                {
                    "page": number,
                    "image": image_name,
                    "width_points": page.rect.width,
                    "height_points": page.rect.height,
                    "text_bounds_points": bounds,
                    "link_count": len(page.get_links()),
                }
            )
            figures.append(
                f"<figure><figcaption>Page {number}</figcaption>"
                f'<a href="{image_name}"><img src="{image_name}" '
                f'width="{pixmap.width}" height="{pixmap.height}" '
                f'alt="Public CV page {number}"></a></figure>'
            )
    summary = {
        "schema_version": 1,
        "artifact_kind": "publication-review-packet",
        "pdf_sha256": pdf_hash,
        "page_count": len(pages),
        "render_dpi": REVIEW_DPI,
        "pages": pages,
    }
    files["review.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    files["review.html"] = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" href="data:,">'
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>Public CV review</title><style>"
        "body{margin:2rem auto;padding:0 1rem;max-width:52rem;font:16px/1.5 system-ui;"
        "color:#242424;background:#f4f3f0}h1{font-size:1.6rem;margin-bottom:.5rem}"
        "a{color:#174b72}figure{margin:2rem 0}figcaption{margin-bottom:.5rem}"
        "img{display:block;width:100%;height:auto;border:1px solid #bdbbb5;background:white}"
        "code{overflow-wrap:anywhere;font-size:.8rem}</style><main>"
        "<h1>Public CV review</h1><p><strong>Review this PDF.</strong> "
        "Check header alignment, contact spacing, line wraps and page breaks before sync.</p>"
        f'<p><a href="cv.pdf">Open PDF</a> · <a href="review.json">Review measurements</a>{reading_link}</p>'
        "<p>This packet preserves review evidence. Use <code>cvw publication status</code> "
        "in the workbench to check current freshness and recorded review.</p>"
        f"<p>PDF SHA-256: <code>{pdf_hash}</code></p>" + "".join(figures) + "</main></html>\n"
    ).encode()
    return files
