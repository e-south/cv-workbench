"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/syncing.py

Synchronizes generated outputs into a site repository.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from cvworkbench.config import resolve_dist_path, resolve_variant_path
from cvworkbench.paths import output_path
from cvworkbench.publish import PublishError, load_publish_config
from cvworkbench.variants import load_variant


class SyncError(RuntimeError):
    pass


class _SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    repo_path: str
    publish_variant: str
    cv_markdown: str
    cv_pdf_dir: str
    cv_pdf_name: str
    cv_page: str
    cv_page_frontmatter_key: str


class _SiteSyncModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    site: _SiteConfig


@dataclass(frozen=True)
class SiteSyncConfig:
    repo_path: Path
    publish_variant: str
    cv_markdown: Path
    cv_pdf_dir: Path
    cv_pdf_name: str
    cv_page: Path
    cv_page_frontmatter_key: str


@dataclass(frozen=True)
class SyncPlan:
    copy_ops: list[tuple[Path, Path]]
    frontmatter_path: Path
    frontmatter_content: str
    pdf_url: str

    def has_changes(self) -> bool:
        return bool(self.copy_ops) or self.frontmatter_content != ""


@dataclass(frozen=True)
class SyncResult:
    mode: str
    site: SiteSyncConfig
    plan: SyncPlan
    branch: str | None


def load_site_sync(path: Path) -> SiteSyncConfig:
    if not path.exists():
        raise SyncError(f"Site config not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raise SyncError("Site config is empty")

    try:
        parsed = _SiteSyncModel.model_validate(raw)
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors())
        raise SyncError(f"Invalid site config: {messages}") from exc

    site = parsed.site
    base = path.parent
    repo_path = _resolve_path(base, site.repo_path)
    return SiteSyncConfig(
        repo_path=repo_path,
        publish_variant=site.publish_variant,
        cv_markdown=Path(site.cv_markdown),
        cv_pdf_dir=Path(site.cv_pdf_dir),
        cv_pdf_name=site.cv_pdf_name,
        cv_page=Path(site.cv_page),
        cv_page_frontmatter_key=site.cv_page_frontmatter_key,
    )


def sync_site(
    *,
    config_path: Path,
    site_config_path: Path,
    mode: str,
    publish_config_path: Path | None = None,
) -> SyncResult:
    site = load_site_sync(site_config_path)
    if publish_config_path is not None:
        try:
            publish = load_publish_config(publish_config_path)
        except PublishError as exc:
            raise SyncError(str(exc)) from exc
        if site.publish_variant not in publish.variants:
            raise SyncError(
                f"Publish variant '{site.publish_variant}' is not allowed by publish config"
            )
    variant_path = resolve_variant_path(site.publish_variant, config_path)
    variant = load_variant(variant_path)
    dist_dir = resolve_dist_path(config_path) / variant.id

    source_md = output_path(dist_dir, variant, "md")
    source_pdf = output_path(dist_dir, variant, "pdf")
    if not source_md.exists():
        raise SyncError(f"Missing markdown output: {source_md}")
    if not source_pdf.exists():
        raise SyncError(f"Missing PDF output: {source_pdf}")

    plan = _plan_sync(site, source_md, source_pdf)
    branch_name: str | None = None
    if mode == "local":
        if plan.has_changes():
            _apply_plan(plan)
        return SyncResult(mode=mode, site=site, plan=plan, branch=None)

    if mode != "pr":
        raise SyncError(f"Unknown sync mode: {mode}")

    _ensure_git_repo(site.repo_path)
    _ensure_clean_repo(site.repo_path)

    if not plan.has_changes():
        return SyncResult(mode=mode, site=site, plan=plan, branch=None)

    branch_name = _branch_name()
    _run_git(site.repo_path, ["switch", "-c", branch_name])
    _apply_plan(plan)
    _run_git(site.repo_path, ["add", str(plan.frontmatter_path)])
    for _, dest in plan.copy_ops:
        _run_git(site.repo_path, ["add", str(dest)])

    if _git_has_changes(site.repo_path):
        _run_git(site.repo_path, ["commit", "-m", "Update CV artifacts"])
        _run_git(site.repo_path, ["push", "-u", "origin", branch_name])

        repo_slug = _github_repo(site.repo_path)
        _run_gh(
            site.repo_path,
            [
                "pr",
                "create",
                "--repo",
                repo_slug,
                "--title",
                "Update CV artifacts",
                "--body",
                "Automated update from cv-workbench.",
            ],
        )

    return SyncResult(mode=mode, site=site, plan=plan, branch=branch_name)


def _plan_sync(site: SiteSyncConfig, source_md: Path, source_pdf: Path) -> SyncPlan:
    dest_md = site.repo_path / site.cv_markdown
    dest_pdf = site.repo_path / site.cv_pdf_dir / site.cv_pdf_name
    dest_page = site.repo_path / site.cv_page

    copy_ops: list[tuple[Path, Path]] = []
    if _content_changed(source_md, dest_md):
        copy_ops.append((source_md, dest_md))
    if _content_changed(source_pdf, dest_pdf):
        copy_ops.append((source_pdf, dest_pdf))

    if not dest_page.exists():
        raise SyncError(f"Missing site page: {dest_page}")

    pdf_url = _pdf_url(site.cv_pdf_dir, site.cv_pdf_name)
    frontmatter_content = _update_frontmatter(dest_page, site.cv_page_frontmatter_key, pdf_url)

    return SyncPlan(
        copy_ops=copy_ops,
        frontmatter_path=dest_page,
        frontmatter_content=frontmatter_content,
        pdf_url=pdf_url,
    )


def _apply_plan(plan: SyncPlan) -> None:
    for source, dest in plan.copy_ops:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    if plan.frontmatter_content:
        plan.frontmatter_path.write_text(plan.frontmatter_content)


def _content_changed(source: Path, dest: Path) -> bool:
    if not dest.exists():
        return True
    return _hash_file(source) != _hash_file(dest)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_frontmatter(path: Path, key: str, value: str) -> str:
    text = path.read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SyncError(f"Frontmatter not found in {path}")

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise SyncError(f"Frontmatter not closed in {path}")

    updated = False
    for index in range(1, end_index):
        stripped = lines[index].lstrip()
        if stripped.startswith(f"{key}:"):
            new_line = f"{key}: {value}"
            if lines[index] != new_line:
                lines[index] = new_line
                updated = True
            break
    else:
        lines.insert(end_index, f"{key}: {value}")
        updated = True
        end_index += 1

    if not updated:
        return ""

    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + trailing


def _pdf_url(pdf_dir: Path, pdf_name: str) -> str:
    parts = pdf_dir.parts
    if parts and parts[0] == "public":
        rel = Path(*parts[1:])
    else:
        rel = pdf_dir
    url_path = "/" + str((rel / pdf_name).as_posix()).lstrip("/")
    return url_path


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _ensure_git_repo(repo_path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError(f"Not a git repo: {repo_path}")


def _ensure_clean_repo(repo_path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError("Failed to read git status")
    if result.stdout.strip():
        raise SyncError("Site repo has uncommitted changes")


def _git_has_changes(repo_path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def _run_git(repo_path: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SyncError(message or "Git command failed")


def _run_gh(repo_path: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["gh", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SyncError(message or "GitHub CLI command failed")


def _github_repo(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError("Failed to read origin remote")
    url = result.stdout.strip()
    if url.startswith("git@"):
        _, path = url.split(":", 1)
    elif "://" in url:
        path = url.split("://", 1)[1].split("/", 1)[1]
    else:
        path = url
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        raise SyncError("Unable to parse GitHub repo from origin")
    return path


def _branch_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"cv-update/{timestamp}"
