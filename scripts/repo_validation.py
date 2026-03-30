"""Validation helpers for the Foreman repository scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


REQUIRED_FILES = (
    Path("AGENTS.md"),
    Path("README.md"),
    Path("CLAUDE.md"),
    Path("CHANGELOG.md"),
    Path("docs/STATUS.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/BRANCHING.md"),
    Path("docs/TESTING.md"),
    Path("docs/RELEASES.md"),
    Path("docs/sprints/current.md"),
    Path("docs/sprints/backlog.md"),
    Path("docs/sprints/archive/README.md"),
    Path("docs/adr/README.md"),
    Path("docs/checkpoints/TEMPLATE.md"),
    Path("docs/prs/TEMPLATE.md"),
    Path("docs/specs/engine-design-v3.md"),
    Path("docs/mockups/foreman-mockup-v6.html"),
    Path("scripts/reviewed_codex.py"),
    Path("scripts/reviewed_claude.py"),
    Path("scripts/repo_validation.py"),
    Path("scripts/validate_repo_memory.py"),
)

REQUIRED_DIRECTORIES = (
    Path("docs/adr"),
    Path("docs/checkpoints"),
    Path("docs/prs"),
    Path("docs/specs"),
    Path("docs/mockups"),
    Path("docs/sprints"),
    Path("docs/sprints/archive"),
    Path("scripts"),
)

REQUIRED_GITIGNORE_ENTRIES = (
    ".foreman/",
    ".codex/",
    ".claude/",
)

VERSIONED_SPEC_PATTERN = re.compile(
    r"^(?P<stem>.+)-v(?P<version>\d+(?:\.\d+)*)\.md$"
)


@dataclass(frozen=True)
class ValidationIssue:
    """A repository validation problem."""

    path: str
    message: str


def discover_versioned_specs(root: Path) -> list[Path]:
    """Return versioned spec files sorted from oldest to newest."""

    specs_dir = root / "docs/specs"
    matches: list[tuple[tuple[int, ...], str, Path]] = []

    for path in specs_dir.glob("*.md"):
        match = VERSIONED_SPEC_PATTERN.fullmatch(path.name)
        if not match:
            continue
        version = tuple(int(part) for part in match.group("version").split("."))
        matches.append((version, path.name, path))

    matches.sort()
    return [path for _, _, path in matches]


def latest_versioned_spec(root: Path) -> Path | None:
    """Return the newest versioned spec file."""

    specs = discover_versioned_specs(root)
    if not specs:
        return None
    return specs[-1]


def branch_summary_path(branch_name: str) -> Path:
    """Map a branch name to its PR summary path."""

    return Path("docs/prs") / f"{branch_name.replace('/', '-')}.md"


def validate_repo_scaffold(
    root: Path, branch_name: str | None = None
) -> list[ValidationIssue]:
    """Validate the required Foreman repository scaffold."""

    issues: list[ValidationIssue] = []

    for relative_path in REQUIRED_DIRECTORIES:
        path = root / relative_path
        if not path.is_dir():
            issues.append(
                ValidationIssue(str(relative_path), "required directory is missing")
            )

    for relative_path in REQUIRED_FILES:
        path = root / relative_path
        if not path.is_file():
            issues.append(
                ValidationIssue(str(relative_path), "required file is missing")
            )
            continue
        if path.stat().st_size == 0:
            issues.append(ValidationIssue(str(relative_path), "required file is empty"))

    gitignore_path = root / ".gitignore"
    if not gitignore_path.is_file():
        issues.append(ValidationIssue(".gitignore", "required file is missing"))
    else:
        gitignore_text = gitignore_path.read_text(encoding="utf-8")
        for entry in REQUIRED_GITIGNORE_ENTRIES:
            if entry not in gitignore_text:
                issues.append(
                    ValidationIssue(".gitignore", f"missing required ignore entry {entry}")
                )

    latest_spec = latest_versioned_spec(root)
    if latest_spec is None:
        issues.append(
            ValidationIssue(
                "docs/specs",
                "at least one versioned product spec is required",
            )
        )

    if branch_name and branch_name not in {"main", "HEAD"}:
        summary_path = root / branch_summary_path(branch_name)
        if not summary_path.is_file():
            issues.append(
                ValidationIssue(
                    str(branch_summary_path(branch_name)),
                    "branch-specific PR summary is missing",
                )
            )

    return issues


def render_validation_report(
    issues: Iterable[ValidationIssue], latest_spec_path: Path | None
) -> str:
    """Render a human-readable validation report."""

    issue_list = list(issues)
    if issue_list:
        lines = ["Repository scaffold validation failed:"]
        for issue in issue_list:
            lines.append(f"- {issue.path}: {issue.message}")
        return "\n".join(lines)

    lines = ["Repository scaffold validation passed."]
    if latest_spec_path is not None:
        lines.append(f"Latest versioned spec: {latest_spec_path.as_posix()}")
    return "\n".join(lines)
