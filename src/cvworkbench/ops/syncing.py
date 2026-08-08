"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/syncing.py

Synchronizes generated outputs into a site repository.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from cvworkbench.build.paths import output_path
from cvworkbench.config import resolve_publish_path, resolve_sot_path, resolve_variant_path
from cvworkbench.ops.public_pdf import PublicPdfError, validate_public_pdf
from cvworkbench.ops.publish import PublishConfig, PublishError, load_publish_config
from cvworkbench.variants import Variant, load_variant


class SyncError(RuntimeError):
    pass


class _SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    repo_path: str
    publish_variant: str
    cv_pdf_dir: str
    cv_pdf_name: str
    cv_manifest: str
    cv_page: str
    cv_page_frontmatter_key: str


class _SiteSyncModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    site: _SiteConfig


@dataclass(frozen=True)
class SiteSyncConfig:
    repo_path: Path
    publish_variant: str
    cv_pdf_dir: Path
    cv_pdf_name: str
    cv_manifest: Path
    cv_page: Path
    cv_page_frontmatter_key: str


@dataclass(frozen=True)
class SyncPlan:
    copy_ops: list[tuple[Path, Path]]
    frontmatter_path: Path
    frontmatter_content: str
    manifest_path: Path
    manifest_content: str
    pdf_url: str

    def has_changes(self) -> bool:
        return bool(self.copy_ops) or bool(self.frontmatter_content) or bool(self.manifest_content)


@dataclass(frozen=True)
class SyncResult:
    mode: str
    site: SiteSyncConfig
    plan: SyncPlan
    branch: str | None


@dataclass(frozen=True)
class _StagedWrite:
    destination: Path
    staged: Path
    backup: Path | None


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
    if not repo_path.exists():
        raise SyncError(f"Site repo path not found: {repo_path}")
    if not repo_path.is_dir():
        raise SyncError(f"Site repo path is not a directory: {repo_path}")
    cv_pdf_name = Path(site.cv_pdf_name)
    if cv_pdf_name.name != site.cv_pdf_name or cv_pdf_name.is_absolute():
        raise SyncError("Site cv_pdf_name must be a single filename")
    return SiteSyncConfig(
        repo_path=repo_path,
        publish_variant=site.publish_variant,
        cv_pdf_dir=_site_relative_path(repo_path, site.cv_pdf_dir, "cv_pdf_dir"),
        cv_pdf_name=site.cv_pdf_name,
        cv_manifest=_site_relative_path(repo_path, site.cv_manifest, "cv_manifest"),
        cv_page=_site_relative_path(repo_path, site.cv_page, "cv_page"),
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
    publish: PublishConfig | None = None
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
    if publish is not None:
        _validate_publish_policy(variant, publish)
    publish_dir = resolve_publish_path(config_path) / variant.id

    source_pdf = output_path(publish_dir, variant, "pdf")
    if not source_pdf.exists():
        raise SyncError(f"Missing PDF output: {source_pdf}")
    source_manifest = publish_dir / "manifest.json"
    pdf_hash = _validate_public_artifact(source_pdf, source_manifest, variant, publish)
    if publish is not None:
        try:
            validate_public_pdf(
                source_pdf,
                variant=variant,
                publish=publish,
                sot_path=resolve_sot_path(None, config_path),
            )
        except (PublicPdfError, ValueError) as exc:
            raise SyncError(str(exc)) from exc

    plan = _plan_sync(site, source_pdf, pdf_hash, publish)
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
    _run_git(site.repo_path, ["add", str(plan.manifest_path)])
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


def _plan_sync(
    site: SiteSyncConfig,
    source_pdf: Path,
    pdf_hash: str,
    publish: PublishConfig | None,
) -> SyncPlan:
    dest_pdf = site.repo_path / site.cv_pdf_dir / site.cv_pdf_name
    dest_page = site.repo_path / site.cv_page
    manifest_path = site.repo_path / site.cv_manifest

    copy_ops: list[tuple[Path, Path]] = []
    if _content_changed(source_pdf, dest_pdf):
        copy_ops.append((source_pdf, dest_pdf))

    if not dest_page.exists():
        raise SyncError(f"Missing site page: {dest_page}")

    pdf_url = _pdf_url(site.cv_pdf_dir, site.cv_pdf_name)
    frontmatter_content = _update_frontmatter(dest_page, site.cv_page_frontmatter_key, pdf_url)
    manifest_content = _public_manifest(site, pdf_hash, publish)
    if manifest_path.exists() and manifest_path.read_text() == manifest_content:
        manifest_content = ""

    return SyncPlan(
        copy_ops=copy_ops,
        frontmatter_path=dest_page,
        frontmatter_content=frontmatter_content,
        manifest_path=manifest_path,
        manifest_content=manifest_content,
        pdf_url=pdf_url,
    )


def _apply_plan(plan: SyncPlan) -> None:
    writes: list[tuple[Path | None, Path, str | None]] = [
        (source, destination, None) for source, destination in plan.copy_ops
    ]
    if plan.frontmatter_content:
        writes.append((None, plan.frontmatter_path, plan.frontmatter_content))
    if plan.manifest_content:
        writes.append((None, plan.manifest_path, plan.manifest_content))

    staged_writes: list[_StagedWrite] = []
    applied: list[_StagedWrite] = []
    try:
        for source, destination, content in writes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = _temporary_sibling(destination, "stage")
            if source is not None:
                shutil.copy2(source, staged)
            else:
                staged.write_text(content or "")
            backup: Path | None = None
            if destination.exists():
                backup = _temporary_sibling(destination, "backup")
                shutil.copy2(destination, backup)
            staged_writes.append(
                _StagedWrite(destination=destination, staged=staged, backup=backup)
            )

        for staged_write in staged_writes:
            os.replace(staged_write.staged, staged_write.destination)
            applied.append(staged_write)
    except OSError as exc:
        rollback_errors: list[OSError] = []
        for staged_write in reversed(applied):
            try:
                if staged_write.backup is None:
                    staged_write.destination.unlink(missing_ok=True)
                else:
                    os.replace(staged_write.backup, staged_write.destination)
            except OSError as rollback_exc:
                rollback_errors.append(rollback_exc)
        if rollback_errors:
            raise SyncError("Site sync failed and rollback was incomplete") from exc
        raise SyncError("Site sync failed; prior artifacts were restored") from exc
    finally:
        for staged_write in staged_writes:
            staged_write.staged.unlink(missing_ok=True)
            if staged_write.backup is not None:
                staged_write.backup.unlink(missing_ok=True)


def _temporary_sibling(destination: Path, role: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.cvw-{role}-",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(raw_path)


def _validate_publish_policy(variant: Variant, publish: PublishConfig) -> None:
    missing_tags = sorted(set(publish.required_exclude_tags) - set(variant.exclude_tags))
    if missing_tags:
        raise SyncError(
            f"Publish variant is missing required exclude tags: {', '.join(missing_tags)}"
        )

    contact_fields = sorted(set(variant.contact_fields) & set(publish.forbidden_contact_fields))
    if contact_fields:
        raise SyncError(
            f"Publish variant includes forbidden contact fields: {', '.join(contact_fields)}"
        )

    sections = sorted(set(variant.order) & set(publish.forbidden_sections))
    if sections:
        raise SyncError(f"Publish variant includes forbidden sections: {', '.join(sections)}")


def _validate_public_artifact(
    source_pdf: Path,
    manifest_path: Path,
    variant: Variant,
    publish: PublishConfig | None,
) -> str:
    if not source_pdf.read_bytes().startswith(b"%PDF-"):
        raise SyncError(f"Public artifact is not a PDF: {source_pdf}")
    if not manifest_path.exists():
        raise SyncError(f"Build manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise SyncError(f"Build manifest is invalid: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise SyncError(f"Build manifest is invalid: {manifest_path}")
    if manifest.get("schema_version") != 1:
        raise SyncError("Build manifest schema does not match authored publication contract")
    if manifest.get("artifact_kind") != "authored-pdf-publication":
        raise SyncError("Build manifest is not an authored PDF publication")
    if manifest.get("formats") != ["pdf"]:
        raise SyncError("Build manifest must declare only the PDF publication format")

    manifest_variant = manifest.get("variant")
    if not isinstance(manifest_variant, dict) or manifest_variant.get("id") != variant.id:
        raise SyncError("Build manifest variant does not match publish variant")
    variant_contract = {
        "exclude_tags": variant.exclude_tags,
        "contact_fields": variant.contact_fields,
        "order": variant.order,
    }
    for key, expected in variant_contract.items():
        if manifest_variant.get(key) != expected:
            raise SyncError(f"Build manifest {key} does not match publish variant")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("pdf") != source_pdf.name:
        raise SyncError("Build manifest does not declare the PDF artifact")
    output_hashes = manifest.get("output_hashes")
    pdf_hash = _hash_file(source_pdf)
    if not isinstance(output_hashes, dict) or output_hashes.get("pdf") != pdf_hash:
        raise SyncError("Build manifest PDF hash does not match the artifact")
    transformation = manifest.get("transformation")
    if not isinstance(transformation, dict) or transformation.get("kind") != "semantic-redaction":
        raise SyncError("Build manifest lacks the semantic-redaction provenance contract")
    redaction_count = transformation.get("redaction_count")
    if not isinstance(redaction_count, int) or isinstance(redaction_count, bool):
        raise SyncError("Build manifest redaction count is invalid")
    if publish is not None:
        if transformation.get("forbidden_contact_fields") != publish.forbidden_contact_fields:
            raise SyncError("Build manifest contact policy does not match publish policy")
        if transformation.get("forbidden_sections") != publish.forbidden_sections:
            raise SyncError("Build manifest section policy does not match publish policy")
    return pdf_hash


def _public_manifest(
    site: SiteSyncConfig,
    pdf_hash: str,
    publish: PublishConfig | None,
) -> str:
    payload = {
        "schema_version": 1,
        "variant": site.publish_variant,
        "pdf_path": str((site.cv_pdf_dir / site.cv_pdf_name).as_posix()),
        "pdf_sha256": pdf_hash,
        "required_exclude_tags": publish.required_exclude_tags if publish else [],
        "forbidden_contact_fields": publish.forbidden_contact_fields if publish else [],
        "forbidden_sections": publish.forbidden_sections if publish else [],
    }
    fields = [
        f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True)}"
        for key, value in sorted(payload.items())
    ]
    return "{\n" + ",\n".join(fields) + "\n}\n"


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
        return path.resolve()
    return (base / path).resolve()


def _site_relative_path(repo_path: Path, value: str, field: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise SyncError(f"Site {field} must be relative to the site repository")
    destination = (repo_path / candidate).resolve()
    try:
        relative = destination.relative_to(repo_path)
    except ValueError as exc:
        raise SyncError(f"Site {field} must remain inside the site repository") from exc
    if relative == Path("."):
        raise SyncError(f"Site {field} must name a path inside the site repository")
    return relative


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
