"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/__init__.py

Expose project operation records and callable lifecycle APIs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from cvworkbench.ops.projects.creation import create_project_from_file as create_project_from_file
from cvworkbench.ops.projects.creation import create_project_from_url as create_project_from_url
from cvworkbench.ops.projects.creation import discard_project_workspace as discard_project_workspace
from cvworkbench.ops.projects.creation import retarget_project_variant as retarget_project_variant
from cvworkbench.ops.projects.identity import resolve_project_dir as resolve_project_dir
from cvworkbench.ops.projects.identity import (
    suggest_project_variant_id as suggest_project_variant_id,
)
from cvworkbench.ops.projects.inspection import load_project_details as load_project_details
from cvworkbench.ops.projects.inspection import (
    project_patch_render_warning as project_patch_render_warning,
)
from cvworkbench.ops.projects.inspection import project_patch_status as project_patch_status
from cvworkbench.ops.projects.manifest import load_project as load_project
from cvworkbench.ops.projects.manifest import load_project_metadata as load_project_metadata
from cvworkbench.ops.projects.patches import (
    append_replace_experience_bullet_operation as append_replace_experience_bullet_operation,
)
from cvworkbench.ops.projects.patches import (
    append_replace_project_summary_operation as append_replace_project_summary_operation,
)
from cvworkbench.ops.projects.patches import apply_project_patch as apply_project_patch
from cvworkbench.ops.projects.patches import compile_project_patch as compile_project_patch
from cvworkbench.ops.projects.patches import load_project_patch as load_project_patch
from cvworkbench.ops.projects.patches import (
    load_project_patch_payload as load_project_patch_payload,
)
from cvworkbench.ops.projects.patches import prepare_project_sot as prepare_project_sot
from cvworkbench.ops.projects.records import ProjectDetails as ProjectDetails
from cvworkbench.ops.projects.records import ProjectError as ProjectError
from cvworkbench.ops.projects.records import ProjectPatch as ProjectPatch
from cvworkbench.ops.projects.records import ProjectPaths as ProjectPaths
from cvworkbench.ops.projects.records import ProjectSpec as ProjectSpec
