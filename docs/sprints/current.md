# Current Sprint

- Sprint: `sprint-36-intervention-and-ordering`
- Status: done
- Branch: `feat/sprint-36-intervention-and-ordering`
- Started: 2026-04-02
- Completed: 2026-04-02

## Goal

Fix sprint list ordering so active/completed sprints appear above planned
sprints, and add a coherent manual intervention system to the dashboard: stop
individual tasks, cancel sprints from the sprint view, and surface intervention
controls consistently across the UI.

## Tasks

### 1. Sprint list ordering — active/completed above planned

- Status: done
- Sort order: active first, then completed, then planned (by `order_index`),
  then cancelled. Render order reversed so active/completed appear above the
  "planned" divider.

### 2. Stop/cancel individual task from sprint board and detail drawer

- Status: done
- `POST /api/tasks/{id}/stop` route and `stop_task` service method block an
  in-progress task and emit `human.stop_requested`.
- Stop button on in-progress task cards and in the task detail drawer.

### 3. Cancel sprint from sprint view header

- Status: done
- Active sprints show "Cancel sprint" button alongside "Complete sprint".
- Planned sprints also show "Cancel sprint" in the sprint view header.
- Sprint list cards already had Cancel for both statuses (verified).

### 4. Consistent intervention controls audit

- Status: done
- Sprint list cards: Start, Complete, Cancel for appropriate statuses.
- Sprint view header: Start (planned), Complete + Cancel (active),
  Cancel (planned), Delete (all).
- Task board cards: Stop (in_progress), Approve/Deny (blocked).
- Task detail drawer: Stop (in_progress), Approve/Deny (blocked),
  Cancel (non-terminal), Delete (all).

### 5. Tests and documentation

- Status: done
- 6 new tests in `DashboardInterventionTests`.
- Updated STATUS.md, CHANGELOG.md, current.md, backlog.md.

## Also included (from earlier in same session)

- Board column equal-width fix (`minmax(0, 1fr)`)
- Custom scrollbar styling (thin, dark-themed)
- Activity panel `overflow-x: hidden`
- Duplicate branch name generation fixed in orchestrator
