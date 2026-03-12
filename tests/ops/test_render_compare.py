"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_render_compare.py

Tests rendered PDF visual comparison behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from cvworkbench.ops.render_compare import RenderCompareError, compare_rendered_pdfs


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  runs: ../var/runs\n")
    return config_path


def _write_run(root: Path, run_id: str) -> Path:
    run_dir = root / "var" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cv.pdf").write_bytes(b"%PDF-1.4\n")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-12T00:00:00+00:00",
                "formats": ["pdf"],
                "outputs": {"pdf": "cv.pdf"},
                "variant": {"id": "base"},
            }
        )
        + "\n"
    )
    return run_dir


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
    width = 1
    height = 1
    raw = b"\x00" + bytes(color)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(png)


def test_compare_rendered_pdfs_writes_report_and_summary(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    run_a = _write_run(tmp_path, "2026-03-12T00-00-00Z")
    run_b = _write_run(tmp_path, "2026-03-12T00-05-00Z")

    def _fake_rasterize(pdf_path: Path, out_dir: Path, *, dpi: int) -> tuple[Path, ...]:
        out_dir.mkdir(parents=True, exist_ok=False)
        page_one = out_dir / "page-001.png"
        page_two = out_dir / "page-002.png"
        _write_png(page_one, (255, 0, 0))
        if pdf_path.parent.name == run_a.name:
            _write_png(page_two, (0, 0, 255))
        else:
            _write_png(page_two, (0, 255, 0))
        return (page_one, page_two)

    monkeypatch.setattr("cvworkbench.ops.render_compare._rasterize_pdf", _fake_rasterize)

    result = compare_rendered_pdfs(
        config_path=config_path,
        run_a=str(run_a),
        run_b=str(run_b),
    )

    assert result.status == "different"
    assert result.report_path.exists()
    assert result.summary_path.exists()
    summary = json.loads(result.summary_path.read_text())
    assert summary["identical_pages"] == 1
    assert summary["different_pages"] == 1
    assert "page-002.png" in result.report_path.read_text()


def test_compare_rendered_pdfs_requires_pdf_output(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run_dir = tmp_path / "var" / "runs" / "2026-03-12T00-00-00Z"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-12T00:00:00+00:00",
                "formats": ["md"],
                "outputs": {"md": "cv.md"},
                "variant": {"id": "base"},
            }
        )
        + "\n"
    )

    with pytest.raises(RenderCompareError, match="PDF output"):
        compare_rendered_pdfs(
            config_path=config_path,
            run_a=str(run_dir),
            run_b=str(run_dir),
        )


def test_compare_rendered_pdfs_preserves_project_run_id_for_relative_paths(
    tmp_path: Path, monkeypatch
) -> None:
    _write_config(tmp_path)
    _write_run(tmp_path, "2026-03-12T00-00-00Z")
    _write_run(tmp_path, "projects/job/2026-03-12T00-05-00Z")

    def _fake_rasterize(pdf_path: Path, out_dir: Path, *, dpi: int) -> tuple[Path, ...]:
        out_dir.mkdir(parents=True, exist_ok=False)
        page = out_dir / "page-001.png"
        _write_png(page, (255, 0, 0))
        return (page,)

    monkeypatch.setattr("cvworkbench.ops.render_compare._rasterize_pdf", _fake_rasterize)
    monkeypatch.chdir(tmp_path)

    result = compare_rendered_pdfs(
        config_path=Path("config/workbench.yaml"),
        run_a=Path("var/runs/2026-03-12T00-00-00Z"),
        run_b=Path("var/runs/projects/job/2026-03-12T00-05-00Z"),
    )

    assert result.run_b.run_id == "projects/job/2026-03-12T00-05-00Z"
