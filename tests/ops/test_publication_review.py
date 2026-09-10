"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_publication_review.py

Checks resource bounds and blank-page evidence in public CV reviews.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json

import pymupdf
import pytest

from cvworkbench.ops.publication_review import PublicationReviewError, publication_review_files


@pytest.mark.parametrize("page_count,dimension", [(51, 72), (1, 10000)])
def test_review_rejects_excessive_render_work(page_count, dimension):
    with pymupdf.open() as document:
        for _ in range(page_count):
            document.new_page(width=dimension, height=dimension)
        pdf = document.tobytes()
    with pytest.raises(PublicationReviewError, match="review size limit"):
        publication_review_files(pdf)


def test_review_preserves_and_identifies_blank_pages():
    with pymupdf.open() as document:
        document.new_page()
        pdf = document.tobytes()
    files = publication_review_files(pdf)
    review = json.loads(files["review.json"])
    assert review["page_count"] == 1
    assert review["pages"][0]["text_bounds_points"] is None
    assert files["page-0001.png"].startswith(b"\x89PNG\r\n\x1a\n")
    assert files["cv.pdf"] == pdf
