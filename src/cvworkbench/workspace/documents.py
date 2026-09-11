"""Inspect ordinary career files without requiring a native document project."""

from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path

from cvworkbench.config import (
    ConfigSource,
    read_config,
    resolve_documents_root,
    resolve_sot_reference,
    resolve_themes_dir,
    resolve_var_root,
)
from cvworkbench.ops.documents.records import DocumentError, load_receipts
from cvworkbench.variants import load_variants_from_config
from cvworkbench.workspace.commands import command_prefix

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".md", ".txt"}


def library_context(configuration: ConfigSource) -> dict:
    snapshot = read_config(configuration)
    root = resolve_documents_root(snapshot)
    if root is None:
        return {"state": "unconfigured", "root": None, "count": 0}
    inventory = inspect_documents(config_path=snapshot)
    return {
        "state": "issues" if inventory["issues"] else "ready",
        "root": str(root),
        "count": len(inventory["items"]),
        "issues": inventory["issues"],
        "current": [
            {key: item.get(key) for key in ("path", "state", "document", "receipt")}
            for item in inventory["items"]
            if item["location"] == "current"
        ],
        "list_command": shlex.join(
            [*command_prefix(), "documents", "list", "--config", str(snapshot.path), "--json"]
        ),
    }


def inspect_documents(
    *,
    root: Path | None = None,
    config_path: ConfigSource | None = None,
    paths: list[Path] | None = None,
) -> dict:
    configuration = read_config(config_path) if config_path is not None else None
    root = root or (resolve_documents_root(configuration) if configuration else None)
    if root is None:
        raise DocumentError("Choose --root or configure documents.root")
    root = root.resolve(strict=True)
    items, issues, recipes = [], [], []
    excluded = set()
    if configuration:
        excluded.update(
            {
                configuration.path.parent,
                resolve_var_root(configuration),
                resolve_sot_reference(None, configuration),
                resolve_themes_dir(configuration),
            }
        )
        recipes = [
            {
                "id": variant["id"],
                "config": str(configuration.path),
                "document_type": variant["document_type"],
            }
            for variant in load_variants_from_config(configuration.path)
        ]
    selected = paths if paths is not None else [root / "current", root / "working"]
    candidates = set()
    for selected_path in selected:
        directory = selected_path.absolute()
        if not directory.resolve().is_relative_to(root):
            raise DocumentError("Selected document path is outside the library")
        if directory.is_symlink():
            issues.append(f"Linked document root is not followed: {directory}")
            continue
        if directory.is_file():
            candidates.add(directory)
            continue
        for parent, folders, files in os.walk(directory, followlinks=False):
            base = Path(parent)
            folders[:] = sorted(
                name
                for name in folders
                if not name.startswith(".")
                and base / name not in excluded
                and not (base / name).is_symlink()
            )
            candidates.update(base / name for name in files)
    for path in sorted(candidates):
        if path.name.startswith((".", "~$")) or path.name in {"README.md", "AGENTS.md"}:
            continue
        if path.suffix.lower() not in DOCUMENT_EXTENSIONS:
            continue
        if path.is_symlink() or not path.is_file():
            issues.append(f"Non-regular document is not opened: {path}")
            continue
        relative = path.relative_to(root)
        items.append(
            {
                "path": str(path),
                "location": relative.parts[0]
                if relative.parts[0] in {"current", "working"}
                else "selected",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "state": "unrecorded",
                "document": None,
            }
        )
    try:
        tips, _ = load_receipts(root)
    except DocumentError as exc:
        tips = {}
        issues.append(str(exc))
    recorded = {
        str(root / f["destination"]): (tip, f) for tip in tips.values() for f in tip["files"]
    }
    present = {item["path"] for item in items}
    for name in sorted(recorded.keys() - present):
        path = Path(name)
        if not path.exists() and any(
            path == chosen.absolute() or path.is_relative_to(chosen.absolute())
            for chosen in selected
        ):
            items.append({"path": name, "location": "current", "sha256": None, "state": "missing"})
            issues.append(f"Promoted document is missing: {name}")
    for item in items:
        if item["path"] in recorded:
            tip, artifact = recorded[item["path"]]
            item.update(
                {
                    "state": "missing"
                    if item["sha256"] is None
                    else ("current" if item["sha256"] == artifact["sha256"] else "modified"),
                    "document": tip["document"],
                    "source": tip["source"],
                    "receipt": str(root / tip["receipt_path"]),
                }
            )
    return {"root": str(root), "items": items, "issues": issues, "recipes": recipes}
