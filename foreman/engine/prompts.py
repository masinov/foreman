"""What an agent is told: the pieces of repository state a prompt carries."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from ..context import ProjectContextProjection, build_project_context
from ..git import GitError, changed_files, recent_commits, status_text
from ..models import CompletionEvidence, Project, Run, Task
from ..roles import RoleDefinition
from ..store import ForemanStore
from .branch_sync import task_working_dir
from .evidence import EvidenceBuilder, branch_diff_content
from .limits import resolve_project_settings
from .task_writes import TaskWrites


def load_repo_instructions(repo_path: str) -> str:
    agents_path = Path(repo_path) / "AGENTS.md"
    if not agents_path.is_file():
        return ""
    return agents_path.read_text(encoding="utf-8")


_VENV_PATH = re.compile(r"(?<![\w./-])(?:(\./)(\.?venv)|(\.venv)|venv(?=/))(?![\w-])")


def detect_virtualenv(instructions: str) -> str | None:
    """The virtual environment path a repository's instructions name, if any.

    Recognises ``./venv``, ``./.venv``, ``.venv`` and ``venv/``; a bare word
    "venv" in prose is not a path. Returns the path as ``./venv`` or ``.venv``.
    """

    match = _VENV_PATH.search(instructions)
    if match is None:
        return None
    if match.group(3):
        return ".venv"
    if match.group(2):
        return f"./{match.group(2)}"
    return "./venv"


def environment_rules(instructions: str) -> str:
    """The Python rule for a prompt: empty when no virtual environment is named."""

    venv = detect_virtualenv(instructions)
    if venv is None:
        return ""
    return (
        f"- Never run `python`, `python3` or `pip` from the system, for anything, "
        f"including one-off scripts, edits and checks. Use `{venv}/bin/python` "
        f"and `{venv}/bin/pip`."
    )


def safe_git_status(repo_path: str | Path) -> str:
    try:
        return status_text(repo_path)
    except GitError:
        return ""


def safe_changed_files(
    repo_path: str,
    target_branch: str,
    branch_name: str | None,
) -> str:
    try:
        return changed_files(
            repo_path,
            target_branch=target_branch,
            branch_name=branch_name,
        )
    except GitError:
        return ""


def safe_recent_commits(repo_path: str, branch_name: str | None) -> str:
    try:
        return recent_commits(repo_path, branch_name=branch_name)
    except GitError:
        return ""


class PromptBuilder:
    """Renders the prompt for one agent step from the task and its history."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        evidence: EvidenceBuilder,
        tasks: TaskWrites,
        build_evidence: Callable[[Task, Project], CompletionEvidence | None],
    ) -> None:
        self.store = store
        self.evidence = evidence
        self.tasks = tasks
        #: Called to build evidence for a reviewer's prompt. A callable, not
        #: ``evidence.build`` directly, so the engine's own entry point (and
        #: anything wrapped around it) is what runs.
        self.build_completion_evidence = build_evidence

    def latest_agent_run(self, task_id: str) -> Run | None:
        """Return the most recent completed agent (non-builtin) run for a task.

        Prompts that quote the "previous output" want the last thing an agent
        said, not the output of the test or merge built-in that ran after it.
        """

        candidates = [
            run
            for run in self.store.list_runs(task_id=task_id)
            if not run.role_id.startswith("_builtin:")
            and run.status == "completed"
            and run.outcome_detail
        ]
        return candidates[-1] if candidates else None

    def build(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        carried_output: str | None,
        *,
        context_projection: ProjectContextProjection | None = None,
    ) -> str:
        latest_run = self.latest_agent_run(task.id)
        if context_projection is None:
            context_projection = build_project_context(
                self.store,
                project,
                current_task=task,
                carried_output=carried_output,
            )
        # Reuse cached evidence on the task record to avoid recomputing on
        # repeated reviewer prompts. Built once at first reviewer render.
        evidence = task.completion_evidence
        if evidence is not None and self.evidence.is_stale(evidence, task, project):
            evidence = None
            task.completion_evidence = None
        if evidence is None and role.completion.output.extract_decision:
            evidence = self.build_completion_evidence(task, project)
            task.completion_evidence = evidence
            self.tasks.save(task)
        repo_instructions = load_repo_instructions(project.repo_path)
        context = {
            "task_title": task.title,
            "task_description": task.description or "",
            "task_type": task.task_type,
            "acceptance_criteria": task.acceptance_criteria or "",
            "branch_name": task.branch_name or "",
            "sprint_context": context_projection.context_markdown,
            "project_status": context_projection.status_markdown,
            "repo_instructions": repo_instructions,
            "environment_rules": environment_rules(repo_instructions),
            "spec_path": project.spec_path or "",
            "previous_feedback": carried_output or "",
            "previous_output": latest_run.outcome_detail if latest_run else "",
            # Status describes the tree the agent works in; diffs and log come
            # from refs, which every worktree shares.
            "git_status": safe_git_status(task_working_dir(project, task)),
            "changed_files": safe_changed_files(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ),
            "recent_commits": safe_recent_commits(project.repo_path, task.branch_name),
            "completion_evidence": (
                str(evidence)
                if role.completion.output.extract_decision
                and task.branch_name
                and evidence is not None
                else ""
            ),
            # Curated diff payload, only for decision roles so they can review
            # the change without exploring the repo. Other roles get "".
            "completion_diff": (
                branch_diff_content(
                    project.repo_path,
                    project.default_branch,
                    task.branch_name,
                    max_chars=resolve_project_settings(project).review_diff_max_chars,
                )
                if role.completion.output.extract_decision and task.branch_name
                else ""
            ),
        }
        if evidence is not None:
            context.update({
                "completion_proof_status": evidence.proof_status,
                "completion_tests_status": evidence.tests_status,
                "completion_review_outcome": evidence.review_outcome,
                "completion_criteria_count": evidence.criteria_count,
                "completion_criteria_addressed": evidence.criteria_addressed,
                "completion_criteria_partially_addressed": evidence.criteria_partially_addressed,
                "completion_changed_files": evidence.changed_files,
                "completion_branch_diff_stat": evidence.branch_diff_stat,
                "completion_builtin_test_passed": evidence.builtin_test_passed,
                "completion_builtin_test_result": evidence.builtin_test_result,
                "completion_builtin_test_detail": evidence.builtin_test_detail,
            })
        return role.render_prompt(context)
