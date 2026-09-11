"""Retain exact native source runs named by private publication preparation."""

from pathlib import Path

from cvworkbench.config import ConfigSource, resolve_publish_path
from cvworkbench.ops.publication.record import NativePreparationRecord, parse_preparation_record


def publication_run_references(configuration: ConfigSource) -> dict[Path, list[str]]:
    root = resolve_publish_path(configuration)
    if root.is_symlink():
        raise ValueError("Invalid publication store: symlink")
    references: dict[Path, list[str]] = {}
    for path in sorted(root.glob("*/preparation.json")):
        try:
            if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
                raise ValueError
            record = parse_preparation_record(path.read_bytes())
            if isinstance(record, NativePreparationRecord):
                manifest = Path(record.run_manifest.path)
                if manifest.name != "manifest.json":
                    raise ValueError
                references.setdefault(manifest.parent.resolve(), []).append(
                    f"publication:{path.parent.name}"
                )
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid publication retention record: {path}") from exc
    return references
