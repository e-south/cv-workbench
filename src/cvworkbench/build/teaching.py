"""Render selected teaching records, retaining each offering's identity and evidence."""

from itertools import groupby
from typing import Any

from cvworkbench.build.entry_layout import append_entry_text, entry_metadata
from cvworkbench.text import slugify, tag_classes


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _evidence(item: dict[str, Any], *, grouped: bool = False) -> tuple[str, ...]:
    enrollment = item.get("enrollment")
    evaluation = _text(item.get("evaluation"))
    if grouped:
        return (
            f"{enrollment} students" if isinstance(enrollment, int) else "",
            f"evaluation {evaluation}" if evaluation else "",
        )
    return (
        f"Enrollment: {enrollment}" if isinstance(enrollment, int) else "",
        f"Evaluation: {evaluation}" if evaluation else "",
    )


def _open_entry(lines: list[str], item: dict[str, Any]) -> None:
    classes = ["section"]
    for tag in item.get("tags", []):
        if isinstance(tag, str):
            classes.extend(f"tag-{value}" for value in tag_classes(tag))
    attributes = " ".join(f".{value}" for value in classes)
    lines.append(f"::: {{#teaching-{slugify(item.get('id', ''))} {attributes}}}")


def append_teaching_entries(lines: list[str], selected: list[dict[str, Any]]) -> None:
    """Group only adjacent exact course/role matches after variant selection."""
    for (course, role), entries in groupby(
        selected, key=lambda item: (_text(item.get("course")), _text(item.get("role")))
    ):
        group = list(entries)
        grouped = len(group) > 1 and bool(course and role)
        if grouped:
            lines.extend((":::: {.teaching-course}", f"### {course}", ""))
            append_entry_text(lines, metadata=entry_metadata(role=role))
        for item in group:
            _open_entry(lines, item)
            if course and not grouped:
                lines.append(f"### {course}")
            term = _text(item.get("term"))
            evidence = _evidence(item, grouped=grouped)
            if grouped:
                # Terms remain separate paragraphs and retain their source IDs.
                metadata = (term, *evidence)
            else:
                metadata = entry_metadata(role, *evidence, dates=term)
            append_entry_text(
                lines,
                metadata=metadata,
                paragraphs=(_text(item.get("summary")),),
            )
            lines.extend((":::", ""))
        if grouped:
            lines.extend(("::::", ""))
