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

import pytest


@pytest.mark.parametrize("owner", ["ops", "workspace"])
def test_project_api_exposes_owned_implementations_without_reverse_imports(owner) -> None:
    module_name = f"cvworkbench.{owner}.projects"
    package = Path(__file__).resolve().parents[2] / f"src/cvworkbench/{owner}/projects"
    api = ast.parse((package / "__init__.py").read_text())
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in ast.walk(api)
    )
    for node in api.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").startswith(module_name + ".")
            assert all(alias.name != "*" for alias in node.names)

    violations = []
    for path in package.glob("*.py"):
        if path.name == "__init__.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = resolve_name("." * node.level + module, module_name)
                imports = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            elif isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            else:
                continue
            if module_name in imports:
                violations.append(f"{path.name}:{node.lineno}")
    assert not violations, f"Project owners must not import the public entrypoint: {violations}"


def test_cli_entrypoint_only_registers_commands_and_groups() -> None:
    package_root = Path(__file__).resolve().parents[2] / "src/cvworkbench/cli"
    entrypoint = package_root / "app.py"
    tree = ast.parse(entrypoint.read_text())
    definitions = [
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    ]
    assert not definitions, f"Command implementation belongs in its owner: {definitions}"
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").startswith(("__future__", "cvworkbench.cli.commands"))
        if isinstance(node, ast.Import):
            assert all(alias.name == "typer" for alias in node.names)


def test_command_owners_do_not_import_the_entrypoint() -> None:
    package_root = Path(__file__).resolve().parents[2] / "src/cvworkbench/cli"
    violations = []
    for path in (package_root / "commands").rglob("*.py"):
        relative = path.relative_to(package_root)
        package = ".".join(("cvworkbench", "cli", *relative.parent.parts))
        for node in ast.walk(ast.parse(path.read_text())):
            imported = []
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = resolve_name("." * node.level + module, package)
                imported = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            elif isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            if any(name in {"cvworkbench.cli", "cvworkbench.cli.app"} for name in imported):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Command registration must remain one-way: {violations}"


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
