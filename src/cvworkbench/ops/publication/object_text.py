"""Decode non-page PDF strings for the publication disclosure checks."""

from __future__ import annotations

import pymupdf
from pymupdf import mupdf


class PdfObjectTextError(RuntimeError):
    pass


def pdf_object_text(document: pymupdf.Document) -> str:
    """Read object strings, including nested and indirect metadata values.

    MuPDF owns PDF parsing and string decoding. Every cross-reference object is
    visited once; indirect edges are not followed, avoiding cycles through page
    parents and structure trees. Stream bytes are outside this inspection.
    """
    strings: list[str] = []
    try:
        pdf = mupdf.pdf_document_from_fz_document(document.this)
        for xref in range(1, document.xref_length()):
            pending = [mupdf.pdf_load_object(pdf, xref)]
            while pending:
                value = pending.pop()
                if mupdf.pdf_is_indirect(value):
                    continue
                if mupdf.pdf_is_string(value):
                    strings.append(mupdf.pdf_to_text_string(value))
                elif mupdf.pdf_is_array(value):
                    pending.extend(
                        mupdf.pdf_array_get(value, index)
                        for index in reversed(range(mupdf.pdf_array_len(value)))
                    )
                elif mupdf.pdf_is_dict(value):
                    pending.extend(
                        mupdf.pdf_dict_get_val(value, index)
                        for index in reversed(range(mupdf.pdf_dict_len(value)))
                    )
    except (mupdf.FzErrorBase, RuntimeError, ValueError) as exc:
        raise PdfObjectTextError("Public PDF object text could not be inspected") from exc
    return "\n".join(strings)
