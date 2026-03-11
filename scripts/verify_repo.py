#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cvworkbench.dev.verify import VerifyError, run_verify


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic repo-local verify harness in an isolated workspace."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to verify (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Optional empty directory to use as the isolated verify workspace.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full verify summary as JSON.",
    )
    args = parser.parse_args()

    try:
        summary = run_verify(repo_root=args.repo_root, workspace_root=args.workspace)
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"status: {summary['status']}")
        print(f"workspace: {summary['workspace']['root']}")
        print(f"summary: {summary['contract']['summary_path']}")
        if summary["error"]:
            print(f"error: {summary['error']}")
        for step in summary["steps"]:
            print(
                f"step[{step['id']}]: {step['status']} "
                f"(exit={step['exit_code']} duration={step['duration_seconds']:.3f}s)"
            )

    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
