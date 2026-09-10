"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_planning.py

Verify build planning is read-only and execution consumes its captured settings.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json

import yaml

from cvworkbench.build.pipeline import execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.ops.scaffold import init_project


def test_build_plan_is_read_only_and_reuses_configuration_during_execution(tmp_path, capsys):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    initial_config = config.read_bytes()
    source = tmp_path / "sot.sample"
    person_path = source / "person.yaml"
    person = yaml.safe_load(person_path.read_text())
    person["name"] = "PRIVATE PLAN FIXTURE"
    person_path.write_text(yaml.safe_dump(person))
    before = {
        p.relative_to(tmp_path): p.read_bytes() if p.is_file() else None
        for p in tmp_path.rglob("*")
    }

    plan = plan_build(
        sot_path=source, config_path=config, variant_id="base", formats=["md", "html"]
    )

    assert before == {
        p.relative_to(tmp_path): p.read_bytes() if p.is_file() else None
        for p in tmp_path.rglob("*")
    }
    assert "PRIVATE PLAN FIXTURE" in plan.markdown
    assert "PRIVATE PLAN FIXTURE" not in repr(plan)
    config.unlink()
    result = execute_build(plan)
    assert result.canonical_path.read_text() == plan.markdown
    assert "PRIVATE PLAN FIXTURE" in (result.dist_dir / "cv.html").read_text()
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["configuration"]["sha256"] == hashlib.sha256(initial_config).hexdigest()
    assert result.formats == ["md", "html"]
    assert capsys.readouterr() == ("", "")
