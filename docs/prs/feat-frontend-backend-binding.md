# PR Summary: feat/frontend-backend-binding

## Summary

Ties the React dashboard to the finished backend (review.md Phases 0–7) and
fixes the bugs found in `docs/reviews/frontend-gap-analysis.md`. Lands Tiers 1
and 2 of that report: correctness/honesty fixes plus making the roadmap features
visible (completion evidence, model transparency, supervision, an accurate
settings panel).

## Scope

### Bugs (Tier 1)
- **A1** New-task "Context" field was collected then dropped — now sent as
  `description` end to end.
- **A2** Run/Stop toggle now reads the authoritative `agent_running` field
  (with `project.status` fallback) instead of inferring from task status.
- **A3** Settings panel no longer writes dead keys; it binds to the real
  `ProjectSettings` schema.
- **A4** Removed the Codex meta-backend option that bricked the manager.

### Backend (Tier 1)
- **C1** `create_task` (service + `POST /api/sprints/{id}/tasks`) now accepts
  `description`, `complexity` (validated), and `depends_on` (validated to exist
  in-project) — matching the `foreman task add` CLI. Response echoes the new
  fields.
- **B3 (backend half)** `get_task` now serializes `completion_evidence`
  (verdict, proof_status, judged_by, score, criteria checklist, failure reasons,
  changed files, diff stat) via a new `_serialize_completion_evidence` helper.

### Visibility (Tier 2)
- **B3** Task drawer renders a Completion Evidence section (verdict / proof /
  score / judged-by badges, per-criterion checklist, failure reasons, diffstat).
- **B4** Run-history rows now show the run's `model`.
- **B1** Supervision: new `superviseMeta` client method; a `SupervisionBanner`
  appears in the sprint view on `engine.attention_needed`, runs one supervision
  turn via `POST …/meta/supervise`, streams the recommendation inline, and
  handles the 409 duplicate.
- **B5/B6** Settings rewritten: Models & Token Economy (`default_model`,
  `meta_agent_model`, `review_diff_max_chars`), Criteria Judge (`judge_*`),
  real Resource Limits (cost/time gates, `event_retention_days`, `test_command`,
  `completion_guard_enabled`).
- **B7** `development_tiered` added to the workflow selector.
- **B2 (partial)** New-task modal gains complexity + dependency pickers; the
  drawer shows complexity and per-step model overrides.

## Files changed

- Backend: `foreman/dashboard_service.py` (create_task fields, evidence
  serializer, get_task), `foreman/dashboard_backend.py` (create_task route).
- Frontend: `frontend/src/api.js`, `App.jsx`, `components.jsx`, `styles.css`,
  `App.test.jsx`; rebuilt `foreman/dashboard_frontend_dist/`.
- Tests: `tests/test_dashboard.py` (+5), `frontend/src/App.test.jsx` (+1, plus
  fixed two pre-existing failures — the mock lacked `listGates`, and the
  human-guidance test never selected a task).
- Docs: `docs/reviews/frontend-gap-analysis.md` (resolution tags),
  `docs/prs/feat-frontend-backend-binding.md`, CHANGELOG, STATUS.

## Migrations

- none.

## Risks

- Settings keys persisted by the *old* panel (e.g. `approve_merges`,
  `max_tokens_per_task`) remain in existing projects' settings JSON; they were
  always inert and `ProjectSettings.from_raw` ignores them. No migration needed.
- The supervision banner derives the pending attention event from the loaded
  sprint events; dismissal is client-side. Re-asking a consumed event is handled
  by the backend 409.

## Tests

- `npm --prefix frontend test` → 4 passed (added supervision-banner test; fixed
  2 pre-existing).
- `npm --prefix frontend run build` → rebuilds the committed dist.
- `./venv/bin/python -m unittest tests.test_dashboard` → 137 passed (+5:
  rich create_task happy path, invalid complexity, unknown dependency, evidence
  serialized, evidence-null).
- `./venv/bin/python -m unittest discover -s tests` → full suite green.

## Acceptance criteria satisfied

- Creating a task from the dashboard persists description, complexity, and
  dependencies.
- The task drawer shows completion evidence and per-run models.
- An `engine.attention_needed` event produces a banner that can run a
  supervision turn.
- The settings panel reflects only real `ProjectSettings`, including the
  token-economy and gate fields, and can select `development_tiered`.

## Follow-ups

- B2 full per-task override *editor* (UI to set `executor_overrides`).
- B8 roles inspection/editing surface (`/api/roles`).
- B9 meta history pagination + supervision/chat origin badges.
- B10 surface `zero_cost_token_runs`; D-series polish (dep editing in drawer,
  inline board deny note, dashboard project scaffolding, meta panel in sprint
  view).
