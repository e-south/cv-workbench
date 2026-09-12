"""Sanitize completed native HTML without repeating its layout projection."""

import html
import re
from html.parser import HTMLParser

from cvworkbench.ops.publication.pdf import PublicPdfError, _safe_public_uri, validate_public_text

TAGS = frozenset(
    "h1 h2 h3 h4 h5 h6 p div section span a em strong ul ol li sup sub br hr code blockquote".split()
)


class ReadingParser(HTMLParser):
    def __init__(self, allowed_links):
        super().__init__(convert_charrefs=True)
        self.allowed_links = allowed_links
        self.parts = []
        self.text = []
        self.stack = []
        self.in_head = False
        self.in_style = False
        self.styles = []

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
            return
        if tag in {"html", "body"}:
            return
        if self.in_head and tag in {"title", "meta", "link", "style"}:
            self.in_style = tag == "style"
            return
        if tag not in TAGS:
            raise PublicPdfError("Public HTML contains unsupported active or embedded content")
        attributes = dict(attrs)
        safe = ""
        if tag == "a":
            href = attributes.get("href")
            if href not in self.allowed_links:
                raise PublicPdfError("Public HTML link is not declared by its native build")
            safe += f' href="{html.escape(href, quote=True)}"'
        classes = (attributes.get("class") or "").split()
        if re.search(
            r"(?:^|;)\s*break-before\s*:\s*page\s*(?:;|$)", attributes.get("style") or "", re.I
        ):
            if "cv-page-break-before" not in classes:
                classes.append("cv-page-break-before")
        if any(not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,80}", item) for item in classes):
            raise PublicPdfError("Public HTML contains an invalid layout class")
        if classes:
            safe += f' class="{" ".join(classes)}"'
        self.parts.append(f"<{tag}{safe}>")
        if tag not in {"br", "hr"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"br", "hr", "meta", "link"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
            return
        if tag in {"html", "body"}:
            return
        if self.in_head:
            if tag == "style":
                self.in_style = False
            return
        if not self.stack or self.stack[-1] != tag:
            raise PublicPdfError("Public HTML structure is unbalanced")
        self.parts.append(f"</{self.stack.pop()}>")
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text.append("\n")

    def handle_data(self, data):
        if self.in_head:
            if self.in_style:
                self.styles.append(data)
            return
        self.parts.append(html.escape(data))
        self.text.append(data)


def build_reading_html(
    rendered_html: bytes, *, stylesheet=b"", allowed_links, person, variant, publish
) -> bytes:
    """Keep native layout classes and theme CSS; never re-render Markdown here."""
    if any(not _safe_public_uri(link, person, variant, allow_email=True) for link in allowed_links):
        raise PublicPdfError("Public HTML contains an unsafe declared link")
    parser = ReadingParser(allowed_links)
    parser.feed(rendered_html.decode("utf-8"))
    parser.close()
    if parser.stack or parser.in_head:
        raise PublicPdfError("Public HTML structure is incomplete")
    css = "\n".join(parser.styles) + "\n" + stylesheet.decode("utf-8")
    css += "\n.cv-page-break-before{break-before:page}\n"
    if re.search(r"[<\\]|url\s*\(|expression\s*\(|@(?:import|font-face|namespace)", css, re.I):
        raise PublicPdfError("Public HTML stylesheet must be passive and self-contained")
    for value in ("".join(parser.text), css):
        validate_public_text(
            value, person=person, variant=variant, publish=publish, label="Public HTML"
        )
        if re.search(r"/Users/|/home/|file://|localhost|127\.0\.0\.1", value, re.I):
            raise PublicPdfError("Public HTML contains a local path or origin")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Curriculum vitae</title><style>"
        + css
        + "</style></head><body>\n"
        + "".join(parser.parts)
        + "\n</body></html>\n"
    ).encode()
