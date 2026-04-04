# Current Sprint

- Sprint: `sprint-38-decision-gates`
- Status: done
- Branch: `feat/sprint-38-decision-gates`
- Started: 2026-04-04
- Completed: 2026-04-04

## Goal

Land the full decision gate infrastructure: schema, model, store, service,
API endpoints, and frontend banner with resolve flow. Orchestrator/runner
integration (agent actually detecting contradictions and raising gates) is
deferred — the surface is ready to wire in.

## Tasks

### 1. Schema migration — decision_gates table

- Status: done
- Migration 4: `decision_gates` table with `id`, `project_id`, `sprint_id`,
  `raised_at`, `conflict_description`, `suggested_order`, `suggested_reason`,
  `status`, `resolved_at`, `resolved_by`
- Index: `idx_decision_gates_project` on `(project_id, status)`

### 2. Model — DecisionGate dataclass

- Status: done
- `GateStatus` type alias added to `models.py`
- `DecisionGate` dataclass with all ADR-0006 fields

### 3. Store — save / get / list gates

- Status: done
- `_row_to_gate` helper
- `save_decision_gate`, `get_decision_gate`, `list_decision_gates` (with optional `status` filter)

### 4. Service — create / list / resolve gates

- Status: done
- `create_gate`: validates project and sprint membership, rejects empty description
- `list_gates`: filtered by status or returns all
- `resolve_gate`: accepted → rewrites `order_index` on all sprints in `suggested_order`;
  rejected/dismissed → no reorder; both close the gate
- `_serialize_gate` helper

### 5. Backend — three API endpoints

- Status: done
- `POST /api/projects/{id}/gates`
- `GET /api/projects/{id}/gates[?status=pending]`
- `PATCH /api/gates/{id}` (resolve)

### 6. Frontend — gate banner and resolve flow

- Status: done
- `services.listGates` and `services.resolveGate` in `api.js`
- `refreshProjectScope` fetches pending gates alongside project and sprints
- `pendingGates` state in App; `handleResolveGate` handler
- `DecisionGateBanner` component: header, description, expandable detail
  (reason + suggested order with sprint titles), Accept / Keep current / Dismiss buttons
- `gate-banners` container renders one banner per pending gate above the sprint page bar
- CSS: `.gate-banner*`, `.gate-btn*` classes

### 7. Tests

- Status: done
- `DashboardDecisionGateTests` (9 tests): create, reject empty description, reject
  unknown project, list filtered/unfiltered, accept reorders sprints, reject
  preserves order, double-resolve blocked, invalid resolution rejected
