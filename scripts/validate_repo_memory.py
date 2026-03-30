#!/usr/bin/env python3
"""Validate the Foreman repository scaffold."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.repo_validation import (  # noqa: E402
    latest_versioned_spec,
    render_validation_report,
    validate_repo_scaffold,
)


def detect_current_branch(root: Path) -> str | None:
    """Return the current git branch if available."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    branch_name = result.stdout.strip()
    return branch_name or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to validate",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Override the branch name used for PR-summary validation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    branch_name = args.branch or detect_current_branch(root)
    latest_spec_path = latest_versioned_spec(root)
    issues = validate_repo_scaffold(root, branch_name=branch_name)

    if latest_spec_path is not None:
        display_spec_path = latest_spec_path.resolve().relative_to(root)
    else:
        display_spec_path = None

    report = render_validation_report(issues, display_spec_path)
    print(report)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
