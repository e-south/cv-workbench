"""Project historical promotion receipts onto exact native run dependencies."""

from pathlib import Path

from cvworkbench.config import ConfigSource, resolve_documents_root
from cvworkbench.ops.documents.records import load_receipts, read_json


def promotion_run_references(configuration: ConfigSource) -> dict[Path, list[str]]:
    root = resolve_documents_root(configuration)
    if root is None:
        return {}
    _, contents = load_receipts(root)
    references: dict[Path, list[str]] = {}
    for path, content in contents.items():
        run = read_json(content)["plan"]["source"]["run_path"]
        if run is not None:
            references.setdefault(Path(run).resolve(), []).append(f"promotion:{path}")
    return references
