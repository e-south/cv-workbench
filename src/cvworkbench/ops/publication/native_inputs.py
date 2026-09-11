"""Capture and verify an explicit native build against its current source inputs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import ConfigSnapshot
from cvworkbench.inputs.native_run import capture_native_run
from cvworkbench.ops.publication.artifact import validate_publish_policy
from cvworkbench.ops.publication.pdf import PublicPdfError, _safe_public_uri
from cvworkbench.ops.publication.policy import PublishConfig, parse_publish_config
from cvworkbench.ops.publication.record import FileStamp, PreparationInputChangedError, stamp_file
from cvworkbench.variants import Variant


@dataclass(frozen=True)
class NativeBuildInputs:
    variant: Variant
    policy: PublishConfig
    person: dict[str, Any] = field(repr=False)
    pdf: bytes = field(repr=False)
    allowed_links: frozenset[str]
    stamps: dict[str, FileStamp]
    source_files: dict[str, FileStamp]

    def verify_current(self) -> None:
        for stamp in [*self.stamps.values(), *self.source_files.values()]:
            try:
                current = stamp_file(Path(stamp.path))
            except OSError as exc:
                raise PreparationInputChangedError(
                    "Native publication input disappeared; prepare again"
                ) from exc
            if current != stamp:
                raise PreparationInputChangedError(
                    "Native publication input changed; prepare again"
                )


def capture_native_build(
    *,
    configuration: ConfigSnapshot,
    run_path: Path,
    variant_id: str,
    publish_config_path: Path,
    sot_path: Path,
) -> NativeBuildInputs:
    try:
        captured = capture_native_run(
            configuration=configuration,
            run_path=run_path,
            variant_id=variant_id,
            sot_path=sot_path,
            formats=("md", "pdf"),
        )
    except ValueError as exc:
        raise PublicPdfError(str(exc)) from exc
    variant = captured.variant
    policy_bytes = publish_config_path.read_bytes()
    policy = parse_publish_config(yaml.safe_load(policy_bytes))
    validate_publish_policy(variant, policy)
    if variant.id not in policy.variants or "pdf" not in variant.outputs:
        raise PublicPdfError("Native publication variant is not an eligible PDF publication")
    names = {"output:md": "rendered_markdown", "output:pdf": "exported_pdf"}
    stamps = {
        names.get(name, name): FileStamp(path=str(path), sha256=sha)
        for name, (path, sha) in captured.stamps.items()
    }
    stamps["policy"] = FileStamp(
        path=str(publish_config_path.resolve()), sha256=hashlib.sha256(policy_bytes).hexdigest()
    )
    source_files = {
        name: FileStamp(path=str(path), sha256=sha)
        for name, (path, sha) in captured.source_files.items()
    }
    stamps["person"] = source_files["person.yaml"]
    person = captured.source_data["person"]
    links = markdown_links(captured.outputs["md"], person=person, variant=variant)
    return NativeBuildInputs(
        variant, policy, person, captured.outputs["pdf"], links, stamps, source_files
    )


def markdown_links(content: bytes, *, person: dict[str, Any], variant: Variant) -> frozenset[str]:
    """Allow only links declared by the selected Markdown, never PDF annotations."""
    result = subprocess.run(
        ["pandoc", "--from=markdown", "--to=json"], input=content, capture_output=True, check=False
    )
    if result.returncode:
        raise PublicPdfError("Cannot parse native Markdown link declarations")
    links = set()

    def visit(node):
        if isinstance(node, dict):
            if node.get("t") == "Link":
                uri = node["c"][-1][0]
                if not _safe_public_uri(uri, person, variant, allow_email=True):
                    raise PublicPdfError("Native Markdown declares an unsafe public link")
                links.add(uri)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(json.loads(result.stdout))
    return frozenset(links)
