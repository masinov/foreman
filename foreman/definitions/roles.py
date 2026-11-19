"""Role loader support for Foreman."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any

from ._toml import TOMLDecodeError, load_toml_file, load_toml_text
from ..domain.outcomes import CANONICAL_OUTCOMES
from ..domain.errors import ForemanError
from ..data import ROLES_DIR

_FORMATTER = Formatter()

SIGNAL_FORMAT_DOC = """Available signals:
- FOREMAN_SIGNAL: {"type": "task_created", "title": "...", "task_type": "...", "description": "...", "criteria": "..."}
- FOREMAN_SIGNAL: {"type": "progress", "message": "..."}
- FOREMAN_SIGNAL: {"type": "blocker", "message": "..."}"""


#: Every signal an agent may emit; roles narrow this with ``[signals] allowed``.
ALL_SIGNALS: tuple[str, ...] = ("task_created", "progress", "blocker")
_DECISION_DEFAULT_OUTCOMES: tuple[str, ...] = ("approve", "deny", "steer")
REVIEW_KINDS: tuple[str, ...] = ("code", "security")
_AGENT_DEFAULT_OUTCOMES: tuple[str, ...] = ("done", "blocked", "error")


class RoleLoadError(ForemanError):
    """Raised when a role definition cannot be loaded or validated."""


class PromptRenderError(ForemanError):
    """Raised when a role prompt cannot be rendered."""


@dataclass(slots=True)
class AgentToolConfig:
    """Tool allowlist and denylist for one role."""

    allowed: tuple[str, ...] = ()
    disallowed: tuple[str, ...] = ()
    #: The role has no tool at all. An empty ``allowed`` means every tool,
    #: so having none is said outright.
    none: bool = False


@dataclass(slots=True)
class AgentConfig:
    """Agent execution configuration for one role."""

    backend: str
    model: str
    session_persistence: bool
    permission_mode: str
    model_ladder: tuple[str, ...] = ()
    flags: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    tools: AgentToolConfig = field(default_factory=AgentToolConfig)


@dataclass(slots=True)
class CompletionOutputConfig:
    """Post-run extraction settings for one role."""

    extract_summary: bool = False
    extract_branch: bool = False
    extract_decision: bool = False
    extract_json: bool = False
    #: For a role that decides on a change: an approval given on a diff that
    #: was cut, with no file opened, is not accepted. The role is asked once
    #: to read the change; an approval still unread stops the task.
    approve_needs_reading: bool = False


@dataclass(slots=True)
class CompletionConfig:
    """Completion settings for one role."""

    marker: str
    timeout_minutes: int
    max_cost_usd: float
    output: CompletionOutputConfig = field(default_factory=CompletionOutputConfig)
    #: Outcomes this role may produce. Decision roles default to
    #: approve/deny/steer; other roles to done/blocked/error. Workflow
    #: validation and decision parsing read this instead of role ids.
    outcomes: tuple[str, ...] = ()
    #: For decision roles: which review this verdict counts as in completion
    #: evidence ("code" or "security"). Ignored for non-decision roles.
    review_kind: str = "code"


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
    #: Signals this role is allowed to emit; anything else is recorded as
    #: ``signal.rejected`` and never applied.
    signals: tuple[str, ...] = ALL_SIGNALS

    def render_prompt(self, context: Mapping[str, Any] | None = None) -> str:
        """Render the role prompt template with the provided context."""

        return render_prompt(self, context or {})


def default_roles_dir() -> Path:
    """Return the shipped roles directory."""

    return ROLES_DIR


#: The tools a Claude Code role may name. The names are the agent program's
#: own; Foreman passes them through. A name that is not here is refused when
#: the role is loaded, because the program ignores a name it does not know and
#: the role would then run with a different tool set than the one written.
CLAUDE_CODE_TOOLS: tuple[str, ...] = (
    "Read",
    "Grep",
    "Glob",
    "Edit",
    "Write",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "Task",
    "Skill",
    "LSP",
    "ToolSearch",
)

KNOWN_TOOLS: dict[str, tuple[str, ...]] = {"claude_code": CLAUDE_CODE_TOOLS}

BACKENDS: tuple[str, ...] = ("claude_code", "codex")


def load_role(path: str | Path) -> RoleDefinition:
    """Load one role definition from disk."""

    role_path = Path(path)
    return parse_role(load_toml_file(role_path), role_path)


def load_role_text(text: str, source: str | Path) -> RoleDefinition:
    """Load one role definition from TOML text; ``source`` names it in errors."""

    try:
        data = load_toml_text(text)
    except TOMLDecodeError as exc:
        raise RoleLoadError(f"{source}: not valid TOML: {exc}") from exc
    return parse_role(data, Path(source))


def parse_role(data: Mapping[str, Any], role_path: Path) -> RoleDefinition:
    """Build one role definition from decoded TOML."""


    try:
        role_data = _require_mapping(data, "role", role_path)
        agent_data = _require_mapping(data, "agent", role_path)
        prompt_data = _require_mapping(data, "prompt", role_path)
        completion_data = _require_mapping(data, "completion", role_path)
    except KeyError as exc:
        raise RoleLoadError(f"{role_path}: missing required section {exc.args[0]!r}.") from exc

    tools_data = _as_mapping(agent_data.get("tools"), default={})
    output_data = _as_mapping(completion_data.get("output"), default={})
    signals_data = _as_mapping(data.get("signals"), default={})
    prompt_template = _require_string(prompt_data, "template", role_path)

    extract_decision = _require_bool(output_data, "extract_decision", role_path, default=False)
    outcomes = tuple(_require_string_list(completion_data, "outcomes", role_path, default=()))
    if not outcomes:
        outcomes = _DECISION_DEFAULT_OUTCOMES if extract_decision else _AGENT_DEFAULT_OUTCOMES
    invalid_outcomes = [value for value in outcomes if value not in CANONICAL_OUTCOMES]
    if invalid_outcomes:
        raise RoleLoadError(
            f"{role_path}: completion.outcomes contains unknown outcome(s) "
            f"{', '.join(sorted(invalid_outcomes))}."
        )
    review_kind = str(completion_data.get("review_kind", "code") or "code")
    if review_kind not in REVIEW_KINDS:
        raise RoleLoadError(
            f"{role_path}: completion.review_kind must be one of {', '.join(REVIEW_KINDS)}."
        )
    allowed_signals = tuple(
        _require_string_list(signals_data, "allowed", role_path, default=ALL_SIGNALS)
    )
    invalid_signals = [value for value in allowed_signals if value not in ALL_SIGNALS]
    if invalid_signals:
        raise RoleLoadError(
            f"{role_path}: signals.allowed contains unknown signal(s) "
            f"{', '.join(sorted(invalid_signals))}."
        )

    backend = _require_string(agent_data, "backend", role_path)
    if backend not in BACKENDS:
        raise RoleLoadError(
            f"{role_path}: agent.backend must be one of {', '.join(BACKENDS)}; got {backend!r}."
        )
    known_tools = KNOWN_TOOLS.get(backend)
    if known_tools is not None:
        for key in ("allowed", "disallowed"):
            unknown = [
                name
                for name in _require_string_list(tools_data, key, role_path, default=())
                if name not in known_tools
            ]
            if unknown:
                raise RoleLoadError(
                    f"{role_path}: agent.tools.{key} names unknown tool(s) "
                    f"{', '.join(unknown)}. Known tools: {', '.join(known_tools)}."
                )

    no_tools = _require_bool(tools_data, "none", role_path, default=False)
    if no_tools and _require_string_list(tools_data, "allowed", role_path, default=()):
        raise RoleLoadError(
            f"{role_path}: agent.tools says none and also lists allowed tools; keep one."
        )

    return RoleDefinition(
        id=_require_string(role_data, "id", role_path),
        name=_require_string(role_data, "name", role_path),
        description=_require_string(role_data, "description", role_path),
        agent=AgentConfig(
            backend=_require_string(agent_data, "backend", role_path),
            model=_require_string(agent_data, "model", role_path),
            session_persistence=_require_bool(agent_data, "session_persistence", role_path),
            permission_mode=_require_string(agent_data, "permission_mode", role_path),
            model_ladder=tuple(
                _require_string_list(agent_data, "model_ladder", role_path, default=())
            ),
            flags=_as_mapping(agent_data.get("flags"), default={}),
            env=_require_string_mapping(agent_data, "env", role_path, default={}),
            tools=AgentToolConfig(
                allowed=_require_string_list(tools_data, "allowed", role_path, default=()),
                disallowed=_require_string_list(tools_data, "disallowed", role_path, default=()),
                none=no_tools,
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
                extract_decision=extract_decision,
                extract_json=_require_bool(output_data, "extract_json", role_path, default=False),
                approve_needs_reading=_require_bool(
                    output_data, "approve_needs_reading", role_path, default=False
                ),
            ),
            outcomes=outcomes,
            review_kind=review_kind,
        ),
        source_path=role_path,
        template_variables=_extract_template_variables(prompt_template),
        signals=allowed_signals,
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


#: Variables that sit alone on a line; the line goes when the value is empty.
OPTIONAL_LINE_VARIABLES = ("environment_rules",)


def render_prompt(role: RoleDefinition, context: Mapping[str, Any]) -> str:
    """Render one role prompt template with stable built-in defaults."""

    values = {name: "" for name in role.template_variables}
    values["completion_marker"] = role.completion.marker
    values["signal_format"] = SIGNAL_FORMAT_DOC
    for key, value in context.items():
        values[key] = _stringify_prompt_value(value)

    template = role.prompt_template
    for name in OPTIONAL_LINE_VARIABLES:
        if not values.get(name):
            # A placeholder alone on its line leaves no empty line when unset.
            template = re.sub(
                rf"^[ \t]*\{{{name}\}}[ \t]*\n", "", template, flags=re.MULTILINE
            )
    try:
        return template.format_map(values)
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


def _require_string_mapping(
    data: Mapping[str, Any],
    key: str,
    path: Path,
    *,
    default: dict[str, str],
) -> dict[str, str]:
    value = data.get(key, default)
    if not isinstance(value, dict) or any(
        not isinstance(item_key, str) or not isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        raise RoleLoadError(f"{path}: expected {key!r} to be a table of strings.")
    return dict(value)
