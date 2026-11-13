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
   | `/dashboard/projects/{id}/backlog` | the project's backlog (a page of its own, see Amendments) |
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
    shows and what its controls call. **Amended 2026-11-12, by owner
    decision: the built bundle is not in git.** While it was committed, every
    frontend change rebuilt it under new file names, so any two frontend
    branches open at once conflicted; in sprint 58 five merges were sent back
    for that alone. `foreman/dashboard_frontend_dist` is ignored. `foreman
    dashboard` builds it when it is missing or older than the source, CI and
    the project's test step build it, a release builds it before packaging,
    and the API starts without it (the shell route answers 503 and says how
    to build).
11. During the rebuild the old application stayed reachable under
    `/dashboard/legacy`, so nothing an operator could do was lost between
    merges. **Amended 2026-11-12, by owner decision: the seam was removed
    that day, not in the rebuild's last slice.** The dashboard is not in
    production and nobody depends on the old application while the new one is
    built, so keeping it running was wasted effort. `/dashboard/legacy` is
    now an unknown address and renders the not-found page. What the old
    application could do is recorded, with the endpoint and the rebuilt route
    for each thing, in `docs/design/dashboard-v7/legacy-capabilities.md`;
    that file is the checklist the remaining slices are measured against.
    No API endpoint was removed.

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
- The old `App.jsx`, `components.jsx`, `styles.css` and their tests were
  deleted, not edited (2026-11-12, decision 11).
- The backlog changes what the standing "Intake queue" sprint means. That
  decision gets its own ADR with the slice that makes it.
- Page tests run in jsdom. Playwright's browser does not install on the
  development host, but the installed Chrome can be driven directly:
  `scripts/dashboard_shot.mjs` captures any address after clicking, hovering
  or typing (amended 2026-11-13). The look is checked that way against the
  rules in `docs/TESTING.md` ("Checking the look") before a person sees it.

## Amendments, 2026-11-13 (owner review of the running dashboard)

- **The backlog is a page, not a tab.** The owner's rule: a tab changes what
  a page shows and is never a place, so it cannot be a breadcrumb step. The
  backlog has its own address and breadcrumb step
  (`/dashboard/projects/{id}/backlog`, "Project / Backlog") and is reached
  from a button in the project's title row, beside Project settings. The
  project page has two tabs: Sprints and Activity.
- **No "Workspace" breadcrumb step.** The wordmark is the one link to the
  workspace; the breadcrumb starts at the project.
- **Pages stay current on their own** (decision 7): `app/useLiveData.js`
  follows the project's event stream and reloads what the page loaded.
- **Sign in** takes the application's place when the server answers 401.
