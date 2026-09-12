"""Capture manual and native authoring evidence without converting manual files."""

from pathlib import Path

from cvworkbench.config import read_config
from cvworkbench.inputs.native_run import capture_native_run
from cvworkbench.ops.documents.records import (
    AuthoredSource,
    DocumentError,
    NativeSource,
    PublicationSource,
    SourceEvidence,
    digest,
    regular_path,
)
from cvworkbench.ops.publication.record import (
    FileStamp,
    NativePreparationRecord,
    parse_preparation_record,
)
from cvworkbench.ops.publication.state import inspect_publication


def capture_source(
    source: AuthoredSource | NativeSource | PublicationSource, base: Path, artifacts: list[Path]
) -> SourceEvidence:
    if isinstance(source, AuthoredSource):
        path = regular_path(base / source.path)
        return SourceEvidence(
            kind="authored", path=str(path), stamps={str(path): digest(path.read_bytes())}
        )
    config = read_config(regular_path(base / source.config))
    if isinstance(source, PublicationSource):
        state = inspect_publication(config, source.variant)
        if state.state != "reviewed":
            raise DocumentError(f"Public promotion requires reviewed publication: {state.state}")
        pdf = regular_path(Path(state.pdf_path))
        if artifacts != [pdf]:
            raise DocumentError("Public promotion requires the exact prepared PDF only")
        preparation = regular_path(Path(state.preparation_path))
        record = parse_preparation_record(preparation.read_bytes())
        files = [
            preparation,
            regular_path(Path(state.receipt_path)),
            pdf,
            pdf.parent / "manifest.json",
        ]
        stamps = {str(p): digest(regular_path(p).read_bytes()) for p in files}
        for value in vars(record).values():
            if isinstance(value, FileStamp):
                stamps[value.path] = value.sha256
        if isinstance(record, NativePreparationRecord):
            stamps.update({s.path: s.sha256 for s in record.source_files.values()})
            path = Path(record.person.path).parent
            run_path = str(Path(record.run_manifest.path).parent)
        else:
            path = Path(record.authored_source.path)
            run_path = None
        return SourceEvidence(
            kind="publication",
            path=str(path),
            configuration=str(config.path),
            variant=source.variant,
            run_path=run_path,
            stamps=stamps,
        )
    run = (base / source.run).resolve()
    path = (base / source.path).resolve()
    formats = tuple(
        sorted(
            {
                "ats" if p.name.lower().endswith(".ats.txt") else p.suffix.lstrip(".").lower()
                for p in artifacts
            }
        )
    )
    captured = capture_native_run(
        configuration=config,
        run_path=run,
        variant_id=source.variant,
        sot_path=path,
        formats=formats,
    )
    if set(artifacts) != set(captured.output_paths.values()):
        raise DocumentError("Native promotion files must be the declared run outputs")
    return SourceEvidence(
        kind="native",
        path=str(path),
        configuration=str(config.path),
        variant=source.variant,
        run_path=str(run),
        stamps={
            str(p): sha for p, sha in [*captured.stamps.values(), *captured.source_files.values()]
        },
    )
