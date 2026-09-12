"""Document input diagnostics do not disclose malformed private YAML values."""

import pytest


def test_unexpected_cli_failure_does_not_dump_private_locals(monkeypatch):
    import subprocess
    import sys

    monkeypatch.setenv("CVW_PRIVACY_TEST_CANARY", "private-canary-not-for-diagnostics")
    probe = """
import os
from cvworkbench.cli import app
@app.command("privacy-probe")
def privacy_probe():
    private_value = os.environ["CVW_PRIVACY_TEST_CANARY"]
    raise RuntimeError("synthetic privacy test failure")
app(["privacy-probe"])
"""
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode != 0
    assert "synthetic privacy test failure" in result.stderr
    assert "private-canary-not-for-diagnostics" not in result.stdout + result.stderr


def test_source_yaml_diagnostic_omits_private_line(tmp_path):
    from cvworkbench.inputs.sot import _load_yaml

    with pytest.raises(ValueError) as error:
        _load_yaml(b"email: [private-canary@example.invalid\n", tmp_path / "person.yaml")
    assert "private-canary" not in str(error.value)


def test_variant_yaml_diagnostic_omits_private_line(tmp_path):
    from cvworkbench.variants import load_variant

    path = tmp_path / "variant.yaml"
    path.write_text("variant: [private-canary@example.invalid\n")
    with pytest.raises(ValueError) as error:
        load_variant(path)
    assert "private-canary" not in str(error.value)
