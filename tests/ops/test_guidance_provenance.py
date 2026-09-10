"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_guidance_provenance.py

Verify saved guidance input provenance against actual captured and current inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from cvworkbench.config import read_config
from cvworkbench.dev.preview import PreviewController
from cvworkbench.ops import projects
from cvworkbench.ops.projects import workflow
from cvworkbench.ops.scaffold import init_project


def _project(root):
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    result = projects.guide_project(config_path=config, job_file=job, variant_id="base")
    return config, result


def _check(config, result):
    details = projects.load_project_details(result.paths.project_dir)
    plan, error = projects.load_project_plan(details)
    assert error is None
    return projects.inspect_guidance_inputs(plan, details=details, config_path=config)


def test_guidance_records_consumed_job_bytes_and_matching_inputs(tmp_path):
    config, result = _project(tmp_path)
    provenance = result.proposal_plan["provenance"]

    assert provenance["schema"] == "cvw-guidance-inputs-v1"
    assert provenance["algorithm"] == "tag-overlap-v1"
    assert set(provenance["components"]) == {
        "extracted_text",
        "signals",
        "source_tags",
        "variant_catalog",
        "default_variant",
    }
    for key, path in [
        ("extracted_text", result.paths.extracted_path),
        ("signals", result.paths.signals_path),
    ]:
        assert provenance["components"][key] == hashlib.sha256(path.read_bytes()).hexdigest()
    check = _check(config, result)
    assert check.state == "matches_inputs"
    assert check.changed == ()
    assert check.unavailable == ()


@pytest.mark.parametrize(
    "component", ["extracted_text", "signals", "source_tags", "variant_catalog", "default_variant"]
)
def test_guidance_detects_changes_independently_of_current_artifact_records(tmp_path, component):
    config, result = _project(tmp_path)
    plan_path = result.paths.job_dir / "proposal-plan.json"
    original_plan = plan_path.read_bytes()
    if component in {"extracted_text", "signals"}:
        path = (
            result.paths.extracted_path
            if component == "extracted_text"
            else result.paths.signals_path
        )
        path.write_bytes(path.read_bytes() + b"\n")
        manifest = yaml.safe_load(result.paths.project_file.read_text())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if component == "extracted_text":
            manifest["project"]["job"]["extracted_hash"] = digest
        else:
            manifest["project"]["signals"]["hash"] = digest
        result.paths.project_file.write_text(yaml.safe_dump(manifest))
        assert all(
            item.state == "matches_record"
            for item in projects.inspect_project_artifacts(result.paths.project_dir)
        )
    elif component == "source_tags":
        path = tmp_path / "sot.sample/experience.yaml"
        data = yaml.safe_load(path.read_text())
        data["roles"][0]["bullets"][0]["tags"].append("new-tag")
        path.write_text(yaml.safe_dump(data))
    elif component == "variant_catalog":
        path = config.parent / "variants/base.yaml"
        data = yaml.safe_load(path.read_text())
        data["variant"]["include_tags"] = ["new-tag"]
        path.write_text(yaml.safe_dump(data))
    else:
        data = yaml.safe_load(config.read_text())
        data["variants"]["default"] = "cover-letter"
        config.write_text(yaml.safe_dump(data))

    check = _check(config, result)

    assert check.state == "changed"
    assert check.changed == (component,)
    assert check.unavailable == ()
    assert plan_path.read_bytes() == original_plan


@pytest.mark.parametrize(
    "provenance", [None, False, {}, {"schema": "future-private-fixture-marker"}]
)
def test_guidance_with_missing_or_invalid_provenance_is_unverifiable(tmp_path, provenance):
    config, result = _project(tmp_path)
    plan = result.paths.job_dir / "proposal-plan.json"
    payload = json.loads(plan.read_text())
    if provenance is None:
        payload.pop("provenance", None)
    else:
        payload["provenance"] = provenance
    plan.write_text(json.dumps(payload))

    check = _check(config, result)

    assert check.state == "unverifiable"
    assert check.errors
    assert "private-fixture-marker" not in str(check.errors)


def test_guidance_fingerprint_uses_job_bytes_consumed_before_intervening_edit(
    tmp_path, monkeypatch
):
    original_read = Path.read_bytes
    captured = {}

    def change_after_read(path):
        content = original_read(path)
        if path.name == "extracted.txt" and "projects" in path.parts and path not in captured:
            captured[path] = content
            path.write_bytes(b"intervening-private-fixture-marker\n")
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", change_after_read)
        _, result = _project(tmp_path)

    assert captured
    original = captured[result.paths.extracted_path]
    assert (
        result.proposal_plan["provenance"]["components"]["extracted_text"]
        == hashlib.sha256(original).hexdigest()
    )
    assert "intervening-private-fixture-marker" not in json.dumps(result.proposal_plan)


@pytest.mark.parametrize(
    "missing", ["extracted_text", "signals", "source_tags", "variant_catalog", "configuration"]
)
def test_guidance_reports_unavailable_inputs_without_hiding_other_checks(tmp_path, missing):
    config, result = _project(tmp_path)
    if missing == "extracted_text":
        result.paths.extracted_path.unlink()
    elif missing == "signals":
        result.paths.signals_path.unlink()
    elif missing == "source_tags":
        (tmp_path / "sot.sample/person.yaml").unlink()
    elif missing == "variant_catalog":
        (config.parent / "variants/base.yaml").write_text("variant: [private-fixture-marker")
    else:
        config.unlink()

    check = _check(config, result)

    assert check.state == "unverifiable"
    assert check.changed == ()
    assert check.unavailable == (
        ("variant_catalog", "default_variant") if missing == "configuration" else (missing,)
    )
    assert "private-fixture-marker" not in str(check.errors)


def test_guidance_ignores_prose_and_render_changes_outside_ranking_inputs(tmp_path):
    config, result = _project(tmp_path)
    path = tmp_path / "sot.sample/experience.yaml"
    data = yaml.safe_load(path.read_text())
    data["roles"][0]["bullets"][0]["text"] += " Revised wording."
    path.write_text(yaml.safe_dump(data))
    variant = config.parent / "variants/base.yaml"
    data = yaml.safe_load(variant.read_text())
    data["variant"]["render"] = {"style_preset": "compact"}
    variant.write_text(yaml.safe_dump(data))

    assert _check(config, result).state == "matches_inputs"


@pytest.mark.parametrize("mutation", ["algorithm", "digest", "missing", "extra"])
def test_guidance_rejects_unsupported_or_malformed_fingerprints(tmp_path, mutation):
    config, result = _project(tmp_path)
    plan = result.paths.job_dir / "proposal-plan.json"
    payload = json.loads(plan.read_text())
    provenance = payload["provenance"]
    if mutation == "algorithm":
        provenance["algorithm"] = "private-fixture-marker"
    elif mutation == "digest":
        provenance["components"]["source_tags"] = False
    elif mutation == "missing":
        del provenance["components"]["source_tags"]
    else:
        provenance["components"]["private-fixture-marker"] = "0" * 64
    plan.write_text(json.dumps(payload))
    before = plan.read_bytes()

    check = _check(config, result)

    assert check.state == "unverifiable"
    assert check.errors
    assert "private-fixture-marker" not in str(check.errors)
    assert plan.read_bytes() == before


def test_guidance_preserves_known_changes_when_another_input_is_unavailable(tmp_path):
    config, result = _project(tmp_path)
    result.paths.extracted_path.write_text("changed job text\n")
    result.paths.signals_path.unlink()

    check = _check(config, result)

    assert check.state == "changed"
    assert check.changed == ("extracted_text",)
    assert check.unavailable == ("signals",)


def test_guidance_inspection_uses_an_explicit_configuration_snapshot(tmp_path):
    config, result = _project(tmp_path)
    captured = read_config(config)
    data = yaml.safe_load(config.read_text())
    data["variants"]["default"] = "cover-letter"
    config.write_text(yaml.safe_dump(data))

    assert _check(captured, result).state == "matches_inputs"
    assert _check(config, result).changed == ("default_variant",)


def test_preview_compares_guidance_with_the_selected_source_override(tmp_path):
    config, result = _project(tmp_path)
    source = tmp_path / "sot.sample"
    alternate = tmp_path / "alternate-source"
    shutil.copytree(source, alternate)
    experience = alternate / "experience.yaml"
    data = yaml.safe_load(experience.read_text())
    data["roles"][0]["bullets"][0]["tags"].append("new-tag")
    experience.write_text(yaml.safe_dump(data))
    controller = PreviewController(
        sot_base=source,
        config_path=config,
        variant_id=result.proposal_variant_id,
        theme_id="default",
        style_preset="modern",
        auto_pdf=False,
        project_dir=result.paths.project_dir,
        project_sot_override=alternate,
    )

    controller.build_once()

    state = controller.state_payload()["project_context"]["guidance_inputs"]
    assert state["state"] == "changed"
    assert state["changed"] == ["source_tags"]
    assert state["unavailable"] == []


@pytest.mark.parametrize("component", ["source_tags", "variant_catalog"])
def test_guidance_fingerprints_values_consumed_before_later_file_edits(
    tmp_path, monkeypatch, component
):
    _, reference = _project(tmp_path / "reference")
    function = "load_sot" if component == "source_tags" else "load_variants_from_config"
    original_load = getattr(workflow, function)

    def edit_after_load(path):
        captured = original_load(path)
        target = (
            path / "experience.yaml"
            if component == "source_tags"
            else path.parent / "variants/base.yaml"
        )
        data = yaml.safe_load(target.read_text())
        if component == "source_tags":
            data["roles"][0]["bullets"][0]["tags"].append("new-tag")
        else:
            data["variant"]["include_tags"] = ["new-tag"]
        target.write_text(yaml.safe_dump(data))
        return captured

    with monkeypatch.context() as patch:
        patch.setattr(workflow, function, edit_after_load)
        config, result = _project(tmp_path / "subject")

    assert (
        result.proposal_plan["provenance"]["components"][component]
        == reference.proposal_plan["provenance"]["components"][component]
    )
    assert _check(config, result).changed == (component,)
