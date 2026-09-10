"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/assets.py

Records explicit render inputs and enforces their request-local lifetime.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from cvworkbench.themes import RenderPlan, Theme, hash_theme, theme_hash_paths


class RenderAssetError(ValueError):
    pass


@dataclass(frozen=True)
class RenderAssetContract:
    file_hashes: Mapping[Path, str] = field(repr=False)
    filter_paths: tuple[Path, ...]
    theme_hash: str

    def verify(self, filter_paths: Sequence[Path], render_plans: Mapping[str, RenderPlan]) -> None:
        self._check_selection(filter_paths, render_plans)
        for path, expected in self.file_hashes.items():
            if _hash_asset(path) != expected:
                raise RenderAssetError(f"Render asset changed since planning: {path}")

    def _check_selection(
        self, filter_paths: Sequence[Path], render_plans: Mapping[str, RenderPlan]
    ) -> None:
        if tuple(path.resolve() for path in filter_paths) != self.filter_paths:
            raise RenderAssetError("Render asset filter selection changed; create a new build plan")
        for fmt, plan in render_plans.items():
            paths = [*plan.defaults, plan.template, plan.style_path, plan.reference_doc]
            for path in paths:
                if path is not None and path.resolve() not in self.file_hashes:
                    raise RenderAssetError(f"Render asset was not recorded during planning: {path}")
            if plan.theme_hash is not None and plan.theme_hash != self.theme_hash:
                raise RenderAssetError(f"Render assets changed while planning the {fmt} route")
            if (
                plan.style_path is not None
                and self.file_hashes[plan.style_path.resolve()] != plan.style_hash
            ):
                raise RenderAssetError(
                    f"Render asset changed while planning its style: {plan.style_path}"
                )

    def filter_metadata(self) -> list[dict[str, str]]:
        return [{"name": path.name, "sha256": self.file_hashes[path]} for path in self.filter_paths]


def capture_render_assets(
    theme: Theme,
    render_plans: Mapping[str, RenderPlan],
    filter_paths: Sequence[Path],
) -> RenderAssetContract:
    """Capture fingerprints, not a frozen copy of Pandoc's dependency graph."""
    selected_filters = tuple(path.resolve() for path in filter_paths)
    paths = [*theme_hash_paths(theme), *selected_filters]
    paths.extend(plan.style_path for plan in render_plans.values() if plan.style_path is not None)
    hashes = {path: _hash_asset(path) for path in dict.fromkeys(path.resolve() for path in paths)}
    definition = (theme.root / "theme.yaml").resolve()
    if hashes[definition] != theme.definition_sha256:
        raise RenderAssetError(f"Render asset changed while parsing its definition: {definition}")
    theme_hash = hash_theme(theme, file_hashes=hashes)
    contract = RenderAssetContract(
        file_hashes=MappingProxyType(hashes),
        filter_paths=selected_filters,
        theme_hash=theme_hash,
    )
    contract._check_selection(filter_paths, render_plans)
    return contract


def _hash_asset(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RenderAssetError(f"Render asset is unavailable: {path}") from exc
