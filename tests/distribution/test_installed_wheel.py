"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/distribution/test_installed_wheel.py

Exercises the installed distribution in a clean workspace without checkout imports.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import site
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_installed_wheel_initializes_and_renders_outside_checkout(tmp_path: Path) -> None:
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CVW_TEMPLATE_DIR"):
        environment.pop(key, None)
    evidence = tmp_path / "evidence"
    evidence.mkdir()

    def run(name: str, argv: list[str], cwd: Path = tmp_path) -> str:
        result = subprocess.run(
            argv, cwd=cwd, env=environment, capture_output=True, text=True, timeout=180
        )
        (evidence / f"{name}.stdout").write_text(result.stdout)
        (evidence / f"{name}.stderr").write_text(result.stderr)
        assert result.returncode == 0, f"{name}: {result.stderr}\n{result.stdout}"
        return result.stdout

    wheel_dir = tmp_path / "dist"
    run("wheel", ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)], ROOT)
    (wheel,) = wheel_dir.glob("*.whl")
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "cvworkbench_data/filters/select.lua" in names
        assert "cvworkbench_data/workspace/sot.sample/person.yaml" in names
        assert not any(name.startswith(("local/", "var/", "config/")) for name in names)

    runtime = tmp_path / "runtime"
    run("venv", ["uv", "venv", "--python", sys.executable, str(runtime)])
    binary = runtime / ("Scripts" if os.name == "nt" else "bin")
    python = binary / ("python.exe" if os.name == "nt" else "python")
    cvw = binary / ("cvw.exe" if os.name == "nt" else "cvw")
    run("install", ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)])
    # Reuse the locked test environment's dependencies without re-fetching them.
    # Append their directories after the installed package; do not process their
    # editable .pth files or add the checkout to the child interpreter's path.
    dependencies = repr(site.getsitepackages())
    bootstrap = f"import sys; sys.path.extend({dependencies}); "
    launch = [
        str(python),
        "-I",
        "-c",
        bootstrap + f"import runpy; runpy.run_path({str(cvw)!r}, run_name='__main__')",
    ]
    environment["PATH"] = str(binary) + os.pathsep + environment.get("PATH", "")
    imported = run(
        "import",
        [str(python), "-I", "-c", bootstrap + "import cvworkbench; print(cvworkbench.__file__)"],
    ).strip()
    assert Path(imported).is_relative_to(runtime)
    for resource in ("filters", "workspace"):
        path = run(
            resource,
            [
                str(python),
                "-I",
                "-c",
                bootstrap
                + "from cvworkbench.resources import distribution_path; "
                + f"print(distribution_path({resource!r}))",
            ],
        ).strip()
        assert Path(path).is_relative_to(runtime)

    workspace = tmp_path / "workspace"
    run("init", [*launch, "init", "--workspace", str(workspace), "--sample-default", "--json"])
    policy = yaml.safe_load((workspace / "config/publish.yaml").read_text())
    site_config = yaml.safe_load((workspace / "config/site-sync.yaml").read_text())
    assert policy["publish"].get("approved_visual_fingerprint_sha256") is None
    assert site_config["site"].get("repo_path") is None
    run("doctor", [*launch, "doctor", "--json"], workspace)
    context = json.loads(run("context", [*launch, "context", "--json"], workspace))
    assert context["sot"]["status"] == "ready"
    assert str(ROOT) not in json.dumps(context)
    for item in context["recommended_workflows"]:
        assert item["command"].startswith("cvw ")

    for variant, output in (("base", "cv"), ("cover-letter", "cover-letter")):
        run(
            variant,
            [*launch, "build", "--variant", variant, "--format", "md,pdf,docx", "--json"],
            workspace,
        )
        target = workspace / "var/dist" / variant
        assert (target / f"{output}.pdf").read_bytes().startswith(b"%PDF-")
        assert (target / f"{output}.docx").read_bytes().startswith(b"PK")
        assert "Alex Example" in (target / f"{output}.md").read_text()
    run("preview", [*launch, "preview", "--once", "--variant", "base", "--json"], workspace)
    assert list((workspace / "var").rglob("cv.html"))

    # Reinitialization must preserve the user's configuration and theme edits.
    config = workspace / "config/workbench.yaml"
    config.write_text(config.read_text().replace("../sot.sample", "../local/my-profile"))
    theme = workspace / "build/themes/default/styles/html/modern.css"
    theme.write_text(theme.read_text() + "\n/* Workspace customization. */\n")
    before = {path: path.read_bytes() for path in (config, theme)}
    run("reinit", [*launch, "init", "--sample-default", "--json"], workspace)
    assert all(path.read_bytes() == contents for path, contents in before.items())
