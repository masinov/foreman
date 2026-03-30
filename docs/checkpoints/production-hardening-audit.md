# Checkpoint: production-hardening-audit

## Purpose

Record the implementation-quality reset and the ranked remediation plan for
known bootstrap-era shortcuts that should not remain in the product.

## Highest-priority findings

1. Dashboard architecture is wrong for a production product.
   Current state: the dashboard is embedded in `foreman/dashboard.py` as HTML,
   CSS, JavaScript, API handlers, and SSE transport in one Python module.

2. No dedicated frontend architecture exists.
   Current state: there is no frontend app, no build pipeline, and no browser
   test stack for product UI work.

3. Schema evolution is still unsafe.
   Current state: SQLite bootstraps from `CREATE TABLE IF NOT EXISTS` DDL with
   no migration metadata or ordered upgrades.

4. Some product surfaces are still stubs or incomplete.
   Current state: several CLI commands still route through `handle_stub`, and
   `task_selection_mode="autonomous"` is exposed but not implemented.

5. Validation is weaker than it should be for finished UI surfaces.
   Current state: dashboard coverage is useful, but it leans heavily on API
   checks and string assertions instead of a dedicated frontend or browser
   validation stack.

## Ordered remediation plan

1. `sprint-21-dashboard-api-extraction`
   Extract dashboard reads, actions, and streaming into explicit backend API
   modules.

2. `sprint-22-react-dashboard-foundation`
   Build a dedicated React frontend that consumes the extracted API and
   replaces the embedded Python-served UI.

3. `sprint-23-product-surface-hardening`
   Remove stub CLI surfaces, close important mockup and settings gaps, and
   strengthen validation for shipped product surfaces.

4. `sprint-24-migration-framework-bootstrap`
   Introduce a versioned migration system for SQLite schema evolution.

5. `sprint-25-history-lifecycle-expansion`
   Extend retention and cleanup beyond `events` once migrations exist.

## Decisions recorded here

- bootstrap status now refers to repo memory and sequencing, not acceptable
  implementation quality,
- the product web UI direction is a dedicated React frontend plus Python API,
- future slices should prefer durable boundaries over "fast for now"
  structural shortcuts.
