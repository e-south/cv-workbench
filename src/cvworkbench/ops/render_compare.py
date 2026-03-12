"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/render_compare.py

Builds visual side-by-side comparisons for rendered PDF outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import struct
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.config import resolve_config_path, resolve_var_root
from cvworkbench.ops.runs import RunError, RunInfo, resolve_run


class RenderCompareError(RuntimeError):
    pass


@dataclass(frozen=True)
class PageVisualDiff:
    page: int
    image_a: Path | None
    image_b: Path | None
    hash_a: str | None
    hash_b: str | None
    size_a: tuple[int, int] | None
    size_b: tuple[int, int] | None
    identical: bool


@dataclass(frozen=True)
class RenderCompareResult:
    out_dir: Path
    report_path: Path
    summary_path: Path
    run_a: RunInfo
    run_b: RunInfo
    pdf_a: Path
    pdf_b: Path
    pages: tuple[PageVisualDiff, ...]
    status: str


def compare_rendered_pdfs(
    *,
    config_path: Path,
    run_a: str | Path,
    run_b: str | Path,
    out_dir: Path | None = None,
    dpi: int = 144,
) -> RenderCompareResult:
    config_path = resolve_config_path(config_path)
    run_info_a = _resolve_run_info(config_path, run_a)
    run_info_b = _resolve_run_info(config_path, run_b)
    pdf_a = _require_pdf_output(run_info_a)
    pdf_b = _require_pdf_output(run_info_b)
    target_dir = out_dir or _default_compare_dir(config_path, run_info_a.run_id, run_info_b.run_id)
    target_dir = target_dir.resolve()
    if target_dir.exists():
        raise RenderCompareError(f"Compare output already exists: {target_dir}")

    committed = False
    try:
        target_dir.mkdir(parents=True, exist_ok=False)
        images_a = _rasterize_pdf(pdf_a, target_dir / "a", dpi=dpi)
        images_b = _rasterize_pdf(pdf_b, target_dir / "b", dpi=dpi)
        pages = _build_page_diffs(images_a, images_b)
        status = (
            "identical"
            if len(images_a) == len(images_b) and all(page.identical for page in pages)
            else "different"
        )
        summary_path = target_dir / "summary.json"
        report_path = target_dir / "report.html"
        summary_payload = _summary_payload(
            target_dir=target_dir,
            run_a=run_info_a,
            run_b=run_info_b,
            pdf_a=pdf_a,
            pdf_b=pdf_b,
            pages=pages,
            status=status,
            dpi=dpi,
        )
        summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n")
        report_path.write_text(_build_html_report(summary_payload))
        committed = True
        return RenderCompareResult(
            out_dir=target_dir,
            report_path=report_path,
            summary_path=summary_path,
            run_a=run_info_a,
            run_b=run_info_b,
            pdf_a=pdf_a,
            pdf_b=pdf_b,
            pages=pages,
            status=status,
        )
    finally:
        if not committed and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)


def _resolve_run_info(config_path: Path, run: str | Path) -> RunInfo:
    candidate = Path(run)
    run_value: str | Path = candidate.resolve() if candidate.exists() else run
    try:
        return resolve_run(config_path, run_value)
    except RunError as exc:
        raise RenderCompareError(str(exc)) from exc


def _require_pdf_output(run: RunInfo) -> Path:
    output_name = run.outputs.get("pdf")
    if not isinstance(output_name, str) or not output_name.strip():
        raise RenderCompareError(f"Run does not include PDF output: {run.run_id}")
    pdf_path = (run.path / output_name).resolve()
    if not pdf_path.exists():
        raise RenderCompareError(f"Run PDF output is missing: {pdf_path}")
    return pdf_path


def _default_compare_dir(config_path: Path, run_id_a: str, run_id_b: str) -> Path:
    compare_root = resolve_var_root(config_path) / "compare"
    compare_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    slug_a = _slugify_run_id(run_id_a)
    slug_b = _slugify_run_id(run_id_b)
    return compare_root / f"{stamp}-{slug_a}-vs-{slug_b}"


def _slugify_run_id(run_id: str) -> str:
    cleaned = [char if char.isalnum() else "-" for char in run_id.lower()]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _rasterize_pdf(pdf_path: Path, out_dir: Path, *, dpi: int) -> tuple[Path, ...]:
    ghostscript = shutil.which("gs")
    if ghostscript is None:
        raise RenderCompareError("Ghostscript (`gs`) is required for visual compare")
    out_dir.mkdir(parents=True, exist_ok=False)
    pattern = out_dir / "page-%03d.png"
    result = subprocess.run(
        [
            ghostscript,
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=png16m",
            f"-r{dpi}",
            f"-sOutputFile={pattern}",
            str(pdf_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise RenderCompareError(f"Ghostscript failed for {pdf_path}: {detail}")
    pages = tuple(sorted(out_dir.glob("page-*.png")))
    if not pages:
        raise RenderCompareError(f"Ghostscript produced no page images for {pdf_path}")
    return pages


def _build_page_diffs(images_a: tuple[Path, ...], images_b: tuple[Path, ...]) -> tuple[PageVisualDiff, ...]:
    pages: list[PageVisualDiff] = []
    for index in range(max(len(images_a), len(images_b))):
        image_a = images_a[index] if index < len(images_a) else None
        image_b = images_b[index] if index < len(images_b) else None
        hash_a = _hash_file(image_a) if image_a is not None else None
        hash_b = _hash_file(image_b) if image_b is not None else None
        pages.append(
            PageVisualDiff(
                page=index + 1,
                image_a=image_a,
                image_b=image_b,
                hash_a=hash_a,
                hash_b=hash_b,
                size_a=_png_size(image_a) if image_a is not None else None,
                size_b=_png_size(image_b) if image_b is not None else None,
                identical=(image_a is not None and image_b is not None and hash_a == hash_b),
            )
        )
    return tuple(pages)


def _summary_payload(
    *,
    target_dir: Path,
    run_a: RunInfo,
    run_b: RunInfo,
    pdf_a: Path,
    pdf_b: Path,
    pages: tuple[PageVisualDiff, ...],
    status: str,
    dpi: int,
) -> dict[str, object]:
    def _rel(path: Path | None) -> str | None:
        if path is None:
            return None
        return path.relative_to(target_dir).as_posix()

    return {
        "status": status,
        "dpi": dpi,
        "run_a": {"run_id": run_a.run_id, "path": str(run_a.path), "pdf": str(pdf_a)},
        "run_b": {"run_id": run_b.run_id, "path": str(run_b.path), "pdf": str(pdf_b)},
        "page_count_a": sum(1 for page in pages if page.image_a is not None),
        "page_count_b": sum(1 for page in pages if page.image_b is not None),
        "identical_pages": sum(1 for page in pages if page.identical),
        "different_pages": sum(1 for page in pages if not page.identical),
        "pages": [
            {
                "page": page.page,
                "image_a": _rel(page.image_a),
                "image_b": _rel(page.image_b),
                "hash_a": page.hash_a,
                "hash_b": page.hash_b,
                "size_a": list(page.size_a) if page.size_a is not None else None,
                "size_b": list(page.size_b) if page.size_b is not None else None,
                "identical": page.identical,
            }
            for page in pages
        ],
    }


def _build_html_report(summary: dict[str, object]) -> str:
    pages = summary["pages"]
    assert isinstance(pages, list)
    page_html: list[str] = []
    for item in pages:
        assert isinstance(item, dict)
        page = int(item["page"])
        identical = bool(item["identical"])
        image_a = item.get("image_a")
        image_b = item.get("image_b")
        status_label = "identical" if identical else "different"
        page_html.append(
            "\n".join(
                [
                    f'<section class="page {"same" if identical else "diff"}">',
                    f"<h2>Page {page} <span>{status_label}</span></h2>",
                    '<div class="grid">',
                    _image_panel("A", image_a),
                    _image_panel("B", image_b),
                    "</div>",
                    "</section>",
                ]
            )
        )
    return "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>cvw compare</title>",
            "<style>",
            "body{font-family:ui-sans-serif,system-ui,sans-serif;margin:24px;background:#f5f4ef;color:#181611;}",
            "h1{margin:0 0 8px;} p.meta{margin:0 0 24px;color:#5d564b;}",
            ".page{padding:16px;border:1px solid #d7d1c4;background:#fff;margin:0 0 20px;border-radius:12px;}",
            ".page.diff{border-color:#b85c38;box-shadow:0 0 0 2px rgba(184,92,56,.08);}",
            ".page.same{border-color:#8ea17b;}",
            ".page h2{margin:0 0 12px;font-size:18px;display:flex;gap:10px;align-items:baseline;}",
            ".page h2 span{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#7a6f5d;}",
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;}",
            ".panel{border:1px solid #e7e1d4;border-radius:10px;padding:12px;background:#fbfaf6;}",
            ".panel h3{margin:0 0 10px;font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:#5d564b;}",
            ".panel img{width:100%;height:auto;display:block;border-radius:6px;background:#fff;}",
            ".missing{min-height:240px;display:grid;place-items:center;color:#8a7d68;border:1px dashed #d7d1c4;border-radius:6px;background:#fff;}",
            "</style></head><body>",
            "<h1>Rendered PDF Compare</h1>",
            (
                f"<p class='meta'>status={html.escape(str(summary['status']))} "
                f"| run_a={html.escape(str(summary['run_a']))} "
                f"| run_b={html.escape(str(summary['run_b']))}</p>"
            ),
            *page_html,
            "</body></html>",
        ]
    )


def _image_panel(label: str, rel_path: object) -> str:
    if not isinstance(rel_path, str):
        return (
            f"<div class='panel'><h3>{html.escape(label)}</h3>"
            "<div class='missing'>Missing page</div></div>"
        )
    return (
        f"<div class='panel'><h3>{html.escape(label)}</h3>"
        f"<img src='{html.escape(rel_path)}' alt='Run {html.escape(label)} page'></div>"
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RenderCompareError(f"Rasterized image is not a PNG: {path}")
    return struct.unpack(">II", header[16:24])
