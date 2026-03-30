"""Role loader support for Foreman."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any

from ._toml import load_toml_file
from .errors import ForemanError

_FORMATTER = Formatter()
_REPO_ROOT = Path(__file__).resolve().parent.parent

SIGNAL_FORMAT_DOC = """Available signals:
- FOREMAN_SIGNAL: {"type": "task_started", "title": "...", "task_type": "...", "branch": "...", "criteria": "..."}
- FOREMAN_SIGNAL: {"type": "task_created", "title": "...", "task_type": "...", "description": "...", "criteria": "..."}
- FOREMAN_SIGNAL: {"type": "progress", "message": "..."}
- FOREMAN_SIGNAL: {"type": "blocker", "message": "..."}"""


class RoleLoadError(ForemanError):
    """Raised when a role definition cannot be loaded or validated."""


class PromptRenderError(ForemanError):
    """Raised when a role prompt cannot be rendered."""


@dataclass(slots=True)
class AgentToolConfig:
    """Tool allowlist and denylist for one role."""

    allowed: tuple[str, ...] = ()
    disallowed: tuple[str, ...] = ()


@dataclass(slots=True)
class AgentConfig:
    """Agent execution configuration for one role."""

    backend: str
    model: str
    session_persistence: bool
    permission_mode: str
    flags: dict[str, Any] = field(default_factory=dict)
    tools: AgentToolConfig = field(default_factory=AgentToolConfig)


@dataclass(slots=True)
class CompletionOutputConfig:
    """Post-run extraction settings for one role."""

    extract_summary: bool = False
    extract_branch: bool = False
    extract_decision: bool = False
    extract_json: bool = False


@dataclass(slots=True)
class CompletionConfig:
    """Completion settings for one role."""

    marker: str
    timeout_minutes: int
    max_cost_usd: float
    output: CompletionOutputConfig = field(default_factory=CompletionOutputConfig)


@dataclass(slots=True)
class RoleDefinition:
    """One declarative role loaded from TOML."""

    id: str
    name: str
    description: str
    agent: AgentConfig
    prompt_template: str
    completion: CompletionConfig
    source_path: Path
    template_variables: tuple[str, ...]

    def render_prompt(self, context: Mapping[str, Any] | None = None) -> str:
        """Render the role prompt template with the provided context."""

        return render_prompt(self, context or {})


def default_roles_dir() -> Path:
    """Return the shipped roles directory."""

    return _REPO_ROOT / "roles"


def load_role(path: str | Path) -> RoleDefinition:
    """Load one role definition from disk."""

    role_path = Path(path)
    data = load_toml_file(role_path)

    try:
        role_data = _require_mapping(data, "role", role_path)
        agent_data = _require_mapping(data, "agent", role_path)
        prompt_data = _require_mapping(data, "prompt", role_path)
        completion_data = _require_mapping(data, "completion", role_path)
    except KeyError as exc:
        raise RoleLoadError(f"{role_path}: missing required section {exc.args[0]!r}.") from exc

    tools_data = _as_mapping(agent_data.get("tools"), default={})
    output_data = _as_mapping(completion_data.get("output"), default={})
    prompt_template = _require_string(prompt_data, "template", role_path)

    return RoleDefinition(
        id=_require_string(role_data, "id", role_path),
        name=_require_string(role_data, "name", role_path),
        description=_require_string(role_data, "description", role_path),
        agent=AgentConfig(
            backend=_require_string(agent_data, "backend", role_path),
            model=_require_string(agent_data, "model", role_path),
            session_persistence=_require_bool(agent_data, "session_persistence", role_path),
            permission_mode=_require_string(agent_data, "permission_mode", role_path),
            flags=_as_mapping(agent_data.get("flags"), default={}),
            tools=AgentToolConfig(
                allowed=_require_string_list(tools_data, "allowed", role_path, default=()),
                disallowed=_require_string_list(tools_data, "disallowed", role_path, default=()),
            ),
        ),
        prompt_template=prompt_template,
        completion=CompletionConfig(
            marker=_require_string(completion_data, "marker", role_path),
            timeout_minutes=_require_int(completion_data, "timeout_minutes", role_path),
            max_cost_usd=_require_float(completion_data, "max_cost_usd", role_path),
            output=CompletionOutputConfig(
                extract_summary=_require_bool(output_data, "extract_summary", role_path, default=False),
                extract_branch=_require_bool(output_data, "extract_branch", role_path, default=False),
                extract_decision=_require_bool(output_data, "extract_decision", role_path, default=False),
                extract_json=_require_bool(output_data, "extract_json", role_path, default=False),
            ),
        ),
        source_path=role_path,
        template_variables=_extract_template_variables(prompt_template),
    )


def load_roles(directory: str | Path | None = None) -> dict[str, RoleDefinition]:
    """Load all role definitions from one directory."""

    roles_dir = default_roles_dir() if directory is None else Path(directory)
    if not roles_dir.is_dir():
        raise RoleLoadError(f"{roles_dir}: roles directory does not exist.")

    roles: dict[str, RoleDefinition] = {}
    for path in sorted(roles_dir.glob("*.toml")):
        role = load_role(path)
        if role.id in roles:
            raise RoleLoadError(
                f"{path}: duplicate role id {role.id!r}; already defined in {roles[role.id].source_path}."
            )
        roles[role.id] = role
    return roles


def render_prompt(role: RoleDefinition, context: Mapping[str, Any]) -> str:
    """Render one role prompt template with stable built-in defaults."""

    values = {name: "" for name in role.template_variables}
    values["completion_marker"] = role.completion.marker
    values["signal_format"] = SIGNAL_FORMAT_DOC
    for key, value in context.items():
        values[key] = _stringify_prompt_value(value)

    try:
        return role.prompt_template.format_map(values)
    except (KeyError, ValueError) as exc:
        raise PromptRenderError(
            f"Failed to render role {role.id!r} from {role.source_path}: {exc}"
        ) from exc


def _extract_template_variables(template: str) -> tuple[str, ...]:
    values: list[str] = []
    for _, field_name, _, _ in _FORMATTER.parse(template):
        if field_name and field_name not in values:
            values.append(field_name)
    return tuple(values)


def _stringify_prompt_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return "\n".join(str(item) for item in value)
    return str(value)


def _require_mapping(data: Mapping[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = data[key]
    if not isinstance(value, dict):
        raise RoleLoadError(f"{path}: expected {key!r} to be a table.")
    return value


def _as_mapping(value: Any, *, default: dict[str, Any]) -> dict[str, Any]:
    if value is None:
        return default
    if not isinstance(value, dict):
        raise RoleLoadError("Expected nested TOML table to decode to a dictionary.")
    return value


def _require_string(data: Mapping[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise RoleLoadError(f"{path}: expected {key!r} to be a string.")
    return value


def _require_bool(
    data: Mapping[str, Any],
    key: str,
    path: Path,
    *,
    default: bool | None = None,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise RoleLoadError(f"{path}: expected {key!r} to be a boolean.")
    return value


def _require_int(data: Mapping[str, Any], key: str, path: Path) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise RoleLoadError(f"{path}: expected {key!r} to be an integer.")
    return value


def _require_float(data: Mapping[str, Any], key: str, path: Path) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise RoleLoadError(f"{path}: expected {key!r} to be numeric.")
    return float(value)


def _require_string_list(
    data: Mapping[str, Any],
    key: str,
    path: Path,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = data.get(key, list(default))
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RoleLoadError(f"{path}: expected {key!r} to be a list of strings.")
    return tuple(value)
