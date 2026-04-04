# Current Sprint

- Sprint: `sprint-37-autonomy-level-foundation`
- Status: done
- Branch: `feat/sprint-37-autonomy-level-foundation`
- Started: 2026-04-04
- Completed: 2026-04-04

## Goal

Land the autonomy level foundation: `autonomy_level` field on `Project`
(schema migration, model, store, API), project settings UI with a radio
selector, "Start" button adaptation per mode, and enforcement of the
one-active-sprint-per-project constraint at the service layer.

## Tasks

### 1. Schema migration — autonomy_level on projects

- Status: done
- Migration 3: `ALTER TABLE projects ADD COLUMN autonomy_level TEXT NOT NULL DEFAULT 'supervised'`
- `AutonomyLevel` type alias and `AUTONOMY_LEVELS` tuple added to `models.py`
- `Project` dataclass gains `autonomy_level: AutonomyLevel = "supervised"`

### 2. Store — save and load autonomy_level

- Status: done
- `_row_to_project` reads `autonomy_level` from row (falls back to `"supervised"` for pre-migration rows)
- `save_project` includes `autonomy_level` in INSERT/ON CONFLICT UPDATE

### 3. Dashboard service — expose and validate autonomy_level

- Status: done
- `get_project` response includes `autonomy_level`
- `get_project_settings` response includes `autonomy_level`
- `update_project_settings` accepts `autonomy_level`, validates against `AUTONOMY_LEVELS`, rejects unknowns with 400
- `transition_sprint` enforces one-active-sprint-per-project: returns 400 if another sprint is already active

### 4. Settings UI — autonomy level radio selector

- Status: done
- `AUTONOMY_LEVEL_OPTIONS` constant with value/label/description for each mode
- `SettingsPanel` gains a radio group at the top of the Supervision section
- Selected option highlighted with accent border; description shown below label
- CSS: `.autonomy-options`, `.autonomy-option`, `.autonomy-option-label`, `.autonomy-option-desc`

### 5. Sprint list — "Start" button adaptation

- Status: done
- `SprintList` accepts `autonomyLevel` prop
- In `autonomous` mode: "Start" button hidden (agent owns activation)
- In `supervised` mode: button labeled "Promote" with tooltip noting queue bypass
- In `directed` mode: button labeled "Start" as before

### 6. Tests

- Status: done
- `DashboardAutonomyLevelTests` (7 tests):
  - default value is "supervised"
  - settings endpoint returns autonomy_level
  - PATCH updates and persists the value
  - PATCH rejects invalid values
  - all three valid values round-trip correctly
  - transition to active blocked when another sprint is already active
  - transition to active allowed when no active sprint exists
