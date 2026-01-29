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
    start: DateValue | None = None
    end: DateValue | None = None


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


class SotData(StrictModel):
    person: Person
    experience: Experience
    projects: Projects
    skills: Skills
    education: Education
    letters: Letters
