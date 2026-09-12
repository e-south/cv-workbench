"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/conftest.py

Give each test an isolated working directory and explicit sample-workspace inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from cvworkbench.ops.scaffold import init_project

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_working_directory(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Keep implicit paths outside both the checkout and caller's workspace."""
    root = tmp_path_factory.mktemp("working-directory")
    with pytest.MonkeyPatch.context() as environment:
        environment.chdir(root)
        yield root


@pytest.fixture
def sample_workspace(isolated_working_directory: Path) -> Path:
    """Use current public samples with neutral, workspace-local scaffold settings."""
    root = isolated_working_directory
    for relative in ("sot.sample", "config/variants", "build/themes"):
        shutil.copytree(ROOT / relative, root / relative)
    with pytest.MonkeyPatch.context() as environment:
        environment.delenv("CVW_TEMPLATE_DIR", raising=False)
        init_project(root, sample_default=True)
    return root
