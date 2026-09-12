"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/provenance.py

Record guidance input fingerprints and compare them with current local observations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import ConfigSource, read_config, resolve_default_variant
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.sot_versions import SotVersionError, resolve_active_sot_path
from cvworkbench.inputs.tags import extract_tags, tag_counts
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects.guidance import GUIDANCE_ALGORITHM, guidance_catalog_inputs
from cvworkbench.ops.projects.records import GuidanceInputCheck, GuidanceJobInputs, ProjectDetails
from cvworkbench.variants import load_variants_from_config

GUIDANCE_INPUT_SCHEMA = "cvw-guidance-inputs-v1"
_COMPONENTS = ("extracted_text", "signals", "source_tags", "variant_catalog", "default_variant")


def _digest(value: Any) -> str:
    content = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _catalog_digest(variants: list[dict[str, Any]]) -> str:
    inputs = guidance_catalog_inputs(variants)
    return _digest(sorted(inputs, key=lambda item: json.dumps(item, sort_keys=True)))


def guidance_input_provenance(
    job: GuidanceJobInputs,
    *,
    source_tags: dict[str, int],
    variants: list[dict[str, Any]],
    default_variant: str,
) -> dict[str, Any]:
    return {
        "schema": GUIDANCE_INPUT_SCHEMA,
        "algorithm": GUIDANCE_ALGORITHM,
        "components": {
            "extracted_text": job.extracted_sha256,
            "signals": job.signals_sha256,
            "source_tags": _digest(source_tags),
            "variant_catalog": _catalog_digest(variants),
            "default_variant": _digest(default_variant),
        },
    }


def _recorded_components(plan: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(plan, dict):
        return None, "Saved guidance must be an object."
    value = plan.get("provenance")
    if value is None:
        return None, "Saved guidance has no input provenance."
    if not isinstance(value, dict):
        return None, "Saved guidance input provenance must be an object."
    if value.get("schema") != GUIDANCE_INPUT_SCHEMA or value.get("algorithm") != GUIDANCE_ALGORITHM:
        return None, "Saved guidance uses an unsupported input schema or algorithm."
    components = value.get("components")
    if not isinstance(components, dict) or set(components) != set(_COMPONENTS):
        return None, "Saved guidance input fingerprints are incomplete or unsupported."
    if any(
        not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
        for digest in components.values()
    ):
        return None, "Saved guidance input fingerprints must be SHA-256 digests."
    return {key: value.lower() for key, value in components.items()}, None


def inspect_guidance_inputs(
    plan: dict[str, Any],
    *,
    details: ProjectDetails,
    config_path: ConfigSource | None,
    sot_path: Path | None = None,
) -> GuidanceInputCheck:
    """Compare saved input fingerprints without rewriting guidance or fetching a source."""
    recorded, error = _recorded_components(plan)
    if recorded is None:
        assert error is not None
        return GuidanceInputCheck(state="unverifiable", errors=(error,))

    observed: dict[str, str] = {
        check.name: check.observed_sha256
        for check in details.artifact_checks
        if check.observed_sha256 is not None
    }
    errors = []
    try:
        source = resolve_active_sot_path(
            sot_path if sot_path is not None else details.spec.sot_path
        )
        if validate_sot(source):
            raise ValueError("Invalid source")
        observed["source_tags"] = _digest(tag_counts(extract_tags(load_sot(source))))
    except (OSError, ValueError, yaml.YAMLError, SotVersionError, RecursionError):
        errors.append("Current source tag inputs could not be inspected.")

    configuration = None
    if config_path is not None:
        try:
            configuration = read_config(config_path)
        except (OSError, ValueError, yaml.YAMLError):
            errors.append("Current guidance configuration could not be inspected.")
    if configuration is not None:
        try:
            observed["variant_catalog"] = _catalog_digest(
                load_variants_from_config(configuration.path)
            )
        except (OSError, ValueError, yaml.YAMLError):
            errors.append("Current guidance variant catalog could not be inspected.")
        try:
            observed["default_variant"] = _digest(resolve_default_variant(configuration))
        except ValueError:
            errors.append("Current default variant could not be inspected.")

    changed = tuple(
        key for key in _COMPONENTS if key in observed and observed[key] != recorded[key]
    )
    unavailable = tuple(key for key in _COMPONENTS if key not in observed)
    return GuidanceInputCheck(
        state="changed" if changed else "unverifiable" if unavailable else "matches_inputs",
        changed=changed,
        unavailable=unavailable,
        errors=tuple(errors),
    )
