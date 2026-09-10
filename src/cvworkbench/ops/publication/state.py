"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/state.py

Inspects authored publication freshness and records hash-bound review declarations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cvworkbench.build.paths import output_path
from cvworkbench.config import (
    ConfigSource,
    read_config,
    resolve_publish_path,
    resolve_reviews_path,
    resolve_sot_path,
    resolve_variant_path,
)
from cvworkbench.ops.publication.artifact import validate_public_artifact, validate_publish_policy
from cvworkbench.ops.publication.pdf import PublicPdfError, validate_public_pdf
from cvworkbench.ops.publication.policy import PublishError, load_publish_config
from cvworkbench.ops.publication.record import (
    FileStamp,
    PreparationRecord,
    ReviewReceipt,
    hash_file,
    json_bytes,
)
from cvworkbench.storage import AtomicWriteError, replace_files_atomically
from cvworkbench.variants import load_variant

PublicationPhase = Literal[
    "unconfigured",
    "untracked",
    "missing",
    "stale_source",
    "stale_export",
    "stale_configuration",
    "invalid",
    "review_required",
    "reviewed",
]


class PublicationStateError(ValueError):
    pass


@dataclass(frozen=True)
class PublicationState:
    variant: str
    state: PublicationPhase = "unconfigured"
    reasons: tuple[str, ...] = ()
    authored_source: str | None = None
    exported_pdf: str | None = None
    pdf_path: str | None = None
    pdf_sha256: str | None = None
    preparation_path: str | None = None
    preparation_sha256: str | None = None
    review_path: str | None = None
    receipt_path: str | None = None


def inspect_publication(
    config_path: ConfigSource,
    variant_id: str,
    *,
    publish_config_path: Path | None = None,
    sot_path: Path | None = None,
) -> PublicationState:
    """Observe current bytes without creating files or interpreting inventory as approval."""
    state = PublicationState(variant=variant_id)
    try:
        if Path(variant_id).name != variant_id or variant_id in {"", ".", ".."}:
            raise ValueError("Publication variant must be a workspace variant identifier")
        configuration = read_config(config_path)
        directory = resolve_publish_path(configuration) / variant_id
        record_path = directory / "preparation.json"
        state = replace(
            state,
            preparation_path=str(record_path),
            receipt_path=str(directory / "review-receipt.json"),
        )
        if not record_path.is_file():
            phase = (
                "untracked" if directory.exists() and any(directory.iterdir()) else "unconfigured"
            )
            return replace(
                state, state=phase, reasons=("Prepare an explicit authored DOCX and PDF export.",)
            )
        record = PreparationRecord.model_validate_json(record_path.read_bytes())
        if record.variant != variant_id:
            raise ValueError("Preparation record variant does not match the selected variant")
        if (
            Path(record.authored_source.path).suffix.lower() != ".docx"
            or Path(record.exported_pdf.path).suffix.lower() != ".pdf"
        ):
            raise ValueError("Preparation record must identify a DOCX and PDF source pair")
        review_dir = resolve_reviews_path(configuration) / "publication" / record.pdf_sha256
        state = replace(
            state,
            authored_source=record.authored_source.path,
            exported_pdf=record.exported_pdf.path,
            pdf_sha256=record.pdf_sha256,
            preparation_sha256=hash_file(record_path),
            review_path=str(review_dir / "review.html"),
        )
        for stamp, phase in (
            (record.authored_source, "stale_source"),
            (record.exported_pdf, "stale_export"),
            (record.policy, "stale_configuration"),
            (record.variant_config, "stale_configuration"),
            (record.person, "stale_configuration"),
        ):
            problem = _changed_input(stamp)
            if problem:
                return replace(
                    state,
                    state="missing" if not Path(stamp.path).is_file() else phase,
                    reasons=(problem,),
                )
        policy_path = (publish_config_path or configuration.path.parent / "publish.yaml").resolve()
        variant_path = resolve_variant_path(variant_id, configuration).resolve()
        person_path = resolve_sot_path(sot_path, configuration).resolve() / "person.yaml"
        if (str(policy_path), str(variant_path), str(person_path)) != (
            record.policy.path,
            record.variant_config.path,
            record.person.path,
        ):
            return replace(
                state,
                state="stale_configuration",
                reasons=("Configured publication inputs have changed; prepare again.",),
            )
        variant = load_variant(variant_path)
        policy = load_publish_config(policy_path)
        pdf = output_path(directory, variant, "pdf")
        manifest = directory / "manifest.json"
        state = replace(state, pdf_path=str(pdf))
        if not pdf.is_file() or not manifest.is_file():
            return replace(
                state, state="missing", reasons=("Prepared PDF or manifest is missing.",)
            )
        if hash_file(pdf) != record.pdf_sha256 or hash_file(manifest) != record.manifest_sha256:
            raise ValueError("Prepared artifact or manifest changed after preparation")
        validate_publish_policy(variant, policy)
        validate_public_artifact(pdf, manifest, variant, policy)
        validate_public_pdf(pdf, variant=variant, publish=policy, sot_path=person_path.parent)
        for filename, digest in record.review_files.items():
            path = review_dir / filename
            if not path.is_file() or hash_file(path) != digest:
                raise ValueError(f"Review packet changed or is missing: {filename}; prepare again")
        if _receipt_matches(Path(state.receipt_path), state):
            return replace(state, state="reviewed")
        return replace(
            state,
            state="review_required",
            reasons=("Inspect the public PDF and record review of its exact hash.",),
        )
    except (OSError, ValueError, PublicPdfError, PublishError) as exc:
        return replace(state, state="invalid", reasons=(str(exc),))


def _changed_input(stamp: FileStamp) -> str | None:
    path = Path(stamp.path)
    if not path.is_file():
        return f"Publication input is missing: {path}"
    if hash_file(path) != stamp.sha256:
        return f"Publication input changed since preparation: {path}"
    return None


def _receipt_matches(path: Path, state: PublicationState) -> bool:
    if not path.is_file():
        return False
    try:
        receipt = ReviewReceipt.model_validate_json(path.read_bytes())
    except (OSError, ValueError):
        return False
    return (receipt.pdf_sha256, receipt.preparation_sha256) == (
        state.pdf_sha256,
        state.preparation_sha256,
    )


def record_publication_review(
    config_path: Path,
    variant_id: str,
    expected_pdf_sha256: str,
    *,
    publish_config_path: Path | None = None,
    sot_path: Path | None = None,
) -> PublicationState:
    """Record the caller's review declaration; never infer it from opening a packet."""
    state = inspect_publication(
        config_path, variant_id, publish_config_path=publish_config_path, sot_path=sot_path
    )
    if expected_pdf_sha256 != state.pdf_sha256:
        raise PublicationStateError("Review hash does not match the prepared PDF")
    if state.state not in {"review_required", "reviewed"}:
        raise PublicationStateError("Cannot record review: " + "; ".join(state.reasons))
    receipt = ReviewReceipt(
        schema_version=1,
        pdf_sha256=state.pdf_sha256,
        preparation_sha256=state.preparation_sha256,
        reviewed_at=datetime.now(timezone.utc),
    )
    try:
        replace_files_atomically(
            [(Path(state.receipt_path), json_bytes(receipt.model_dump(mode="json")))],
            file_modes={Path(state.receipt_path): 0o600},
        )
    except AtomicWriteError as exc:
        raise PublicationStateError(str(exc)) from exc
    return replace(state, state="reviewed", reasons=())
