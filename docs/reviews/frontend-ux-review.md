# Frontend UX / design review

Date: 2026-06-13
Scope: a full walkthrough of the dashboard user flow — landing → project view →
sprint board → task/sprint creation — assessing functionality, state behavior,
labels, and visual consistency. Companion to
`docs/reviews/frontend-gap-analysis.md` (which covered backend binding); this doc
is about polish and UX correctness of what's already wired.
Method: read every screen component and cross-referenced labels/behaviors
against the real backend payloads and event taxonomy.

---

## Flow 1 — Landing (`ProjectOverview`)

- **Dev-jargon subtitle.** "SQLite-backed project state, active sprint summaries,
  and aggregate engine totals." is implementation-speak on the primary landing
  screen.
- **Card footer leaks internals.** Each card shows `directed · development_tiered`
  (raw `task_selection_mode` + `workflow_id`) with no friendly framing.
- **No live-agent signal.** Card status is the *inferred* status ("Running" when
  any task is in-progress), not whether an agent process is live
  (`agent_running`). A card can read "Running" with no process attached.

## Flow 2 — Topbar / breadcrumb

- **Engine-status vs Run/Stop can disagree.** The topbar dot/label uses inferred
  `projectStatus`; the Run/Stop controls now use `agent_running`. On the same
  screen these can contradict. Decide whether "Running" means *task progress* or
  *live agent*, pick one meaning, or render them as two distinct indicators.
- **Sprint dropdown miscolors `cancelled`.** The breadcrumb sprint option styles
  only active/done/planned; `cancelled` falls through to the "planned" color.

## Flow 3 — Project view (`SprintList`)

- **"awaiting approval" is wrong for most blocks.** The project badge renders
  `{n} awaiting approval` for any blocked task, but tasks also block on
  cost/time/loop-limit/evidence — none of which are approvals.
- **Planned sprints behave differently from active/archived.** Clicking a
  *planned* card expands an inline editor; clicking an active/archived card
  navigates to the board. Identical-looking cards, two behaviors — a
  discoverability trap. The inline "Open →" is the only way into a planned sprint.
- **Two divergent task-creation UIs.** The inline queue editor (`addExTask`) and
  `NewTaskModal` are separate forms with different capabilities: the inline one
  is still title/type/criteria only (no description/complexity/dependencies).
  They should share one component.
- **Meta panel labeled "Agent" / hardcoded "Claude Code".** In a product about
  agents, "Agent" is ambiguous for the manager chat; the subtitle hardcodes
  "Claude Code — project operator" even when `meta_agent_model` points elsewhere.

## Flow 4 — Sprint board

- **Title & goal editing is invisible.** Both edit via double-click with no
  affordance, while the task drawer uses a visible ✎ icon. Inconsistent and
  undiscoverable.
- **`cancelled` tasks have no column.** Board lanes are todo/in_progress/blocked/
  done only; cancelled tasks disappear from the board.
- **Approve/Deny shown on every blocked card.** Approve/Deny only applies at a
  human gate; tasks blocked by cost/loop/evidence get the same buttons.
- **Activity filters are partly dead.** "File changes" (`agent.file*`) and
  "Review" (`*review*`) match event types the backend never emits, so those two
  filters always show nothing; meanwhile most real events (`engine.*`,
  `workflow.*`) collapse into one "Workflow" bucket.
- **New roadmap events have no readable summary.** `engine.attention_needed`,
  `engine.completion_evidence`, `workflow.model_selected` fall through
  `formatEventSummary` to printing the raw `event_type`.

## Flow 5 — Task creation (functional bug)

- **`NewTaskModal` offers an invalid type "bug".** `TASK_TYPE_CHIPS =
  [feature, bug, refactor, chore]`, but valid backend `TASK_TYPES` are
  `feature/fix/refactor/docs/spike/chore`. Picking "bug" → backend 400
  "Unsupported task type"; `fix/docs/spike` aren't offered at all. The drawer's
  editor uses the correct list (`TASK_TYPE_OPTIONS`), so the two task forms
  disagree with each other and with the backend.
- **Color classifier mismatch.** `getTaskTypeClass` keys on `bug` (nonexistent)
  and lacks `fix/docs/spike`, so those render with the default "feature" color.
- **Label drift.** The sprint modal's task form labels the description field
  "Context (optional)"; the standalone modal now says "Description".

## Cross-cutting polish

- **Status casing is inconsistent.** Sprint badges show raw lowercase
  (`active`); task statuses are Title-Cased; project statuses Title-Cased.
- **Verb overload.** "Start" activates a *sprint*; "Run" launches the *agent*;
  the empty active slot says "Press Run to start" — three overlapping meanings.
- **Icon system is ad-hoc.** SVG (gear, stop) mixed with unicode glyphs
  (`▶ ▾ ▲ ▼ × ✕ ✎ ⚠`); no consistent icon language.
- **Empty-state copy varies** in tone/casing: "No tasks." / "no sprints queued" /
  "No matching activity yet." / "No runs recorded for this task yet."
- **New CSS uses hardcoded hex** (`#ef5350`, `#ffb300`, `#4caf50`) instead of the
  existing CSS-variable palette, so evidence/supervision colors won't track the
  theme.

## Already addressed in this branch

- The sprint board's lone (dead) **Stop** button is replaced by a Run↔Stop
  toggle driven by `agent_running`, so an idle sprint shows a usable **Run**.

## Suggested priority

1. **Functional bugs:** invalid "bug" task type (creates a 400), dead activity
   filters, the topbar-status vs `agent_running` contradiction.
2. **Unify the two task forms** (one component, full field set, correct type
   list) and **add edit affordances** (pencils on sprint title/goal).
3. **Label / consistency pass:** "awaiting approval" → accurate block reason,
   status casing, friendlier footer/subtitle, event summaries for the new event
   types, empty-state copy, CSS tokens.
4. **Behavioral consistency:** planned-card behavior parity (or an explicit
   inline-edit affordance), a `cancelled` lane/filter, scope Approve/Deny to
   actual gates.
