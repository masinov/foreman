"""Projects: init, list, show, config."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ..models import Project, utc_now_text
from ..roles import RoleLoadError, default_roles_dir, load_roles
from ..scaffold import (
    DEFAULT_DB_FILENAME,
    DEFAULT_DEFAULT_BRANCH,
    DEFAULT_TEST_COMMAND,
    DEFAULT_WORKFLOW_ID,
    ScaffoldError,
    default_project_settings,
    resolve_spec_path,
    scaffold_repository,
)
from ..policy import POLICY_DECISIONS, PolicyMatrix
from ..settings import ProjectSettings, SettingsError, settings_of
from ..store import ForemanStore
from ..workflows import WorkflowLoadError, default_workflows_dir, load_workflows

from .common import (
    CliResolutionError,
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    allocate_project_id,
    format_run_totals,
    format_setting_value,
    format_task_counts,
    parse_config_assignment,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    role_outcomes,
    set_handler,
)


def handle_init(args: argparse.Namespace) -> int:
    """Handle ``foreman init``."""

    roles_dir = default_roles_dir()
    workflows_dir = default_workflows_dir()
    repo_path = Path(args.repo_path).expanduser().resolve()
    db_path = resolve_db_path_or_print(args.db, repo_path=repo_path)
    if db_path is None:
        return 1
    try:
        roles = load_roles(roles_dir)
        workflows = load_workflows(
            workflows_dir,
            available_role_ids=set(roles),
            role_outcomes=role_outcomes(roles),
        )
        spec_reference, _ = resolve_spec_path(repo_path, args.spec)
    except (RoleLoadError, WorkflowLoadError, ScaffoldError) as exc:
        print(f"Failed to initialize project: {exc}", file=sys.stderr)
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        existing = store.find_project_by_repo_path(str(repo_path))
        workflow_id = args.workflow or (
            existing.workflow_id if existing is not None else DEFAULT_WORKFLOW_ID
        )
        workflow = workflows.get(workflow_id)
        if workflow is None:
            print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
            return 1

        default_branch = args.default_branch or (
            existing.default_branch if existing is not None else DEFAULT_DEFAULT_BRANCH
        )
        test_command = args.test_command or (
            settings_of(existing).test_command
            if existing is not None
            else DEFAULT_TEST_COMMAND
        )
        if not test_command:
            test_command = DEFAULT_TEST_COMMAND

        try:
            scaffold_result = scaffold_repository(
                repo_path,
                project_name=args.name,
                spec_path=spec_reference,
                default_branch=default_branch,
                test_command=test_command,
            )
        except ScaffoldError as exc:
            print(f"Failed to initialize project: {exc}", file=sys.stderr)
            return 1

        settings = dict(existing.settings) if existing is not None else {}
        for key, value in default_project_settings(test_command=test_command).items():
            settings.setdefault(key, value)
        settings["test_command"] = test_command

        project = Project(
            id=allocate_project_id(store, args.name, repo_path, existing),
            name=args.name,
            repo_path=str(repo_path),
            spec_path=spec_reference,
            methodology=workflow.methodology,
            workflow_id=workflow_id,
            default_branch=default_branch,
            settings=settings,
            created_at=existing.created_at if existing is not None else utc_now_text(),
            updated_at=utc_now_text(),
        )
        store.save_project(project)
        db_path = store.db_path

    lines = [
        "Initialized project" if existing is None else "Updated project",
        f"Database: {db_path}",
        f"Project ID: {project.id}",
        f"Project name: {project.name}",
        f"Repo: {project.repo_path}",
        f"Spec: {project.spec_path}",
        f"Workflow: {project.workflow_id}",
        f"Default branch: {project.default_branch}",
        "Scaffold:",
    ]
    for artifact in scaffold_result.artifacts:
        lines.append(f"{artifact.path} | {artifact.action}")
    print_lines(*lines)
    return 0


def handle_projects(args: argparse.Namespace) -> int:
    """Handle ``foreman projects``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        projects = store.list_projects()
        if getattr(args, "as_json", False):
            print_json(
                {
                    "database": str(store.db_path),
                    "projects": [
                        {
                            "id": project.id,
                            "name": project.name,
                            "repo_path": project.repo_path,
                            "workflow_id": project.workflow_id,
                            "default_branch": project.default_branch,
                            "active_sprint_id": getattr(
                                store.get_active_sprint(project.id), "id", None
                            ),
                            "task_counts": store.task_counts(project.id),
                        }
                        for project in projects
                    ],
                }
            )
            return 0

        lines = ["Projects", f"Database: {store.db_path}"]
        if not projects:
            lines.extend(
                [
                    "No projects are tracked yet.",
                    f"Use `foreman init <repo_path> --name <name> --spec <path>` to create the default `{DEFAULT_DB_FILENAME}`, or pass `--db PATH` to inspect another store.",
                ]
            )
        else:
            for project in projects:
                active_sprint = store.get_active_sprint(project.id)
                task_counts = store.task_counts(project.id)
                active_sprint_label = active_sprint.title if active_sprint else "none"
                lines.append(
                    f"{project.id} | {project.name} | workflow={project.workflow_id} | active_sprint={active_sprint_label}"
                )
                lines.append(
                    f"repo={project.repo_path} | "
                    f"triage={task_counts['triage']} "
                    f"todo={task_counts['todo']} "
                    f"in_progress={task_counts['in_progress']} "
                    f"blocked={task_counts['blocked']} "
                    f"done={task_counts['done']} "
                    f"cancelled={task_counts['cancelled']}"
                )

    print_lines(*lines)
    return 0


def handle_project(args: argparse.Namespace) -> int:
    """Handle ``foreman project``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        active_sprint = store.get_active_sprint(project.id)
        task_counts = store.task_counts(project_id=project.id)
        totals = store.run_totals(project_id=project.id)
        project_sprints = store.list_sprints(project.id)
        db_path = store.db_path

    lines = [
        "Project",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Repo: {project.repo_path}",
        f"Spec: {project.spec_path or 'n/a'}",
        (
            f"Workflow: {project.workflow_id} | methodology={project.methodology} | "
            f"default_branch={project.default_branch}"
        ),
        (
            f"Active sprint: {active_sprint.id} | {active_sprint.title}"
            if active_sprint is not None
            else "Active sprint: none"
        ),
        f"Sprints: {len(project_sprints)}",
        format_task_counts(task_counts),
        format_run_totals(totals),
        "Settings:",
    ]
    if not project.settings:
        lines.append("- none")
    else:
        for key in sorted(project.settings):
            lines.append(f"- {key}={format_setting_value(project.settings[key])}")
    print_lines(*lines)
    return 0


def handle_config(args: argparse.Namespace) -> int:
    """Handle ``foreman config``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        assignment_summary = None
        if args.config_set:
            try:
                key, value = parse_config_assignment(args.config_set)
            except CliResolutionError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            candidate = dict(project.settings)
            candidate[key] = value
            try:
                ProjectSettings.from_raw(candidate)
            except SettingsError as exc:
                print(f"Invalid setting {key}: {exc}", file=sys.stderr)
                return 1
            project.settings = candidate
            project.updated_at = utc_now_text()
            store.save_project(project)
            assignment_summary = f"{key}={format_setting_value(value)}"
        db_path = store.db_path

    lines = [
        "Updated config" if assignment_summary is not None else "Config",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Workflow: {project.workflow_id} | default_branch={project.default_branch}",
    ]
    if assignment_summary is not None:
        lines.append(f"Changed: {assignment_summary}")
    lines.append("Settings:")
    if not project.settings:
        lines.append("- none")
    else:
        for key in sorted(project.settings):
            lines.append(f"- {key}={format_setting_value(project.settings[key])}")
    lines.extend(_policy_matrix_lines(project))
    print_lines(*lines)
    return 0


def _policy_matrix_lines(project: Project) -> list[str]:
    """Render the project's policy matrix: the defaults and the type rules."""

    matrix = PolicyMatrix.for_project(project)
    described = matrix.describe()
    lines = ["Policy matrix:"]
    for decision in POLICY_DECISIONS:
        entry = described["defaults"][decision]
        origin = "set" if entry["source"] == "project_default" else "default"
        lines.append(f"- {decision}={entry['value']} ({origin})")
    rules = described["rules"]
    if not rules:
        lines.append("Policy rules: none")
    else:
        lines.append("Policy rules:")
        for task_type in sorted(rules):
            rule = rules[task_type]
            joined = " ".join(f"{d}={rule[d]}" for d in POLICY_DECISIONS if d in rule)
            lines.append(f"- {task_type}: {joined}")
    return lines


def register_init(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman init` to the parser."""

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a repository for Foreman.",
    )
    init_parser.add_argument("repo_path", help="Path to the target repository.")
    init_parser.add_argument("--name", required=True, help="Human-readable project name.")
    init_parser.add_argument("--spec", required=True, help="Path to the project spec.")
    add_db_option(
        init_parser,
        help_text=f"Path to the SQLite store to initialize or update. Defaults to <repo>/{DEFAULT_DB_FILENAME}.",
    )
    init_parser.add_argument(
        "--workflow",
        default=None,
        help="Workflow identifier to assign to the project. Defaults to `development` for new projects; use `development_secure` to require a security review step before test and merge.",
    )
    init_parser.add_argument(
        "--default-branch",
        default=None,
        help="Default branch for the target repository. Defaults to `main` for new projects.",
    )
    init_parser.add_argument(
        "--test-command",
        default=None,
        help="Override the persisted test command for the initialized project.",
    )
    set_handler(init_parser, handle_init, "init")



def register_projects(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman projects` to the parser."""

    projects_parser = subparsers.add_parser(
        "projects",
        help="List tracked projects.",
    )
    add_db_option(projects_parser)
    add_json_option(projects_parser)
    set_handler(projects_parser, handle_projects, "projects")



def register_project(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman project` to the parser."""

    project_parser = subparsers.add_parser(
        "project",
        help="Inspect one project.",
    )
    project_parser.add_argument("project_id", help="Project identifier.")
    add_db_option(
        project_parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(project_parser, handle_project, "project")



def register_config(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman config` to the parser."""

    config_parser = subparsers.add_parser(
        "config",
        help="Inspect or mutate project configuration.",
    )
    config_parser.add_argument("project_id", help="Project identifier.")
    config_parser.add_argument(
        "--set",
        dest="config_set",
        help="Configuration assignment in key=value form.",
    )
    add_db_option(
        config_parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(config_parser, handle_config, "config")

