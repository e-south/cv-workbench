"""Capture publication inputs into private copies with original-file provenance."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from cvworkbench.ops.publication.record import FileStamp, PreparationInputs


class PublicationInputError(ValueError):
    pass


@dataclass(frozen=True)
class PublicationInputCopies:
    authored_source: Path
    exported_pdf: Path
    policy: Path
    variant_config: Path
    person: Path
    stamps: PreparationInputs


@contextmanager
def capture_publication_inputs(
    *,
    authored_source: Path,
    source_pdf: Path,
    policy_path: Path,
    variant_path: Path,
    person_path: Path,
) -> Iterator[PublicationInputCopies]:
    """Process captured bytes, then remove this operation's private input copies."""
    sources = {
        "authored_source": authored_source,
        "exported_pdf": source_pdf,
        "policy": policy_path,
        "variant_config": variant_path,
        "person": person_path,
    }
    with TemporaryDirectory(prefix="cvw-publication-inputs-") as temporary:
        staged = {}
        stamps = {}
        for name, source in sources.items():
            try:
                original = source.resolve()
                if not original.is_file():
                    raise PublicationInputError(f"Publication {name} must be a regular file")
                content = original.read_bytes()
                target = Path(temporary) / name / source.name
                target.parent.mkdir(mode=0o700)
                target.write_bytes(content)
                target.chmod(0o600)
            except OSError as exc:
                raise PublicationInputError(f"Publication {name} could not be captured") from exc
            staged[name] = target
            stamps[name] = FileStamp(path=str(original), sha256=sha256(content).hexdigest())
        yield PublicationInputCopies(**staged, stamps=PreparationInputs(**stamps))
