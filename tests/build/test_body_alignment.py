"""Optional list alignment never changes heading/date layout or selected text."""

import subprocess
from pathlib import Path

import pytest
import yaml
from lxml import html

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.rendering import resolve_filter_paths
from cvworkbench.variants import parse_variant


def render(tmp_path, setting=None, *, format="html5"):
    source = {
        "skills": {
            "skills": [{"id": "craft", "name": "Craft", "keywords": ["Optics", "Fabrication"]}]
        },
        "experience": {
            "roles": [
                {
                    "id": "studio",
                    "title": "Designer",
                    "company": "Example Studio",
                    "start": 2030,
                    "bullets": [{"id": "optics", "text": "Designed optical exhibits."}],
                }
            ]
        },
    }
    variant = parse_variant({"variant": {"id": "base", "outputs": ["md"]}})
    metadata = {
        "cvw-aligned-entries": True,
        "cvw-concise-entries": True,
        "cvw-entry-structure": True,
    }
    if setting is not None:
        metadata["cvw-justify-lists"] = setting
    md = "---\n" + yaml.safe_dump(metadata) + "---\n" + build_markdown(source, variant)
    args = ["pandoc", "-t", format]
    for path in resolve_filter_paths(Path(__file__).resolve().parents[2] / "build/filters"):
        args += ["--lua-filter", str(path)]
    return subprocess.run(args, input=md, text=True, capture_output=True, check=True).stdout


def test_justified_lists_are_opt_in_and_preserve_heading_and_date(tmp_path):
    baseline = html.fromstring("<main>" + render(tmp_path) + "</main>")
    aligned = html.fromstring("<main>" + render(tmp_path, ["skills", "experience"]) + "</main>")
    assert " ".join(aligned.text_content().split()) == " ".join(baseline.text_content().split())
    assert not baseline.xpath('//*[contains(@class,"body-justified")]')
    selected = aligned.xpath('//*[contains(@class,"body-justified")]')
    assert len(selected) == 2
    assert all(
        not item.xpath('.//*[contains(@class,"entry-heading") or contains(@class,"entry-date")]')
        for item in selected
    )
    assert set(aligned.xpath("//@id")) == set(baseline.xpath("//@id"))
    assert "Designed optical exhibits." in aligned.get_element_by_id("role-studio").text_content()
    assert len(aligned.xpath('//*[contains(@class,"entry-date")]')) == 1


def test_justification_preserves_native_writer_hooks(tmp_path):
    latex = render(tmp_path, ["skills", "experience"], format="latex")
    assert latex.count("\\cvwjustifiedlist") == 4  # guard and invocation for each list
    native = render(tmp_path, ["skills", "experience"], format="native")
    assert "Justified List" in native and "Justified Entry Bullet" in native


@pytest.mark.parametrize("setting", [True, ["unknown-section"]])
def test_unknown_alignment_settings_fail_instead_of_styling_everything(tmp_path, setting):
    with pytest.raises(subprocess.CalledProcessError, match="pandoc"):
        render(tmp_path, setting)
