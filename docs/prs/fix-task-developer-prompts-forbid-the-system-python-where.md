# fix: developer prompts forbid the system Python where a virtual environment is named

## Summary
`{environment_rules}` replaces the fixed venv line in `developer` and `developer_worker`; `PromptBuilder.build` fills it from `AGENTS.md` via `detect_virtualenv` / `environment_rules` (`foreman/engine/prompts.py`). `render_prompt` drops the placeholder's line when empty.

## Tests
`tests/test_engine_prompts.py` (EnvironmentRulesTests), `tests/test_roles.py`; full suite and ruff pass.

## Risks
Detection is textual: `./venv`, `./.venv`, `.venv`, `venv/`. Not enforced in the sandbox (out of scope).
