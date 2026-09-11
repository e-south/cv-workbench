"""Preview and apply exact local document promotion using recoverable file writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.ops.documents.locking import promotion_lock
from cvworkbench.ops.documents.records import (
    DocumentError,
    PromotionRequest,
    digest,
    encode,
    library_path,
    load_receipts,
    read_json,
    regular_path,
)
from cvworkbench.ops.documents.sources import capture_source
from cvworkbench.storage import replace_files_atomically


@dataclass(frozen=True)
class PromotionPlan:
    root: Path
    request_path: Path
    payload: dict

    @property
    def sha256(self) -> str:
        return digest(encode(self.payload))


def plan_promotion(*, request_path: Path, root: Path) -> PromotionPlan:
    root = root.resolve(strict=True)
    request_path = regular_path(request_path)
    request_bytes = request_path.read_bytes()
    try:
        request = PromotionRequest.model_validate(read_json(request_bytes))
    except ValueError as exc:
        raise DocumentError("Invalid promotion request; see document-library contract") from exc
    if (request.document.audience == "public") != (request.source.kind == "publication"):
        raise DocumentError("Public documents require the publication review gate")
    tips, records = load_receipts(root)
    previous = tips.get(request.document.id)
    files, retired = [], []
    for transfer in request.files:
        origin = regular_path(request_path.parent / transfer.source)
        destination = library_path(root, transfer.destination, "current")
        if origin.suffix.lower() != destination.suffix.lower():
            raise DocumentError("Promotion must preserve the artifact extension")
        if origin == destination:
            raise DocumentError("Promotion source and destination must differ")
        files.append(
            {
                "source": str(origin),
                "destination": transfer.destination,
                "sha256": digest(origin.read_bytes()),
                "previous_sha256": digest(destination.read_bytes())
                if destination.exists()
                else None,
            }
        )
    destinations = [item["destination"] for item in files]
    source = capture_source(request.source, request_path.parent, [Path(f["source"]) for f in files])
    if len(set(destinations)) != len(destinations):
        raise DocumentError("Promotion destinations must be unique")
    for tip in tips.values():
        if tip["document"]["id"] != request.document.id and set(destinations) & {
            f["destination"] for f in tip["files"]
        }:
            raise DocumentError("Destination already belongs to another document")
    if previous:
        old = {f["destination"]: f["sha256"] for f in previous["files"]}
        if any(f["destination"] not in old and f["previous_sha256"] is not None for f in files):
            raise DocumentError("Unrecorded current files cannot be overwritten")
        if (
            any(f["previous_sha256"] != old.get(f["destination"]) for f in files)
            and not request.replace_modified_current
        ):
            raise DocumentError(
                "Current files changed after promotion; preserve manual edits first"
            )
        for destination in sorted(old.keys() - set(destinations)):
            path = library_path(root, destination, "current")
            if not path.exists():
                raise DocumentError("Missing current file; restore it before changing the file set")
            sha = digest(path.read_bytes())
            if sha != old[destination] and not request.replace_modified_current:
                raise DocumentError(
                    "Current files changed after promotion; preserve manual edits first"
                )
            retired.append({"destination": destination, "sha256": sha})
    elif any(f["previous_sha256"] is not None for f in files):
        raise DocumentError(
            "Unrecorded current files cannot be overwritten; archive them or choose an unused destination"
        )
    modified_paths = {
        str(root / name) for name in [*destinations, *(f["destination"] for f in retired)]
    }
    if modified_paths & {
        request_path.as_posix(),
        *source.stamps.keys(),
        *(f["source"] for f in files),
    }:
        raise DocumentError("Promotion outputs cannot overwrite their source or request")
    return PromotionPlan(
        root,
        request_path,
        {
            "schema_version": 1,
            "root": str(root),
            "request_path": str(request_path),
            "request_sha256": digest(request_bytes),
            "document": request.document.model_dump(),
            "source": source.model_dump(),
            "files": files,
            "retired_files": retired,
            "previous_receipt": previous["receipt_path"] if previous else None,
            "history": {
                path: digest(content)
                for path, content in records.items()
                if Path(path).parent.name == request.document.id
            },
        },
    )


def apply_promotion(plan: PromotionPlan, *, reviewed_sha256: str) -> Path:
    if reviewed_sha256 != plan.sha256:
        raise DocumentError("Promotion plan does not match the reviewed hash")
    current = plan_promotion(request_path=plan.request_path, root=plan.root)
    if current.sha256 != reviewed_sha256:
        raise DocumentError("Promotion inputs or destinations changed after review")
    with promotion_lock(plan.root):
        current = plan_promotion(request_path=plan.request_path, root=plan.root)
        if current.sha256 != reviewed_sha256:
            raise DocumentError("Promotion inputs or destinations changed after review")
        return _commit(current)


def _commit(current: PromotionPlan) -> Path:
    plan = current
    writes, expected, previous_files, deletions = [], {}, [], []
    for item in [*current.payload["retired_files"], *current.payload["files"]]:
        destination = library_path(plan.root, item["destination"], "current")
        old = destination.read_bytes() if destination.exists() else None
        expected[destination] = old
        if old is not None:
            archived = f"archive/promotions/{current.payload['document']['id']}/{current.sha256}/{item['destination']}"
            archive = library_path(plan.root, archived, "archive")
            writes.append((archive, old))
            expected[archive] = None
            previous_files.append(
                {"destination": item["destination"], "archive": archived, "sha256": digest(old)}
            )
        if "source" not in item:
            deletions.append(destination)
            continue
        content = regular_path(Path(item["source"])).read_bytes()
        if digest(content) != item["sha256"]:
            raise DocumentError("Promotion artifact changed after review")
        writes.append((destination, content))
    receipt_path = library_path(
        plan.root,
        f"records/promotions/{current.payload['document']['id']}/{current.sha256}.json",
        "records",
    )
    receipt = {
        "schema_version": 1,
        "plan": current.payload,
        "plan_sha256": current.sha256,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "previous_files": previous_files,
    }
    writes.append((receipt_path, encode(receipt)))
    expected[receipt_path] = None
    replace_files_atomically(
        writes,
        delete_paths=deletions,
        expected_contents=expected,
        file_modes={p: 0o600 for p, _ in writes},
    )
    return receipt_path
