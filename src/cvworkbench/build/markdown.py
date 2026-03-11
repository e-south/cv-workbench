"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/markdown.py

Materializes canonical markdown from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

from cvworkbench.text import slugify, tag_classes
from cvworkbench.variants import Variant


def build_markdown(sot: dict[str, Any], variant: Variant) -> str:
    snippets = _extract_snippets(sot)
    if variant.document_type == "cover-letter":
        return _build_cover_letter_markdown(sot, variant, snippets)
    return _build_resume_markdown(sot, variant, snippets)


def _build_resume_markdown(
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> str:
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
        "publications": _build_publications,
        "conferences": _build_conferences,
        "honors": _build_honors,
        "service": _build_service,
        "teaching": _build_teaching,
        "references": _build_references,
    }

    for section in variant.order:
        builder = section_builders.get(section)
        if builder is None:
            continue
        builder(lines, sot, variant, snippets)

    content = "\n".join(lines).strip()
    if not content.endswith("\n"):
        content += "\n"
    return content


def _build_cover_letter_markdown(
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> str:
    if not variant.letter_id:
        raise ValueError("Cover letter variants must define letter_id")

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

    letters = _find_letter(sot, variant.letter_id)
    title = _string(letters.get("title"))
    if title:
        lines.append(f"## {title}")
        lines.append("")

    salutation = _string(letters.get("salutation"))
    if salutation:
        lines.append(salutation)
        lines.append("")

    opening_snippet = _select_snippet_text(snippets, variant, scope="letter-open", section=None)
    if opening_snippet:
        lines.append(opening_snippet)
        lines.append("")

    sections = letters.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = slugify(section.get("id", ""))
            tag_classes = _tag_classes(section.get("tags"))
            div_attr = _format_div_attributes(
                f"section-{section_id}",
                ["section", *tag_classes],
            )
            lines.append(f"::: {div_attr}")
            heading = _string(section.get("heading"))
            if heading:
                lines.append(f"### {heading}")
            text = _string(section.get("text"))
            if text:
                lines.append(text)
            lines.append(":::")
            lines.append("")

    closing_snippet = _select_snippet_text(snippets, variant, scope="letter-close", section=None)
    if closing_snippet:
        lines.append(closing_snippet)
        lines.append("")

    closing = _string(letters.get("closing"))
    if closing:
        lines.append(closing)
        lines.append("")

    content = "\n".join(lines).strip()
    if not content.endswith("\n"):
        content += "\n"
    return content


def _find_letter(sot: dict[str, Any], letter_id: str) -> dict[str, Any]:
    letters_data = sot.get("letters", {})
    letters = letters_data.get("letters")
    if not isinstance(letters, list):
        raise ValueError("letters.letters must be a list")
    for letter in letters:
        if not isinstance(letter, dict):
            continue
        if letter.get("id") == letter_id:
            return letter
    raise ValueError(f"Letter not found: {letter_id}")


def _build_contact_line(person: dict[str, Any]) -> str:
    parts: list[str] = []
    label = person.get("label")
    if isinstance(label, str) and label.strip():
        parts.append(label.strip())

    email = person.get("email")
    if isinstance(email, str) and email.strip():
        parts.append(email.strip())

    phone = person.get("phone")
    if isinstance(phone, str) and phone.strip():
        parts.append(phone.strip())

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


def _build_summary(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    person = sot.get("person", {})
    summary = _select_snippet_text(snippets, variant, scope="summary", section=None)
    if not summary:
        summary = _string(person.get("summary"))
    if not summary:
        return

    lines.append("## Summary")
    lines.append("")
    lines.append(summary)
    lines.append("")


def _build_experience(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    experience = sot.get("experience", {})
    roles = experience.get("roles")
    if not isinstance(roles, list) or not roles:
        return

    lines.append("## Experience")
    lines.append("")
    _append_section_intro(lines, "experience", variant, snippets)

    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
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
            emitted_bullet = False
            selected_count = 0
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    continue
                if not _tags_match_variant(bullet.get("tags"), variant):
                    continue
                if (
                    variant.max_bullets_per_role is not None
                    and selected_count >= variant.max_bullets_per_role
                ):
                    continue
                bullet_text = _string(bullet.get("text"))
                if not bullet_text:
                    continue
                if not emitted_bullet:
                    lines.append("")
                    emitted_bullet = True
                selected_count += 1
                bullet_id = slugify(bullet.get("id", ""))
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


def _build_projects(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    projects = sot.get("projects", {})
    items = projects.get("projects")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Projects")
    lines.append("")
    _append_section_intro(lines, "projects", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        project_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"project-{project_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        name = _string(item.get("name"))
        summary = _string(item.get("summary"))
        if name:
            lines.append(f"### {name}")
        if summary:
            lines.append(summary)
        lines.append(":::")
        lines.append("")


def _build_skills(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    skills = sot.get("skills", {})
    items = skills.get("skills")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Skills")
    lines.append("")
    _append_section_intro(lines, "skills", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _string(item.get("name"))
        keywords = item.get("keywords")
        if name and isinstance(keywords, list):
            keywords_text = ", ".join(_string(keyword) for keyword in keywords if _string(keyword))
            lines.append(f"- **{name}**: {keywords_text}")
    lines.append("")


def _build_education(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    education = sot.get("education", {})
    items = education.get("education")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Education")
    lines.append("")
    _append_section_intro(lines, "education", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"education-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        institution = _string(item.get("institution"))
        area = _string(item.get("area"))
        study_type = _string(item.get("study_type"))
        heading = " - ".join([part for part in [study_type, area] if part])
        if institution:
            lines.append(f"### {institution}")
        if heading:
            lines.append(heading)
        location = _string(item.get("location"))
        if location:
            lines.append(location)
        dates = _format_dates(item)
        if dates:
            lines.append(dates)
        advisors = item.get("advisors")
        if isinstance(advisors, list) and advisors:
            advisors_text = ", ".join(_string(advisor) for advisor in advisors if _string(advisor))
            if advisors_text:
                lines.append(f"Advisors: {advisors_text}")
        thesis_title = _string(item.get("thesis_title"))
        if thesis_title:
            lines.append(f'Thesis: "{thesis_title}"')
        highlights = item.get("highlights")
        if isinstance(highlights, list) and highlights:
            lines.append("")
            for highlight in highlights:
                highlight_text = _string(highlight)
                if highlight_text:
                    lines.append(f"- {highlight_text}")
        lines.append(":::")
        lines.append("")


def _build_publications(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    publications = sot.get("publications", {})
    items = publications.get("publications")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Publications")
    lines.append("")
    _append_section_intro(lines, "publications", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"publication-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        title = _string(item.get("title"))
        if title:
            lines.append(f"### {title}")

        authors_text = _format_authors(item.get("authors"))
        if authors_text:
            lines.append(authors_text)

        venue_line = _format_publication_venue(item)
        if venue_line:
            lines.append(venue_line)

        notes = _string(item.get("notes"))
        if notes:
            lines.append(notes)

        lines.append(":::")
        lines.append("")


def _build_conferences(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    conferences = sot.get("conferences", {})
    items = conferences.get("conferences")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Conferences & Workshops")
    lines.append("")
    _append_section_intro(lines, "conferences", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"conference-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        title = _string(item.get("title"))
        if title:
            lines.append(f"### {title}")

        event = _string(item.get("event"))
        year = _date_string(item.get("year"))
        presentation_type = _string(item.get("presentation_type"))
        location = _string(item.get("location"))
        line_bits = [bit for bit in [event, presentation_type, location, year] if bit]
        if line_bits:
            lines.append(" | ".join(line_bits))

        notes = _string(item.get("notes"))
        if notes:
            lines.append(notes)

        lines.append(":::")
        lines.append("")


def _build_honors(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    honors = sot.get("honors", {})
    items = honors.get("honors")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Honors & Awards")
    lines.append("")
    _append_section_intro(lines, "honors", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"honor-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        title = _string(item.get("title"))
        if title:
            lines.append(f"### {title}")

        issuer = _string(item.get("issuer"))
        year = _date_string(item.get("year"))
        line_bits = [bit for bit in [issuer, year] if bit]
        if line_bits:
            lines.append(" | ".join(line_bits))

        summary = _string(item.get("summary"))
        if summary:
            lines.append(summary)

        lines.append(":::")
        lines.append("")


def _build_service(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    service = sot.get("service", {})
    items = service.get("service")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Service & Leadership")
    lines.append("")
    _append_section_intro(lines, "service", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"service-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        role = _string(item.get("role"))
        organization = _string(item.get("organization"))
        heading = " - ".join([part for part in [role, organization] if part])
        if heading:
            lines.append(f"### {heading}")

        dates = _format_dates(item)
        if dates:
            lines.append(dates)

        summary = _string(item.get("summary"))
        if summary:
            lines.append(summary)

        lines.append(":::")
        lines.append("")


def _build_teaching(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    teaching = sot.get("teaching", {})
    items = teaching.get("teaching")
    if not isinstance(items, list) or not items:
        return

    lines.append("## Teaching")
    lines.append("")
    _append_section_intro(lines, "teaching", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"teaching-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        course = _string(item.get("course"))
        if course:
            lines.append(f"### {course}")

        role = _string(item.get("role"))
        term = _string(item.get("term"))
        enrollment = item.get("enrollment")
        enrollment_text = str(enrollment) if isinstance(enrollment, int) else ""
        evaluation = _string(item.get("evaluation"))
        line_bits = [bit for bit in [role, term, enrollment_text, evaluation] if bit]
        if line_bits:
            lines.append(" | ".join(line_bits))

        summary = _string(item.get("summary"))
        if summary:
            lines.append(summary)

        lines.append(":::")
        lines.append("")


def _build_references(
    lines: list[str],
    sot: dict[str, Any],
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    references = sot.get("references", {})
    items = references.get("references")
    if not isinstance(items, list) or not items:
        return

    lines.append("## References")
    lines.append("")
    _append_section_intro(lines, "references", variant, snippets)
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _tags_match_variant(item.get("tags"), variant):
            continue
        entry_id = slugify(item.get("id", ""))
        tag_list = _tag_classes(item.get("tags"))
        div_attr = _format_div_attributes(f"reference-{entry_id}", ["section", *tag_list])
        lines.append(f"::: {div_attr}")

        name = _string(item.get("name"))
        if name:
            lines.append(f"### {name}")

        title = _string(item.get("title"))
        organization = _string(item.get("organization"))
        line_bits = [bit for bit in [title, organization] if bit]
        if line_bits:
            lines.append(" | ".join(line_bits))

        email = _string(item.get("email"))
        relationship = _string(item.get("relationship"))
        contact_bits = [bit for bit in [relationship, email] if bit]
        if contact_bits:
            lines.append(" | ".join(contact_bits))

        notes = _string(item.get("notes"))
        if notes:
            lines.append(notes)

        lines.append(":::")
        lines.append("")


def _extract_snippets(sot: dict[str, Any]) -> list[dict[str, Any]]:
    snippets_block = sot.get("snippets")
    if not isinstance(snippets_block, dict):
        return []
    snippets = snippets_block.get("snippets")
    if not isinstance(snippets, list):
        return []
    return snippets


def _append_section_intro(
    lines: list[str],
    section: str,
    variant: Variant,
    snippets: list[dict[str, Any]],
) -> None:
    intro = _select_snippet_text(snippets, variant, scope="section-intro", section=section)
    if not intro:
        return
    lines.append(intro)
    lines.append("")


def _select_snippet_text(
    snippets: list[dict[str, Any]],
    variant: Variant,
    *,
    scope: str,
    section: str | None,
) -> str:
    matches: list[tuple[str, str]] = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        if snippet.get("scope") != scope:
            continue
        if section is not None and snippet.get("section") != section:
            continue
        if section is None and snippet.get("section") not in (None, ""):
            continue
        if not _snippet_matches_variant(snippet, variant):
            continue
        text = _string(snippet.get("text"))
        if not text:
            continue
        snippet_id = _string(snippet.get("id")) or "snippet"
        matches.append((snippet_id, text))

    if len(matches) > 1:
        ids = ", ".join(snippet_id for snippet_id, _ in matches)
        label = f"{scope}:{section}" if section else scope
        raise ValueError(f"Multiple snippets matched {label}: {ids}")

    return matches[0][1] if matches else ""


def _snippet_matches_variant(snippet: dict[str, Any], variant: Variant) -> bool:
    return _tags_match_variant(snippet.get("tags"), variant)


def _tags_match_variant(raw_tags: Any, variant: Variant) -> bool:
    tag_set = _expand_tag_set(raw_tags)
    if variant.exclude_tags and _has_any(tag_set, variant.exclude_tags):
        return False
    if not variant.include_tags:
        return True
    return _has_any(tag_set, variant.include_tags)


def _expand_tag_set(raw_tags: Any) -> set[str]:
    if not isinstance(raw_tags, list):
        return set()
    classes: set[str] = set()
    for tag in raw_tags:
        if not isinstance(tag, str):
            continue
        for klass in tag_classes(tag):
            classes.add(klass)
    return classes


def _has_any(tag_set: set[str], tags: list[str]) -> bool:
    for tag in tags:
        if tag in tag_set:
            return True
    return False


def _format_authors(raw: Any) -> str:
    if not isinstance(raw, list) or not raw:
        return ""
    formatted: list[str] = []
    for author in raw:
        if not isinstance(author, dict):
            continue
        name = _string(author.get("name"))
        if not name:
            continue
        classes = ["author"]
        roles = author.get("roles")
        if isinstance(roles, list):
            for role in roles:
                role_text = _string(role)
                if not role_text:
                    continue
                role_class = slugify(role_text)
                if role_class:
                    classes.append(f"role-{role_class}")
        class_attr = " ".join(f".{klass}" for klass in classes if klass)
        if class_attr:
            formatted.append(f"[{name}]{{{class_attr}}}")
        else:
            formatted.append(name)
    return ", ".join(formatted)


def _format_publication_venue(item: dict[str, Any]) -> str:
    venue = _string(item.get("venue"))
    year = _date_string(item.get("year"))
    volume = _string(item.get("volume"))
    issue = _string(item.get("issue"))
    pages = _string(item.get("pages"))
    venue_bits = [bit for bit in [venue, year] if bit]
    if volume or issue or pages:
        details = ", ".join(bit for bit in [volume, issue, pages] if bit)
        if details:
            venue_bits.append(details)
    return " | ".join(venue_bits)


def _format_dates(item: dict[str, Any]) -> str:
    start = _date_string(item.get("start"))
    end = _date_string(item.get("end"))
    if start and end:
        return f"{start} — {end}"
    if start:
        return f"{start} — Present"
    return ""


def _string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _date_string(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _tag_classes(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    classes: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        for klass in tag_classes(tag):
            classes.append(f"tag-{klass}")
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
