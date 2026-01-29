"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/sot_schema.py

Defines strict schemas for Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
DateValue = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)] | Annotated[
    int, Field(gt=0)
]
NonEmptyStrList = Annotated[list[NonEmptyStr], Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Location(StrictModel):
    city: NonEmptyStr | None = None
    region: NonEmptyStr | None = None
    country: NonEmptyStr | None = None


class Link(StrictModel):
    label: NonEmptyStr
    url: NonEmptyStr


class Person(StrictModel):
    id: NonEmptyStr
    name: NonEmptyStr
    label: NonEmptyStr | None = None
    email: NonEmptyStr | None = None
    phone: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    location: Location | None = None
    links: list[Link] | None = None


class Bullet(StrictModel):
    id: NonEmptyStr
    text: NonEmptyStr
    tags: NonEmptyStrList


class Role(StrictModel):
    id: NonEmptyStr
    company: NonEmptyStr
    title: NonEmptyStr
    location: NonEmptyStr | None = None
    start: DateValue
    end: DateValue | None = None
    bullets: Annotated[list[Bullet], Field(min_length=1)]


class Experience(StrictModel):
    roles: Annotated[list[Role], Field(min_length=1)]


class Project(StrictModel):
    id: NonEmptyStr
    name: NonEmptyStr
    summary: NonEmptyStr
    tags: NonEmptyStrList


class Projects(StrictModel):
    projects: Annotated[list[Project], Field(min_length=1)]


class Skill(StrictModel):
    id: NonEmptyStr
    name: NonEmptyStr
    keywords: NonEmptyStrList


class Skills(StrictModel):
    skills: Annotated[list[Skill], Field(min_length=1)]


class EducationEntry(StrictModel):
    id: NonEmptyStr
    institution: NonEmptyStr
    area: NonEmptyStr
    study_type: NonEmptyStr | None = None
    location: NonEmptyStr | None = None
    start: DateValue | None = None
    end: DateValue | None = None
    advisors: NonEmptyStrList | None = None
    thesis_title: NonEmptyStr | None = None
    highlights: NonEmptyStrList | None = None
    tags: NonEmptyStrList


class Education(StrictModel):
    education: Annotated[list[EducationEntry], Field(min_length=1)]


class LetterSection(StrictModel):
    id: NonEmptyStr
    heading: NonEmptyStr | None = None
    text: NonEmptyStr
    tags: NonEmptyStrList


class Letter(StrictModel):
    id: NonEmptyStr
    title: NonEmptyStr
    salutation: NonEmptyStr
    closing: NonEmptyStr
    sections: Annotated[list[LetterSection], Field(min_length=1)]


class Letters(StrictModel):
    letters: Annotated[list[Letter], Field(min_length=1)]


class Author(StrictModel):
    name: NonEmptyStr
    roles: NonEmptyStrList | None = None
    affiliation: NonEmptyStr | None = None
    orcid: NonEmptyStr | None = None


class Publication(StrictModel):
    id: NonEmptyStr
    title: NonEmptyStr
    authors: Annotated[list[Author], Field(min_length=1)]
    venue: NonEmptyStr | None = None
    year: DateValue | None = None
    volume: NonEmptyStr | None = None
    issue: NonEmptyStr | None = None
    pages: NonEmptyStr | None = None
    doi: NonEmptyStr | None = None
    url: NonEmptyStr | None = None
    notes: NonEmptyStr | None = None
    tags: NonEmptyStrList


class Publications(StrictModel):
    publications: Annotated[list[Publication], Field(min_length=1)]


class Honor(StrictModel):
    id: NonEmptyStr
    title: NonEmptyStr
    issuer: NonEmptyStr | None = None
    year: DateValue | None = None
    summary: NonEmptyStr | None = None
    tags: NonEmptyStrList


class Honors(StrictModel):
    honors: Annotated[list[Honor], Field(min_length=1)]


class ServiceEntry(StrictModel):
    id: NonEmptyStr
    organization: NonEmptyStr
    role: NonEmptyStr
    start: DateValue | None = None
    end: DateValue | None = None
    summary: NonEmptyStr | None = None
    highlights: NonEmptyStrList | None = None
    tags: NonEmptyStrList


class Service(StrictModel):
    service: Annotated[list[ServiceEntry], Field(min_length=1)]


class TeachingEntry(StrictModel):
    id: NonEmptyStr
    course: NonEmptyStr
    role: NonEmptyStr
    term: NonEmptyStr | None = None
    enrollment: Annotated[int, Field(gt=0)] | None = None
    evaluation: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    tags: NonEmptyStrList


class Teaching(StrictModel):
    teaching: Annotated[list[TeachingEntry], Field(min_length=1)]


class ConferenceEntry(StrictModel):
    id: NonEmptyStr
    title: NonEmptyStr
    event: NonEmptyStr
    year: DateValue | None = None
    location: NonEmptyStr | None = None
    presentation_type: NonEmptyStr | None = None
    notes: NonEmptyStr | None = None
    tags: NonEmptyStrList


class Conferences(StrictModel):
    conferences: Annotated[list[ConferenceEntry], Field(min_length=1)]


class ReferenceEntry(StrictModel):
    id: NonEmptyStr
    name: NonEmptyStr
    title: NonEmptyStr | None = None
    organization: NonEmptyStr | None = None
    email: NonEmptyStr | None = None
    relationship: NonEmptyStr | None = None
    notes: NonEmptyStr | None = None
    tags: NonEmptyStrList


class References(StrictModel):
    references: Annotated[list[ReferenceEntry], Field(min_length=1)]


class SotData(StrictModel):
    person: Person
    experience: Experience
    projects: Projects
    skills: Skills
    education: Education
    letters: Letters
    publications: Publications | None = None
    honors: Honors | None = None
    service: Service | None = None
    teaching: Teaching | None = None
    conferences: Conferences | None = None
    references: References | None = None
