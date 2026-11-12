# ADR-0020: Dashboard Design v7 Is The UI Reference, And How The Frontend Is Built

- Status: accepted
- Date: 2026-11-12
- Deciders: owner, engine team

## Context

`docs/mockups/foreman-mockup-v6.html` was the UI authority. The shipped
dashboard had diverged from it (project view, settings, policy matrix,
triage, manager chat), and the 2026-11-10 review found the frontend itself
unmaintainable: one 1217-line `App.jsx`, one 2852-line `components.jsx`,
one 4435-line stylesheet, no primitives, state fetched ad hoc.

Phase 4 of the finish plan rebuilds the frontend. The owner and the engine
team agreed a new design on 2026-11-12, screen by screen. The owner's words
on the result: "the base is ready for implementation".

## Decision

### The reference

1. `docs/design/dashboard-v7/` is the UI reference: structure, wording and
   look. Its `README.md` states the rules; the HTML files are the screens.
   Where it and the spec disagree about system behaviour, the spec wins and
   the conflict is recorded in `docs/STATUS.md`.
2. `docs/mockups/foreman-mockup-v6.html` stays in the repository as history.
   It is no longer a reference for anything.
3. The screens are drawings. The product does not copy their inline-styled
   markup.

### The frontend

4. React 18 and Vite, plain JavaScript, as today. No component library and
   no router library. Dependencies are added only with a reason written in
   the PR summary.
5. Source layout under `frontend/src/`:

   | Path | Holds |
   |---|---|
   | `app/` | entry, shell (top bar, breadcrumb, manager side bar slot), router |
   | `api/` | the `/api/v1` client, one module per resource, data hooks |
   | `ui/` | primitives: button, table, tabs, surface, status dot, field, select, menu, dialog, disclosure, mark |
   | `pages/` | one folder per level: `workspace/`, `project/`, `sprint/`, `task/`, `settings/` |
   | `styles/` | `tokens.css` (the design tokens as custom properties) and one stylesheet per area |

   A page composes primitives and hooks. It does not fetch with `fetch`
   directly and does not define colours, sizes or line weights of its own.
6. Routes are paths, so every screen has an address that can be shared:

   | Path | Screen |
   |---|---|
   | `/dashboard` | workspace |
   | `/dashboard/settings` | workspace settings |
   | `/dashboard/projects/{id}` | project, Sprints |
   | `/dashboard/projects/{id}/backlog` | project, Backlog |
   | `/dashboard/projects/{id}/activity` | project, Activity |
   | `/dashboard/projects/{id}/settings` | project settings, General |
   | `/dashboard/projects/{id}/settings/workflow` | project settings, Workflow |
   | `/dashboard/sprints/{id}` and `/board` | sprint, list and board |
   | `/dashboard/tasks/{id}`, `/changes`, `/checks`, `/activity` | task tabs |

7. Data comes through hooks keyed by resource. A hook exposes
   `{data, error, loading, reload}`, ignores a response that arrives after a
   newer request, and refreshes when the project or sprint event stream says
   something changed. Errors are the API's one envelope (ADR-0019) and are
   shown as a sentence, never swallowed.
8. Styling is class-based CSS reading the tokens. The three line weights,
   the single tinted surface and the list caps in the design README are
   rules, not suggestions.
9. Every interactive element is reachable by keyboard, has a visible focus
   state and an accessible name. Motion is off under
   `prefers-reduced-motion`.
10. Each page lands with tests (Vitest and Testing Library) for what it
    shows and what its controls call. The built bundle in
    `foreman/dashboard_frontend_dist` is rebuilt and committed by the change
    that alters the source, as CI checks.
11. During the rebuild the old application stays reachable under
    `/dashboard/legacy`, so nothing an operator can do today is lost between
    merges. The last slice of the rebuild removes it and its files. It is a
    migration seam with a stated end, not a second frontend.

### What the API must add

12. The design needs server behaviour the API does not have. Each lands as
    its own slice with its own tests, before or with the page that uses it:
    a backlog that is not a sprint; paging and filtering on lists; a
    cross-project needs-you list and project milestones; a task's changed
    files and diff. Evidence files are Phase 5 and out of scope here.

## Consequences

- Agents and people building UI read `docs/design/dashboard-v7/README.md`
  first. `AGENTS.md`, `CLAUDE.md`, `README.md` and `docs/ARCHITECTURE.md`
  point there.
- The old `App.jsx`, `components.jsx`, `styles.css` and their tests are
  deleted at the end of the rebuild, not edited.
- The backlog changes what the standing "Intake queue" sprint means. That
  decision gets its own ADR with the slice that makes it.
- A real-browser check is still not possible on the development host
  (Playwright's browser does not install on it). Page tests run in jsdom;
  the look is checked by a person against the drawings.
