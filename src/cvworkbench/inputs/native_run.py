"""Attest explicit native outputs against the current configuration and source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from cvworkbench.config import ConfigSnapshot, resolve_runs_path, resolve_variant_path
from cvworkbench.inputs.sot import load_sot_snapshot
from cvworkbench.variants import Variant, parse_variant_bytes


@dataclass(frozen=True)
class CapturedRun:
    variant: Variant
    source_data: dict = field(repr=False)
    outputs: dict[str, bytes] = field(repr=False)
    output_paths: dict[str, Path]
    stamps: dict[str, tuple[Path, str]]
    source_files: dict[str, tuple[Path, str]]
    styles: dict[str, bytes] = field(default_factory=dict, repr=False)


def capture_native_run(
    *,
    configuration: ConfigSnapshot,
    run_path: Path,
    variant_id: str,
    sot_path: Path,
    formats: tuple[str, ...],
    optional_formats: tuple[str, ...] = (),
) -> CapturedRun:
    run = run_path.resolve()
    root = resolve_runs_path(configuration).resolve()
    if run == root or not run.is_relative_to(root):
        raise ValueError("Native operation requires an explicit run beneath configured runs")
    stamps = {"configuration": (configuration.path, configuration.sha256)}

    def capture(name: str, path: Path) -> bytes:
        if any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file():
            raise ValueError("Native run inputs must be regular files without symlink traversal")
        content = path.read_bytes()
        stamps[name] = (path.resolve(), hashlib.sha256(content).hexdigest())
        return content

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Native manifest contains a duplicate field")
            result[key] = value
        return result

    manifest = json.loads(capture("run_manifest", run / "manifest.json"), object_pairs_hook=unique)
    variant = parse_variant_bytes(
        capture("variant_config", resolve_variant_path(variant_id, configuration))
    )
    source = load_sot_snapshot(sot_path)
    source_files = {
        name: ((sot_path / name).resolve(), sha) for name, sha in source.sot_hashes.items()
    }
    source_files.update(
        {
            "snippet:" + name: ((sot_path / name).resolve(), sha)
            for name, sha in source.snippet_hashes.items()
            if not name.startswith("inline:")
        }
    )
    try:
        if (
            manifest["configuration"] != {"sha256": configuration.sha256}
            or manifest["variant_hash"] != stamps["variant_config"][1]
            or manifest["sot_hashes"] != dict(source.sot_hashes)
            or manifest["snippet_hashes"] != dict(source.snippet_hashes)
        ):
            raise ValueError("Native build inputs no longer match source or configuration; rebuild")
        for key in ("id", "exclude_tags", "contact_fields", "order"):
            if manifest["variant"][key] != getattr(variant, key):
                raise ValueError("Native build variant does not match selection")
        if variant.id != variant_id:
            raise ValueError("Native build variant identity does not match selection")
        outputs, paths = {}, {}
        selected_formats = (
            *formats,
            *(fmt for fmt in optional_formats if fmt in manifest["outputs"]),
        )
        for fmt in selected_formats:
            name = manifest["outputs"][fmt]
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or name in {".", ".."}
                or "\\" in name
            ):
                raise ValueError("Native run outputs must remain inside their run")
            path = run / name
            if path.resolve().parent != run:
                raise ValueError("Native run outputs must remain inside their run")
            outputs[fmt] = capture("output:" + fmt, path)
            paths[fmt] = path
            if stamps["output:" + fmt][1] != manifest["output_hashes"][fmt]:
                raise ValueError("Native output hash does not match its build manifest")
    except (KeyError, TypeError) as exc:
        raise ValueError("Native build manifest is incomplete or malformed") from exc
    styles = {}
    if "html" in outputs:
        details = manifest.get("render", {}).get("formats", {}).get("html", {})
        relative = details.get("style_path")
        if relative is not None:
            if (
                not isinstance(relative, str)
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or "\\" in relative
            ):
                raise ValueError("Native HTML stylesheet must remain inside its run")
            style_path = run / relative
            if not style_path.resolve().is_relative_to(run) or style_path.suffix != ".css":
                raise ValueError("Native HTML stylesheet must remain inside its run")
            styles["html"] = capture("style:html", style_path)
            if stamps["style:html"][1] != details.get("style_hash"):
                raise ValueError("Native HTML stylesheet hash does not match its build manifest")
    return CapturedRun(variant, source.data, outputs, paths, stamps, source_files, styles)
