"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/test_boundaries.py

Enforces import direction between adapters, workspace inspection, and domain code.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import ast
from importlib.util import resolve_name
from pathlib import Path


def test_package_imports_respect_workspace_and_adapter_boundaries() -> None:
    package_root = Path(__file__).resolve().parents[2] / "src" / "cvworkbench"
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(package_root)
        owner = relative.parts[0]
        forbidden = [] if owner == "cli" else ["cvworkbench.cli"]
        if owner == "workspace":
            forbidden += ["cvworkbench.dev", "typer", "rich"]
        if owner in {"build", "inputs"}:
            forbidden += ["cvworkbench.ops", "cvworkbench.dev", "cvworkbench.workspace"]
        if owner == "ops":
            forbidden += ["cvworkbench.workspace"]

        package = ".".join(("cvworkbench", *relative.parent.parts))
        for node in ast.walk(ast.parse(path.read_text())):
            imports: list[str] = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = resolve_name("." * node.level + module, package)
                imports = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            for imported in imports:
                if any(
                    imported == target or imported.startswith(target + ".") for target in forbidden
                ):
                    violations.append(f"{relative}:{node.lineno}: {imported}")

    assert not violations, "\n".join(violations)
