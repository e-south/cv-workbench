"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/markdown.py

Materializes canonical markdown from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

from cvworkbench.variants import Variant


def build_markdown(sot: dict[str, Any], variant: Variant) -> str:
    lines: list[str] = []

    person = sot.get("person", {})
    name = person.get("name", "")
    if name:
        lines.append(f"# {name}")
        lines.append("")

    contact_line = _build_contact_line(person)
    if contact_line:
        lines.append(contact_line)
        lines.append("")

    section_builders = {
        "summary": _build_summary,
        "experience": _build_experience,
        "projects": _build_projects,
        "skills": _build_skills,
        "education": _build_education,
    }

    for section in variant.order:
        builder = section_builders.get(section)
        if builder is None:
            continue
        builder(lines, sot)

    content = "\n".join(lines).strip()
    if not content.endswith("\n"):
        content += "\n"
    return content


def _build_contact_line(person: dict[str, Any]) -> str:
    parts: list[str] = []
    label = person.get("label")
    if isinstance(label, str) and label.strip():
        parts.append(label.strip())

    email = person.get("email")
    if isinstance(email, str) and email.strip():
        parts.append(email.strip())

    location = person.get("location")
    if isinstance(location, dict):
        city = location.get("city")
        region = location.get("region")
        country = location.get("country")
        location_bits = [bit for bit in [city, region, country] if isinstance(bit, str)]
        if location_bits:
            parts.append(", ".join(location_bits))

    links = person.get("links")
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            label_text = link.get("label")
            url = link.get("url")
            if isinstance(label_text, str) and isinstance(url, str):
                parts.append(f"{label_text}: {url}")

    return " | ".join(parts)


def _build_summary(lines: list[str], sot: dict[str, Any]) -> None:
    person = sot.get("person", {})
    summary = person.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return

    lines.append("## Summary")
    lines.append("")
    lines.append(summary.strip())
    lines.append("")


def _build_experience(lines: list[str], sot: dict[str, Any]) -> None:
    experience = sot.get("experience", {})
    roles = experience.get("roles")
    if not isinstance(roles, list) or not roles:
        return

    lines.append("## Experience")
    lines.append("")

    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = _slugify(role.get("id"))
        lines.append(f"::: {{#role-{role_id} .role}}")

        title = _string(role.get("title"))
        company = _string(role.get("company"))
        heading = " - ".join([part for part in [title, company] if part])
        if heading:
            lines.append(f"### {heading}")

        dates = _format_dates(role)
        location = _string(role.get("location"))
        if dates or location:
            line = " | ".join([part for part in [location, dates] if part])
            lines.append(line)

        bullets = role.get("bullets")
        if isinstance(bullets, list) and bullets:
            lines.append("")
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    continue
                bullet_text = _string(bullet.get("text"))
                if not bullet_text:
                    continue
                bullet_id = _slugify(bullet.get("id"))
                tag_classes = _tag_classes(bullet.get("tags"))
                div_attr = _format_div_attributes(
                    f"bullet-{bullet_id}",
                    ["bullet", *tag_classes],
                )
                lines.append(f"::: {div_attr}")
                lines.append(f"- {bullet_text}")
                lines.append(":::")

        lines.append(":::")
        lines.append("")


def _build_projects(lines: list[str], sot: dict[str, Any]) -> None:
    projects = sot.get("projects", {})
    items = projects.get("projects")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Projects")
    lines.append("")
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _string(item.get("name"))
        summary = _string(item.get("summary"))
        if name:
            lines.append(f"### {name}")
        if summary:
            lines.append(summary)
        lines.append("")


def _build_skills(lines: list[str], sot: dict[str, Any]) -> None:
    skills = sot.get("skills", {})
    items = skills.get("skills")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Skills")
    lines.append("")
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _string(item.get("name"))
        keywords = item.get("keywords")
        if name and isinstance(keywords, list):
            keywords_text = ", ".join(_string(keyword) for keyword in keywords if _string(keyword))
            lines.append(f"- **{name}**: {keywords_text}")
    lines.append("")


def _build_education(lines: list[str], sot: dict[str, Any]) -> None:
    education = sot.get("education", {})
    items = education.get("education")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Education")
    lines.append("")
    for item in items:
        if not isinstance(item, dict):
            continue
        institution = _string(item.get("institution"))
        area = _string(item.get("area"))
        study_type = _string(item.get("study_type"))
        heading = " - ".join([part for part in [study_type, area] if part])
        if institution:
            lines.append(f"### {institution}")
        if heading:
            lines.append(heading)
        dates = _format_dates(item)
        if dates:
            lines.append(dates)
        lines.append("")


def _format_dates(item: dict[str, Any]) -> str:
    start = _string(item.get("start"))
    end = _string(item.get("end"))
    if start and end:
        return f"{start} — {end}"
    if start:
        return f"{start} — Present"
    return ""


def _string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _slugify(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _tag_classes(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    classes: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        slug = _slugify(tag)
        if slug:
            classes.append(f"tag-{slug}")
    return classes


def _format_div_attributes(element_id: str, classes: list[str]) -> str:
    parts: list[str] = []
    if element_id:
        parts.append(f"#{element_id}")
    for klass in classes:
        parts.append(f".{klass}")
    if not parts:
        return ""
    return "{" + " ".join(parts) + "}"
