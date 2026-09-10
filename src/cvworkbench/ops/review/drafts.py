"""Read import-draft source identities for retention without requiring healthy artifacts."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cvworkbench.config import ConfigSource, read_config, resolve_drafts_path, resolve_runs_path
from cvworkbench.ops.review import ReviewError


@dataclass(frozen=True)
class ImportDraftSource:
    run_id: str
    run_path: Path


def load_import_draft_sources(config_path: ConfigSource) -> dict[Path, ImportDraftSource]:
    configuration = read_config(config_path)
    root = resolve_drafts_path(configuration)
    runs_root = resolve_runs_path(configuration).resolve()
    if root.exists() and not root.is_dir():
        raise ReviewError(f"Import draft store must be a directory: {root}")
    directories: set[Path] = set()
    try:
        for path in root.rglob("*"):
            if path.is_symlink() and path.is_dir():
                raise ReviewError(
                    f"Import draft discovery cannot traverse a directory symlink: {path}"
                )
            if path.name in {"draft.json", "imported.md"}:
                directories.add(path.parent)
            elif path.is_dir() and path.name.startswith("import-"):
                directories.add(path)
    except OSError as exc:
        raise ReviewError(f"Import draft store could not be read: {root}") from exc
    sources: dict[Path, ImportDraftSource] = {}
    for directory in sorted(directories):
        path = directory / "draft.json"
        if path.is_symlink() or not path.is_file():
            raise ReviewError(f"Import draft source record must be a regular file: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
        except (OSError, ValueError) as exc:
            raise ReviewError(f"Invalid import draft source record: {path}") from exc
        if not isinstance(raw, dict) or raw.get("source") != "import-docx":
            raise ReviewError(f"Import draft metadata must declare source: import-docx: {path}")
        run_id = raw.get("run_id")
        canonical = raw.get("canonical_path")
        if not isinstance(run_id, str) or not isinstance(canonical, str):
            raise ReviewError(f"Import draft requires run_id and canonical_path: {path}")
        identity = PurePosixPath(run_id)
        if (
            not run_id
            or identity.is_absolute()
            or run_id == "."
            or ".." in identity.parts
            or "\\" in run_id
            or identity.as_posix() != run_id
        ):
            raise ReviewError(f"Import draft run_id must be a normalized relative path: {path}")
        baseline = Path(canonical)
        if (
            not baseline.is_absolute()
            or baseline.name != "canonical.md"
            or ".." in baseline.parts
            or "\\" in canonical
            or baseline.as_posix() != canonical
        ):
            raise ReviewError(
                f"Import draft canonical_path must identify an absolute canonical.md: {path}"
            )
        run_path = baseline.parent.resolve()
        if (
            run_path.is_relative_to(runs_root)
            and run_path.relative_to(runs_root).as_posix() != run_id
        ):
            raise ReviewError(f"Import draft run_id and canonical_path disagree: {path}")
        sources[directory] = ImportDraftSource(run_id, run_path)
    return sources


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for name, value in pairs:
        if name in data:
            raise ValueError("Duplicate import draft field")
        data[name] = value
    return data
