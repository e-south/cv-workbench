"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/themes.py

Loads render themes and resolves render plans.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ThemeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThemeRoute:
    name: str
    to: str
    template: Path | None
    pdf_engine: str | None
    defaults: list[Path]


@dataclass(frozen=True)
class Theme:
    id: str
    description: str | None
    root: Path
    routes: dict[str, ThemeRoute]


@dataclass(frozen=True)
class RenderPlan:
    output_format: str
    to: str
    template: Path | None
    pdf_engine: str | None
    defaults: list[Path]
    style_path: Path | None
    style_kind: str | None
    theme_id: str | None
    theme_hash: str | None
    style_hash: str | None


_FORMAT_ROUTES = {
    "pdf": "pdf",
    "html": "html_preview",
    "docx": "docx",
}


def list_themes(themes_dir: Path) -> list[Theme]:
    if not themes_dir.exists():
        raise ThemeError(f"Themes directory not found: {themes_dir}")

    themes: list[Theme] = []
    for entry in sorted(themes_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        theme_path = entry / "theme.yaml"
        if not theme_path.exists():
            continue
        themes.append(load_theme(entry))
    return themes


def resolve_theme(themes_dir: Path, theme_id: str) -> Theme:
    theme_dir = themes_dir / theme_id
    if not theme_dir.exists():
        raise ThemeError(f"Theme not found: {theme_id}")
    return load_theme(theme_dir)


def list_theme_presets(theme: Theme) -> list[str]:
    html_presets = {
        path.stem for path in (theme.root / "styles" / "html").glob("*.css")
    }
    pdf_presets = {
        path.stem for path in (theme.root / "styles" / "pdf").glob("*.tex")
    }
    return sorted(html_presets & pdf_presets)


def build_render_plan(
    *,
    output_format: str,
    theme: Theme | None,
    style_preset: str | None,
    pdf_engine: str | None,
) -> RenderPlan:
    if output_format == "md":
        return RenderPlan(
            output_format=output_format,
            to="markdown",
            template=None,
            pdf_engine=None,
            defaults=[],
            style_path=None,
            style_kind=None,
            theme_id=None,
            theme_hash=None,
            style_hash=None,
        )
    if output_format == "ats":
        return RenderPlan(
            output_format=output_format,
            to="plain",
            template=None,
            pdf_engine=None,
            defaults=[],
            style_path=None,
            style_kind=None,
            theme_id=None,
            theme_hash=None,
            style_hash=None,
        )

    if theme is None:
        raise ThemeError(f"Theme is required for output format '{output_format}'")

    route_name = _FORMAT_ROUTES.get(output_format)
    if route_name is None:
        raise ThemeError(f"Unsupported output format '{output_format}'")
    route = theme.routes.get(route_name)
    if route is None:
        raise ThemeError(f"Theme '{theme.id}' does not define route '{route_name}'")

    resolved_engine = None
    if output_format == "pdf":
        resolved_engine = route.pdf_engine or pdf_engine
    if output_format == "pdf" and not resolved_engine:
        raise ThemeError("PDF engine is required for PDF outputs")

    style_path, style_kind = _resolve_style_path(theme, output_format, style_preset)
    style_hash = _hash_file(style_path) if style_path else None
    return RenderPlan(
        output_format=output_format,
        to=route.to,
        template=route.template,
        pdf_engine=resolved_engine,
        defaults=route.defaults,
        style_path=style_path,
        style_kind=style_kind,
        theme_id=theme.id,
        theme_hash=hash_theme(theme),
        style_hash=style_hash,
    )


def hash_theme(theme: Theme) -> str:
    paths: list[Path] = [theme.root / "theme.yaml"]
    for route in theme.routes.values():
        paths.extend(route.defaults)
        if route.template is not None:
            paths.append(route.template)
    return _hash_files(paths)


def load_theme(theme_dir: Path) -> Theme:
    theme_path = theme_dir / "theme.yaml"
    if not theme_path.exists():
        raise ThemeError(f"Theme file not found: {theme_path}")

    raw = yaml.safe_load(theme_path.read_text())
    if raw is None:
        raise ThemeError("Theme file is empty")
    if not isinstance(raw, dict):
        raise ThemeError("Theme file must be a YAML mapping")

    theme_id = _require_str(raw, "id")
    description = _optional_str(raw.get("description"))
    if theme_id != theme_dir.name:
        raise ThemeError(f"Theme id '{theme_id}' does not match directory '{theme_dir.name}'")

    routes_data = raw.get("routes")
    if not isinstance(routes_data, dict) or not routes_data:
        raise ThemeError("Theme routes must be a non-empty mapping")

    routes: dict[str, ThemeRoute] = {}
    for name, data in routes_data.items():
        if not isinstance(name, str) or not name.strip():
            raise ThemeError("Theme route names must be strings")
        if not isinstance(data, dict):
            raise ThemeError(f"Theme route '{name}' must be a mapping")

        to_value = _require_str(data, "to")
        template_value = _require_str(data, "template")
        template_path = _resolve_template(theme_dir, template_value)
        defaults = _resolve_defaults(theme_dir, name, data)
        pdf_engine = _optional_str(data.get("pdf_engine"))

        routes[name] = ThemeRoute(
            name=name,
            to=to_value,
            template=template_path,
            pdf_engine=pdf_engine,
            defaults=defaults,
        )

    return Theme(
        id=theme_id,
        description=description,
        root=theme_dir,
        routes=routes,
    )


def _resolve_template(theme_dir: Path, template_value: str) -> Path | None:
    if template_value == "default":
        return None
    template_path = theme_dir / template_value
    if not template_path.exists():
        raise ThemeError(f"Template not found: {template_path}")
    return template_path.resolve()


def _resolve_defaults(theme_dir: Path, route: str, data: dict[str, Any]) -> list[Path]:
    defaults_value = data.get("defaults")
    if not isinstance(defaults_value, list) or not defaults_value:
        raise ThemeError(f"Theme route '{route}' defaults must be a non-empty list")

    defaults: list[Path] = []
    for item in defaults_value:
        if not isinstance(item, str) or not item.strip():
            raise ThemeError(f"Theme route '{route}' defaults must be strings")
        path = theme_dir / item
        if not path.exists():
            raise ThemeError(f"Theme defaults file not found: {path}")
        defaults.append(path.resolve())
    return defaults


def _resolve_style_path(
    theme: Theme,
    output_format: str,
    style_preset: str | None,
) -> tuple[Path | None, str | None]:
    if style_preset is None:
        return None, None

    if output_format == "pdf":
        path = theme.root / "styles" / "pdf" / f"{style_preset}.tex"
        if not path.exists():
            raise ThemeError(f"Style preset not found: {path}")
        return path.resolve(), "header"
    if output_format == "html":
        path = theme.root / "styles" / "html" / f"{style_preset}.css"
        if not path.exists():
            raise ThemeError(f"Style preset not found: {path}")
        return path.resolve(), "css"
    return None, None


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ThemeError(f"Theme field '{key}' is required")
    return value.strip()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _hash_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(_hash_file(path).encode("utf-8"))
    return digest.hexdigest()


def _hash_file(path: Path | None) -> str:
    if path is None:
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
