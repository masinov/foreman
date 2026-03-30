"""Repository scaffold generation helpers for Foreman."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Any, Literal

from .errors import ForemanError

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _REPO_ROOT / "templates"
DEFAULT_CONTEXT_DIR = ".foreman"
DEFAULT_DB_FILENAME = ".foreman.db"
DEFAULT_TEST_COMMAND = "./venv/bin/python -m unittest discover -s tests"
DEFAULT_DEFAULT_BRANCH = "main"
DEFAULT_DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_WORKFLOW_ID = "development"
DEFAULT_TASK_SELECTION_MODE = "directed"

ArtifactAction = Literal["created", "updated", "unchanged"]


class ScaffoldError(ForemanError):
    """Raised when Foreman cannot scaffold or initialize a target repository."""


@dataclass(slots=True)
class ScaffoldArtifact:
    """One scaffold artifact and how the current run affected it."""

    path: str
    action: ArtifactAction


@dataclass(slots=True)
class ScaffoldResult:
    """Summary of one scaffold generation run."""

    repo_path: Path
    artifacts: tuple[ScaffoldArtifact, ...]


def default_project_settings(
    *,
    test_command: str | None = None,
    default_model: str | None = None,
) -> dict[str, Any]:
    """Return the baseline project settings for a new scaffolded project."""

    return {
        "default_model": default_model or DEFAULT_DEFAULT_MODEL,
        "task_selection_mode": DEFAULT_TASK_SELECTION_MODE,
        "context_dir": DEFAULT_CONTEXT_DIR,
        "test_command": test_command or DEFAULT_TEST_COMMAND,
        "max_step_visits": 5,
        "max_infra_retries": 3,
        "write_pr_summaries": False,
        "write_checkpoint_notes": False,
    }


def scaffold_repository(
    repo_path: str | Path,
    *,
    project_name: str,
    spec_path: str,
    default_branch: str,
    test_command: str,
) -> ScaffoldResult:
    """Create the minimal spec-defined repository scaffold."""

    root = Path(repo_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    artifacts: list[ScaffoldArtifact] = []
    docs_dir = root / "docs"
    adr_dir = docs_dir / "adr"
    context_dir = root / DEFAULT_CONTEXT_DIR
    gitignore_path = root / ".gitignore"
    agents_path = root / "AGENTS.md"

    docs_dir.mkdir(parents=True, exist_ok=True)
    artifacts.append(
        ScaffoldArtifact(path="docs/adr/", action=_ensure_directory(adr_dir))
    )
    artifacts.append(
        ScaffoldArtifact(path=f"{DEFAULT_CONTEXT_DIR}/", action=_ensure_directory(context_dir))
    )
    artifacts.append(
        ScaffoldArtifact(path=".gitignore", action=_ensure_gitignore_entry(gitignore_path))
    )
    artifacts.append(
        ScaffoldArtifact(
            path="AGENTS.md",
            action=_ensure_agents_file(
                agents_path,
                project_name=project_name,
                spec_path=spec_path,
                default_branch=default_branch,
                test_command=test_command,
            ),
        )
    )
    return ScaffoldResult(repo_path=root, artifacts=tuple(artifacts))


def resolve_spec_path(repo_path: str | Path, spec_path: str | Path) -> tuple[str, Path]:
    """Resolve a spec path and return its persisted reference plus absolute path."""

    repo_root = Path(repo_path).expanduser().resolve()
    raw_path = Path(spec_path).expanduser()
    candidate_paths: list[Path] = []
    if raw_path.is_absolute():
        candidate_paths.append(raw_path.resolve())
    else:
        candidate_paths.append((repo_root / raw_path).resolve())
        candidate_paths.append((Path.cwd() / raw_path).resolve())

    for candidate in candidate_paths:
        if candidate.is_file():
            return _reference_path(repo_root, candidate), candidate
    raise ScaffoldError(f"Spec path {spec_path!r} does not exist.")


def generate_project_id(name: str, repo_path: str | Path) -> str:
    """Return a readable stable project identifier candidate."""

    slug = _slugify(name)
    if slug:
        return slug
    repo_name = Path(repo_path).expanduser().resolve().name
    slug = _slugify(repo_name)
    return slug or "project"


def load_agents_template() -> str:
    """Load the generated AGENTS.md template from disk."""

    template_path = _TEMPLATES_DIR / "agents_md.md.j2"
    if not template_path.is_file():
        raise ScaffoldError(f"Missing scaffold template: {template_path}")
    return template_path.read_text(encoding="utf-8")


def render_agents_md(
    *,
    project_name: str,
    spec_path: str,
    default_branch: str,
    test_command: str,
) -> str:
    """Render the generated AGENTS.md content."""

    template = load_agents_template()
    return template.format_map(
        {
            "project_name": project_name,
            "spec_path": spec_path,
            "default_branch": default_branch,
            "test_command": test_command,
            "completion_marker": "TASK_COMPLETE",
            "context_dir": DEFAULT_CONTEXT_DIR,
        }
    ).rstrip() + os.linesep


def _ensure_directory(path: Path) -> ArtifactAction:
    if path.is_dir():
        return "unchanged"
    path.mkdir(parents=True, exist_ok=True)
    return "created"


def _ensure_gitignore_entry(path: Path) -> ArtifactAction:
    entries = (f"{DEFAULT_CONTEXT_DIR}/", DEFAULT_DB_FILENAME)
    if not path.exists():
        path.write_text("".join(f"{entry}\n" for entry in entries), encoding="utf-8")
        return "created"

    existing_lines = path.read_text(encoding="utf-8").splitlines()
    normalized = {line.strip() for line in existing_lines}
    missing_entries = [
        entry
        for entry in entries
        if entry not in normalized and entry.rstrip("/") not in normalized
    ]
    if not missing_entries:
        return "unchanged"

    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text = f"{text}\n"
    additions = "".join(f"{entry}\n" for entry in missing_entries)
    text = f"{text}{additions}"
    path.write_text(text, encoding="utf-8")
    return "updated"


def _ensure_agents_file(
    path: Path,
    *,
    project_name: str,
    spec_path: str,
    default_branch: str,
    test_command: str,
) -> ArtifactAction:
    if path.exists():
        return "unchanged"
    content = render_agents_md(
        project_name=project_name,
        spec_path=spec_path,
        default_branch=default_branch,
        test_command=test_command,
    )
    path.write_text(content, encoding="utf-8")
    return "created"


def _reference_path(repo_root: Path, target_path: Path) -> str:
    try:
        return str(target_path.relative_to(repo_root))
    except ValueError:
        return str(target_path)


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
