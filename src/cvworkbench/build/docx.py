"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/docx.py

Checks generated DOCX package structure before artifact replacement.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


def validate_docx(path: Path) -> None:
    """Require core document parts and well-formed XML, without claiming layout fidelity."""
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if not {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= names:
                raise ValueError("Rendered DOCX is missing required document parts")
            for name in sorted(names):
                if name.endswith((".xml", ".rels")):
                    ElementTree.fromstring(archive.read(name))
    except (BadZipFile, ElementTree.ParseError, OSError) as error:
        raise ValueError("Rendered DOCX contains an invalid archive or malformed XML") from error
