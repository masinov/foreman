import { useMemo, useState } from "react";

import {
  eventMatchesFilter,
  formatCompactCount,
  formatCount,
  formatDuration,
  formatEventSummary,
  formatEventTime,
  formatProjectStatus,
  formatTaskStatus,
  formatTokenCount,
  formatWorkflowCounts,
  getEventCategory,
  getTaskTypeClass,
} from "./format";

export const STATUS_COLUMNS = [
  { key: "todo", label: "Todo" },
  { key: "in_progress", label: "In Progress" },
  { key: "blocked", label: "Blocked" },
  { key: "done", label: "Done" },
];

export const EVENT_FILTERS = [
  { key: "all", label: "All events" },
  { key: "message", label: "Agent messages" },
  { key: "file", label: "File changes" },
  { key: "workflow", label: "Workflow" },
  { key: "human", label: "Human" },
  { key: "review", label: "Review" },
];

function totalsSummaryLine(sprintTotals, projectTotals) {
  const sprint = sprintTotals?.total_token_count ? formatCompactCount(sprintTotals.total_token_count) : null;
  const project = projectTotals?.total_token_count ? formatCompactCount(projectTotals.total_token_count) : null;
  if (sprint && project) {
    return `sprint ${sprint} · project ${project} tokens`;
  }
  if (project) {
    return `project ${project} tokens`;
  }
  return "No run totals yet";
}

function projectStatusClass(status) {
  switch (status) {
    case "running": return "opt-s-running";
    case "active": return "opt-s-active";
    case "idle": return "opt-s-idle";
    case "done": return "opt-s-done";
    case "planned": return "opt-s-planned";
    case "blocked": return "opt-s-blocked";
    default: return "opt-s-idle";
  }
}

export function Topbar({
  projects,
  currentProject,
  currentSprint,
  sprintTotals,
  projectTotals,
  projectStatus,
  onOpenDashboard,
  onSelectProject,
  onSelectSprint,
  onToggleSettings,
}) {
  const [openSegment, setOpenSegment] = useState(null);

  function toggleSegment(name) {
    setOpenSegment((prev) => (prev === name ? null : name));
  }

  function closeAll() {
    setOpenSegment(null);
  }

  return (
    <header className="topbar">
      {openSegment ? <div className="dropdown-overlay visible" onClick={closeAll} /> : null}
      <div className="topbar-left">
        <button className="logo-button" type="button" onClick={onOpenDashboard}>
          <span className="logo">FOREMAN</span>
        </button>
        <nav className="breadcrumb" aria-label="Breadcrumb">
          {currentProject ? (
            <>
              <span className="breadcrumb-sep">/</span>
              <div className={`breadcrumb-segment ${openSegment === "project" ? "open" : ""}`}>
                <span
                  className={`breadcrumb-link ${!currentSprint ? "current" : ""}`}
                  onClick={currentSprint ? () => { closeAll(); onSelectProject(currentProject.id); } : undefined}
                  style={{ cursor: currentSprint ? "pointer" : "default" }}
                >
                  {currentProject.name}
                </span>
                <button
                  className="breadcrumb-chevron"
                  type="button"
                  onClick={(e) => { e.stopPropagation(); toggleSegment("project"); }}
                >
                  &#9662;
                </button>
                <div className="breadcrumb-dropdown">
                  {projects.map((project) => (
                    <div
                      key={project.id}
                      className={`breadcrumb-option ${project.id === currentProject.id ? "active-option" : ""}`}
                      onClick={() => { closeAll(); onSelectProject(project.id); }}
                    >
                      <span>{project.name}</span>
                      <span className={`opt-status ${projectStatusClass(project.status)}`}>
                        {formatProjectStatus(project.status)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : null}
          {currentSprint ? (
            <>
              <span className="breadcrumb-sep">/</span>
              <div className={`breadcrumb-segment ${openSegment === "sprint" ? "open" : ""}`}>
                <span className="breadcrumb-link current">{currentSprint.title}</span>
                <button
                  className="breadcrumb-chevron"
                  type="button"
                  onClick={(e) => { e.stopPropagation(); toggleSegment("sprint"); }}
                >
                  &#9662;
                </button>
                <div className="breadcrumb-dropdown">
                  {(currentProject?.sprints || []).map((sprint) => {
                    const statusClass = sprint.status === "active" ? "opt-s-active"
                      : sprint.status === "done" ? "opt-s-done"
                      : "opt-s-planned";
                    return (
                      <div
                        key={sprint.id}
                        className={`breadcrumb-option ${sprint.id === currentSprint.id ? "active-option" : ""}`}
                        onClick={() => { closeAll(); onSelectSprint(sprint.id); }}
                      >
                        <span>{sprint.title}</span>
                        <span className={`opt-status ${statusClass}`}>{sprint.status}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          ) : null}
        </nav>
      </div>
      <div className="topbar-right">
        <div className="topbar-tokens">{totalsSummaryLine(sprintTotals, projectTotals)}</div>
        <div className={`engine-status ${projectStatus || "idle"}`}>
          <span className="dot" />
          <span>{formatProjectStatus(projectStatus || "idle")}</span>
        </div>
        {onToggleSettings ? (
          <button className="topbar-btn" title="Settings" onClick={onToggleSettings}>
            <svg viewBox="0 0 24 24"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        ) : null}
      </div>
    </header>
  );
}

export function ProjectOverview({ projects, onSelectProject, onNewProject }) {
  return (
    <section className="dashboard view visible">
      <div className="dashboard-overview-header">
        <div>
          <div className="page-title">Projects</div>
          <div className="page-subtitle">
            SQLite-backed project state, active sprint summaries, and aggregate engine totals.
          </div>
        </div>
        {onNewProject ? (
          <button className="btn-action" type="button" onClick={onNewProject}>
            + New project
          </button>
        ) : null}
      </div>
      <div className="dashboard-grid">
        {projects.map((project) => {
          return (
            <button
              key={project.id}
              className="project-card"
              type="button"
              aria-label={`Open project ${project.name}`}
              onClick={() => onSelectProject(project.id)}
            >
              <div className="pc-header">
                <div className="pc-name">{project.name}</div>
                <div className={`pc-status s-${project.status}`}>{formatProjectStatus(project.status)}</div>
              </div>
              <div className="pc-sprint">
                {project.active_sprint
                  ? `${project.active_sprint.title}${project.active_sprint.goal ? ` \u2014 ${project.active_sprint.goal}` : ""}`
                  : "No active sprint"}
              </div>
              <div className="pc-tasks">
                <span><span className="n">{formatCount(project.task_counts.done)}</span> done</span>
                <span><span className="n">{formatCount(project.task_counts.in_progress)}</span> in progress</span>
                {project.task_counts.blocked > 0 ? (
                  <span><span className="n">{formatCount(project.task_counts.blocked)}</span> blocked</span>
                ) : null}
                <span><span className="n">{formatCount(project.task_counts.todo)}</span> todo</span>
              </div>
              <div className="progress-bar" aria-hidden="true">
                <span className="p-done" style={{ flex: project.task_counts.done || 0 }} />
                <span className="p-wip" style={{ flex: project.task_counts.in_progress || 0 }} />
                <span className="p-blocked" style={{ flex: project.task_counts.blocked || 0 }} />
                <span className="p-todo" style={{ flex: project.task_counts.todo || 0 }} />
              </div>
              <div className="pc-footer">
                <div className="pc-tokens">
                  {project.active_sprint ? "sprint" : "total"}{" "}
                  <span className="v">{formatCompactCount(project.totals?.total_token_count)} tokens</span>
                </div>
                <div>{project.settings?.task_selection_mode || "directed"} · {project.workflow_id || "development"}</div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

const STATUS_FILTER_OPTIONS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "done", label: "Done" },
  { key: "planned", label: "Planned" },
  { key: "cancelled", label: "Cancelled" },
];

const KANBAN_COLUMNS = [
  { key: "active", label: "Active" },
  { key: "done", label: "Done" },
  { key: "planned", label: "Planned" },
];

export function SprintList({ project, sprints, onSelectSprint, onOpenNewSprint, onTransitionSprint }) {
  const [filterKey, setFilterKey] = useState("all");
  const [newestFirst, setNewestFirst] = useState(true);
  const [viewMode, setViewMode] = useState("list");

  const visibleSprints = useMemo(() => {
    const filtered = filterKey === "all" ? sprints : sprints.filter((s) => s.status === filterKey);
    return filtered.slice().sort((a, b) => {
      const orderA = a.order ?? 0;
      const orderB = b.order ?? 0;
      return newestFirst ? orderB - orderA : orderA - orderB;
    });
  }, [sprints, filterKey, newestFirst]);

  return (
    <section className="project-view view visible">
      <div className="project-info">
        <h1>{project.name}</h1>
        <div className="project-meta">
          <span>
            Workflow <span className="v">{project.workflow_id}</span>
          </span>
          <span>
            Default branch <span className="v">{project.default_branch || "main"}</span>
          </span>
          <span>
            Repo <span className="v">{project.repo_path}</span>
          </span>
        </div>
        {project.task_counts?.blocked > 0 ? (
          <div className="project-badges">
            <span className="badge badge-warn">{project.task_counts.blocked} awaiting approval</span>
          </div>
        ) : null}
      </div>
      <div className="sprint-toolbar">
        <div className="sprint-toolbar-left">
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              className={`filter-btn ${filterKey === opt.key ? "active" : ""}`}
              type="button"
              onClick={() => setFilterKey(opt.key)}
            >
              {opt.label}
            </button>
          ))}
          <div className="filter-sep" />
          <button className="sort-btn" type="button" onClick={() => setNewestFirst((v) => !v)}>
            {newestFirst ? "Newest first" : "Oldest first"}
          </button>
        </div>
        <div className="sprint-toolbar-right">
          <div className="view-toggle">
            <button
              className={`view-toggle-btn ${viewMode === "list" ? "active" : ""}`}
              type="button"
              onClick={() => setViewMode("list")}
            >List</button>
            <button
              className={`view-toggle-btn ${viewMode === "board" ? "active" : ""}`}
              type="button"
              onClick={() => setViewMode("board")}
            >Board</button>
          </div>
          {onOpenNewSprint ? (
            <button className="btn-action" type="button" onClick={onOpenNewSprint}>
              <span className="plus">+</span> New sprint
            </button>
          ) : null}
        </div>
      </div>

      {viewMode === "list" ? (
        <div className="sprint-list">
          {visibleSprints.map((sprint) => {
            const counts = sprint.task_counts || {};
            const total = (counts.todo || 0) + (counts.in_progress || 0) + (counts.blocked || 0) + (counts.done || 0);
            const done = counts.done || 0;
            const statusClass = sprint.status === "active" ? "sc-active"
              : sprint.status === "done" ? "sc-completed"
              : sprint.status === "planned" ? "sc-planned"
              : `sc-${sprint.status}`;
            return (
              <div
                key={sprint.id}
                className={`sprint-card ${sprint.status === "active" ? "active-sprint" : ""}`}
              >
                <button
                  className="sc-main"
                  type="button"
                  aria-label={`Open sprint ${sprint.title}`}
                  onClick={() => onSelectSprint(sprint.id)}
                >
                  <div className={`sc-status ${statusClass}`}>{sprint.status}</div>
                  <div className="sc-body">
                    <span className="sc-title">{sprint.title}</span>
                    <span className="sc-goal">{sprint.goal || "No goal recorded."}</span>
                  </div>
                  <div className="sc-tasks-inline">
                    <span>
                      <span className="n">{done}</span>/<span className="n">{total}</span>{" "}
                      {total === done && total > 0 ? "done" : "tasks"}
                    </span>
                    <div className="progress-bar sc-progress-inline" aria-hidden="true">
                      <span className="p-done" style={{ flex: done }} />
                      <span className="p-wip" style={{ flex: counts.in_progress || 0 }} />
                      <span className="p-blocked" style={{ flex: counts.blocked || 0 }} />
                      <span className="p-todo" style={{ flex: counts.todo || 0 }} />
                    </div>
                  </div>
                  <div className="sc-stats-inline">
                    {sprint.totals?.total_token_count > 0 ? (
                      <>
                        <span><span>{formatCompactCount(sprint.totals.total_token_count)}</span> tok</span>
                        <span><span>{formatCount(sprint.totals.run_count)}</span> runs</span>
                      </>
                    ) : (
                      <span>—</span>
                    )}
                  </div>
                </button>
                {onTransitionSprint ? (
                  <div className="sc-actions" onClick={(e) => e.stopPropagation()}>
                    {sprint.status === "planned" ? (
                      <button
                        className="sc-action-btn"
                        type="button"
                        onClick={() => onTransitionSprint(sprint.id, "active")}
                      >
                        Start
                      </button>
                    ) : null}
                    {sprint.status === "active" ? (
                      <button
                        className="sc-action-btn"
                        type="button"
                        onClick={() => onTransitionSprint(sprint.id, "completed")}
                      >
                        Complete
                      </button>
                    ) : null}
                    {sprint.status === "planned" || sprint.status === "active" ? (
                      <button
                        className="sc-action-btn sc-action-danger"
                        type="button"
                        onClick={() => onTransitionSprint(sprint.id, "cancelled")}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="sprint-kanban">
          {KANBAN_COLUMNS.map((col) => {
            const colSprints = sprints.filter((s) => {
              if (col.key === "active") return s.status === "active";
              if (col.key === "done") return s.status === "done" || s.status === "completed" || s.status === "cancelled";
              return s.status === "planned";
            });
            return (
              <div key={col.key} className="sk-column">
                <div className="sk-col-header">
                  <span className="sk-col-title">{col.label}</span>
                  <span className="sk-col-count">{colSprints.length}</span>
                </div>
                {colSprints.map((sprint) => {
                  const counts = sprint.task_counts || {};
                  const total = (counts.todo || 0) + (counts.in_progress || 0) + (counts.blocked || 0) + (counts.done || 0);
                  const done = counts.done || 0;
                  return (
                    <button
                      key={sprint.id}
                      className={`sk-card ${sprint.status === "active" ? "active-sprint" : ""}`}
                      type="button"
                      onClick={() => onSelectSprint(sprint.id)}
                    >
                      <div className="sk-card-title">{sprint.title}</div>
                      <div className="sk-card-goal">{sprint.goal || "No goal recorded."}</div>
                      <div className="sk-card-footer">
                        <div className="sk-card-tasks">
                          <span><span className="n">{done}</span> done</span>
                          {counts.in_progress > 0 ? <span><span className="n">{counts.in_progress}</span> wip</span> : null}
                          {counts.blocked > 0 ? <span><span className="n">{counts.blocked}</span> blocked</span> : null}
                        </div>
                        {sprint.totals?.total_token_count > 0 ? (
                          <span><span className="n">{formatCompactCount(sprint.totals.total_token_count)}</span> tok</span>
                        ) : <span>—</span>}
                      </div>
                      {sprint.status === "active" ? (
                        <div className="progress-bar" style={{ marginTop: "6px" }} aria-hidden="true">
                          <span className="p-done" style={{ flex: done }} />
                          <span className="p-wip" style={{ flex: counts.in_progress || 0 }} />
                          <span className="p-blocked" style={{ flex: counts.blocked || 0 }} />
                          <span className="p-todo" style={{ flex: counts.todo || 0 }} />
                        </div>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function TaskCard({ task, selected, onSelect, onApprove, onDeny }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(task.id);
    }
  }

  return (
    <div
      className={`card ${selected ? "selected" : ""} ${task.status === "blocked" ? "card-blocked" : ""} ${task.status === "done" ? "done-card" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(task.id)}
      onKeyDown={handleKeyDown}
    >
      <div className="card-title">{task.title}</div>
      <div className="card-meta">
        <span className={`card-tag ${getTaskTypeClass(task.task_type)}`}>{task.task_type}</span>
        <span className="card-tokens">{formatTokenCount(task.totals.total_token_count)}</span>
      </div>
      {task.status === "in_progress" && task.workflow_current_step ? (
        <div className="card-step">step: {task.workflow_current_step}</div>
      ) : null}
      {task.branch_name ? <div className="card-branch">{task.branch_name}</div> : null}
      {task.assigned_role ? <div className="card-role">Role: {task.assigned_role}</div> : null}
      {task.blocked_reason ? <div className="card-blocked-reason">{task.blocked_reason}</div> : null}
      {task.status === "blocked" ? (
        <div className="card-actions" onClick={(event) => event.stopPropagation()}>
          <button className="btn btn-approve" type="button" onClick={() => onApprove(task.id)}>
            Approve
          </button>
          <button className="btn btn-deny" type="button" onClick={() => onDeny(task.id)}>
            Deny
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function EventList({ events, filterKey, taskIndex, containerRef, onScroll }) {
  const filteredEvents = events.filter((event) => eventMatchesFilter(event, filterKey));
  return (
    <div className="activity-stream" aria-live="polite" ref={containerRef} onScroll={onScroll}>
      {filteredEvents.length === 0 ? (
        <div className="empty-panel">No matching activity yet.</div>
      ) : (
        filteredEvents.map((event, index) => {
          const category = getEventCategory(event.event_type);
          const taskTitle = taskIndex.get(event.task_id)?.title;
          const isStepStart = event.event_type && event.event_type.includes("step_started");
          return (
            <div key={event.id}>
              {isStepStart && index > 0 ? <div className="event-divider" /> : null}
              <div className="event-row">
                <div className="event-time">{formatEventTime(event.timestamp)}</div>
                <div className="event-icon">
                  <span className={`event-dot dot-${category}`} />
                </div>
                <div className="event-body">
                  <div className="event-label">
                    {event.event_type}
                    {taskTitle ? ` • ${taskTitle}` : ""}
                  </div>
                  <div>{formatEventSummary(event)}</div>
                </div>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

const TASK_TYPE_OPTIONS = ["feature", "fix", "refactor", "docs", "spike", "chore"];

export function TaskDetailDrawer({
  task,
  taskIndex,
  denyNote,
  onClose,
  onApprove,
  onDenyNoteChange,
  onDeny,
  onCancel,
  onSave,
}) {
  const [editing, setEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [taskTypeDraft, setTaskTypeDraft] = useState("");
  const [criteriaDraft, setCriteriaDraft] = useState("");

  if (!task) {
    return null;
  }

  function startEditing() {
    setTitleDraft(task.title);
    setTaskTypeDraft(task.task_type);
    setCriteriaDraft(task.acceptance_criteria || "");
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
  }

  async function saveEditing() {
    if (!titleDraft.trim()) return;
    await onSave(task.id, {
      title: titleDraft.trim(),
      task_type: taskTypeDraft,
      acceptance_criteria: criteriaDraft.trim() || null,
    });
    setEditing(false);
  }

  return (
    <aside className="detail-overlay" id="detail-panel" aria-label="Task detail">
      <div className="detail-header">
        <div className="detail-header-title-row">
          {editing ? (
            <input
              className="detail-title-input"
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              aria-label="Task title"
            />
          ) : (
            <h2>{task.title}</h2>
          )}
          {onSave && !editing ? (
            <button className="detail-edit-btn" type="button" onClick={startEditing} aria-label="Edit task">
              ✎
            </button>
          ) : null}
        </div>
        <div className="detail-kicker">
          {editing ? (
            <div className="detail-type-chips">
              {TASK_TYPE_OPTIONS.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`card-tag type-chip ${getTaskTypeClass(t)} ${taskTypeDraft === t ? "chip-selected" : ""}`}
                  onClick={() => setTaskTypeDraft(t)}
                >
                  {t}
                </button>
              ))}
            </div>
          ) : (
            <>
              <span className={`card-tag ${getTaskTypeClass(task.task_type)}`}>{task.task_type}</span>
              <span className="detail-status">{formatTaskStatus(task.status)}</span>
            </>
          )}
        </div>
        {!editing ? (
          <button className="detail-close" type="button" onClick={onClose} aria-label="Close task detail">
            ×
          </button>
        ) : null}
      </div>
      {editing ? (
        <div className="detail-edit-actions">
          <button className="btn btn-save-edit" type="button" onClick={saveEditing} disabled={!titleDraft.trim()}>
            Save
          </button>
          <button className="btn btn-cancel-edit" type="button" onClick={cancelEditing}>
            Cancel
          </button>
        </div>
      ) : null}
      <div className="detail-body">
        {task.description ? (
          <div className="detail-section">
            <div className="detail-section-title">Description</div>
            <div className="detail-text">{task.description}</div>
          </div>
        ) : null}
        <div className="detail-section">
          <div className="detail-section-title">Details</div>
          {task.workflow_current_step ? (
            <div className="detail-field">
              <span className="detail-field-label">Step</span>
              <span className="detail-field-value detail-step">{task.workflow_current_step}</span>
            </div>
          ) : null}
          <div className="detail-field">
            <span className="detail-field-label">Branch</span>
            <span className="detail-field-value">{task.branch_name || "—"}</span>
          </div>
          <div className="detail-field">
            <span className="detail-field-label">Role</span>
            <span className="detail-field-value">{task.assigned_role || "Unassigned"}</span>
          </div>
          {task.priority > 0 ? (
            <div className="detail-field">
              <span className="detail-field-label">Priority</span>
              <span className="detail-field-value">{task.priority}</span>
            </div>
          ) : null}
          <div className="detail-field">
            <span className="detail-field-label">Tokens</span>
            <span className="detail-field-value">{formatTokenCount(task.totals.total_token_count)}</span>
          </div>
          <div className="detail-field">
            <span className="detail-field-label">Step visits</span>
            <span className="detail-field-value">{formatWorkflowCounts(task.step_visit_counts)}</span>
          </div>
        </div>
        {task.depends_on_task_ids && task.depends_on_task_ids.length > 0 ? (
          <div className="detail-section">
            <div className="detail-section-title">Dependencies</div>
            <div className="detail-deps">
              {task.depends_on_task_ids.map((depId) => {
                const depTask = taskIndex?.get(depId);
                return (
                  <span key={depId} className="dep-chip">
                    {depTask ? depTask.title : depId}
                  </span>
                );
              })}
            </div>
          </div>
        ) : null}
        <div className="detail-section">
          <div className="detail-section-title">Acceptance Criteria</div>
          {editing ? (
            <textarea
              className="detail-textarea"
              value={criteriaDraft}
              onChange={(e) => setCriteriaDraft(e.target.value)}
              placeholder="Describe what done looks like."
              rows={4}
            />
          ) : (
            <div className="detail-criteria">{task.acceptance_criteria || <span className="detail-empty">None specified.</span>}</div>
          )}
        </div>
        {task.blocked_reason ? (
          <div className="detail-section">
            <div className="detail-section-title">Blocked Reason</div>
            <div className="detail-text blocked-text">{task.blocked_reason}</div>
          </div>
        ) : null}
        {task.status === "blocked" ? (
          <div className="detail-section">
            <div className="detail-section-title">Human Gate</div>
            <div className="detail-actions">
              <button className="btn btn-approve" type="button" onClick={() => onApprove(task.id)}>
                Approve
              </button>
              <button className="btn btn-deny" type="button" onClick={() => onDeny(task.id)}>
                Deny
              </button>
            </div>
            <label className="detail-label" htmlFor="deny-note">Denial note</label>
            <textarea
              id="deny-note"
              className="detail-textarea"
              value={denyNote}
              onChange={(event) => onDenyNoteChange(event.target.value)}
              placeholder="Explain what needs to change before this task can continue."
            />
          </div>
        ) : null}
        {onCancel && task.status !== "done" && task.status !== "cancelled" ? (
          <div className="detail-section">
            <button
              className="btn btn-cancel-task"
              type="button"
              onClick={() => onCancel(task.id)}
            >
              Cancel task
            </button>
          </div>
        ) : null}
        <div className="detail-section">
          <div className="detail-section-title">Run History</div>
          <div className="run-timeline">
            {task.runs.length === 0 ? (
              <div className="empty-panel">No runs recorded for this task yet.</div>
            ) : (
              task.runs.map((run) => (
                <div key={run.id} className="run-entry">
                  <span className="run-role">{run.role_id}</span>
                  <span className="run-detail-text">
                    {run.workflow_step}{run.duration_ms ? ` · ${formatDuration(run.duration_ms)}` : ""}
                  </span>
                  <span className="run-entry-right">
                    <span className={`run-outcome outcome-${run.status}`}>{run.status}</span>
                    <div className="run-tokens">{formatTokenCount(run.token_count)}</div>
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

export function EmptyPanel({ title, message }) {
  return (
    <div className="empty-panel">
      <div className="empty-title">{title}</div>
      <div>{message}</div>
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }) {
  if (!message) {
    return null;
  }
  return (
    <div className="error-banner" role="alert">
      <span>{message}</span>
      <button className="detail-close" type="button" onClick={onDismiss} aria-label="Dismiss error">
        ×
      </button>
    </div>
  );
}

const WORKFLOW_OPTIONS = [
  { value: "development", label: "development" },
  { value: "development_with_architect", label: "development_with_architect" },
  { value: "development_secure", label: "development_secure" },
];


export function SettingsPanel({ settings, onUpdate, onClose }) {
  const [draft, setDraft] = useState(null);

  const current = draft || settings;
  if (!current) {
    return null;
  }

  const innerSettings = current.settings || {};

  function handleChange(field, value) {
    setDraft((prev) => {
      const base = prev || { ...current };
      return { ...base, settings: { ...(base.settings || {}), [field]: value } };
    });
  }

  function handleTopLevel(field, value) {
    setDraft((prev) => {
      const base = prev || { ...current };
      return { ...base, [field]: value };
    });
  }

  function handleSave() {
    if (!draft) return;
    onUpdate(draft);
    setDraft(null);
  }

  return (
    <>
      <div className="settings-backdrop visible" onClick={onClose} />
      <aside className="settings-overlay visible" aria-label="Project settings">
        <div className="settings-header">
          <h3>Project Settings</h3>
          <button className="modal-close" type="button" onClick={onClose}>×</button>
        </div>
        <div className="settings-body">
          <div className="settings-section">
            <div className="settings-section-title">Supervision</div>
            <SettingsToggle
              label="Approve merges"
              description="Require human approval before merging to target branch"
              checked={innerSettings.approve_merges ?? true}
              onChange={(checked) => handleChange("approve_merges", checked)}
            />
            <SettingsToggle
              label="Approve task completion"
              description="Require human sign-off before marking a task done"
              checked={innerSettings.approve_task_completion ?? true}
              onChange={(checked) => handleChange("approve_task_completion", checked)}
            />
            <SettingsToggle
              label="Approve sprint completion"
              description="Require human sign-off before closing a sprint"
              checked={innerSettings.approve_sprint_completion ?? true}
              onChange={(checked) => handleChange("approve_sprint_completion", checked)}
            />
            <SettingsToggle
              label="Allow autonomous task selection"
              description="Engine picks the next task instead of waiting for assignment"
              checked={innerSettings.task_selection_mode === "autonomous"}
              onChange={(checked) => handleChange("task_selection_mode", checked ? "autonomous" : "directed")}
            />
            <SettingsToggle
              label="Allow agent to create tasks"
              description="Engine may add tasks to the sprint during a run"
              checked={innerSettings.agent_can_create_tasks ?? true}
              onChange={(checked) => handleChange("agent_can_create_tasks", checked)}
            />
            <SettingsToggle
              label="Approve architect plans"
              description="Require human approval of architect-generated plans"
              checked={innerSettings.approve_architect_plans ?? true}
              onChange={(checked) => handleChange("approve_architect_plans", checked)}
            />
          </div>
          <div className="settings-section">
            <div className="settings-section-title">Workflow</div>
            <div className="form-group">
              <label className="form-label">Default workflow</label>
              <select
                className="form-input"
                value={current.workflow_id || "development"}
                onChange={(e) => handleTopLevel("workflow_id", e.target.value)}
              >
                {WORKFLOW_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Merge target</label>
              <input
                className="form-input"
                type="text"
                value={current.default_branch || "main"}
                onChange={(e) => handleTopLevel("default_branch", e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Spec file</label>
              <input
                className="form-input"
                type="text"
                value={current.spec_path || ""}
                onChange={(e) => handleTopLevel("spec_path", e.target.value)}
              />
            </div>
          </div>
          <div className="settings-section">
            <div className="settings-section-title">Resource Limits</div>
            <div className="form-group">
              <label className="form-label">Max tokens per task</label>
              <input
                className="form-input"
                type="number"
                min="0"
                style={{ fontVariantNumeric: "tabular-nums" }}
                value={innerSettings.max_tokens_per_task ?? 200000}
                onChange={(e) => handleChange("max_tokens_per_task", Number(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Max step visits (loop limit)</label>
              <input
                className="form-input"
                type="number"
                min="1"
                value={innerSettings.max_step_visits ?? 5}
                onChange={(e) => handleChange("max_step_visits", Number(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Max retries on infrastructure error</label>
              <input
                className="form-input"
                type="number"
                min="0"
                value={innerSettings.max_infra_retries ?? 3}
                onChange={(e) => handleChange("max_infra_retries", Number(e.target.value))}
              />
            </div>
          </div>
        </div>
        {draft ? (
          <div className="settings-footer">
            <button className="btn-cancel" type="button" onClick={() => setDraft(null)}>Discard</button>
            <button className="btn-primary" type="button" onClick={handleSave}>Save settings</button>
          </div>
        ) : null}
      </aside>
    </>
  );
}

function SettingsToggle({ label, description, checked, onChange }) {
  return (
    <div className="settings-row">
      <div className="settings-label">
        <span className="settings-label-text">{label}</span>
        {description ? <span className="settings-label-desc">{description}</span> : null}
      </div>
      <label className="toggle">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
    </div>
  );
}

export function NewSprintModal({ onSubmit, onClose }) {
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [pendingTasks, setPendingTasks] = useState([]);
  const [taskInput, setTaskInput] = useState("");

  function addTask() {
    const trimmed = taskInput.trim();
    if (!trimmed) return;
    setPendingTasks((prev) => [...prev, { title: trimmed, task_type: "feature" }]);
    setTaskInput("");
  }

  function removeTask(index) {
    setPendingTasks((prev) => prev.filter((_, i) => i !== index));
  }

  function handleTaskKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      addTask();
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      goal: goal.trim() || undefined,
      initialTasks: pendingTasks.length > 0 ? pendingTasks : undefined,
    });
  }

  return (
    <div className="modal-backdrop visible" onClick={onClose}>
      <div className="modal" style={{ width: "540px" }} onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h3>New Sprint</h3>
            <button className="modal-close" type="button" onClick={onClose}>×</button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Title</label>
              <input className="form-input" type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Sprint 5" autoFocus />
            </div>
            <div className="form-group">
              <label className="form-label">Goal</label>
              <textarea className="form-input" style={{ minHeight: "48px" }} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What should this sprint accomplish?" />
            </div>
            <div className="form-group">
              <label className="form-label">Initial tasks (optional)</label>
              <div className="task-entry-row">
                <input
                  className="form-input"
                  type="text"
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  onKeyDown={handleTaskKeyDown}
                  placeholder="Task title — press Enter or Add"
                />
                <button
                  className="btn-action"
                  type="button"
                  onClick={addTask}
                  disabled={!taskInput.trim()}
                >
                  Add
                </button>
              </div>
              {pendingTasks.length > 0 ? (
                <ul className="pending-tasks">
                  {pendingTasks.map((t, i) => (
                    <li key={i} className="pending-task-item">
                      <span>{t.title}</span>
                      <button
                        className="pending-task-remove"
                        type="button"
                        onClick={() => removeTask(i)}
                        aria-label={`Remove task ${t.title}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
          <div className="modal-footer">
            <button className="btn-cancel" type="button" onClick={onClose}>Cancel</button>
            <button className="btn-primary" type="submit" disabled={!title.trim()}>Create sprint</button>
          </div>
        </form>
      </div>
    </div>
  );
}

const TASK_TYPE_CHIPS = ["feature", "bug", "refactor", "chore"];

export function NewTaskModal({ onSubmit, onClose }) {
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState("feature");
  const [criteria, setCriteria] = useState("");
  const [context, setContext] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      taskType,
      acceptanceCriteria: criteria.trim() || undefined,
      context: context.trim() || undefined,
    });
  }

  return (
    <div className="modal-backdrop visible" onClick={onClose}>
      <div className="modal" style={{ width: "480px" }} onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h3>New Task</h3>
            <button className="modal-close" type="button" onClick={onClose}>×</button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Title</label>
              <input className="form-input" type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short description of the task" autoFocus />
            </div>
            <div className="form-group">
              <label className="form-label">Acceptance criteria</label>
              <textarea className="form-input" style={{ minHeight: "48px" }} value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="What must be true for this task to be done?" />
            </div>
            <div className="form-group">
              <label className="form-label">Context (optional)</label>
              <textarea className="form-input" style={{ minHeight: "48px" }} value={context} onChange={(e) => setContext(e.target.value)} placeholder="Relevant files, reproduction steps, references..." />
            </div>
            <div className="form-group">
              <label className="form-label">Label (optional)</label>
              <div className="form-chips">
                {TASK_TYPE_CHIPS.map((type) => (
                  <button
                    key={type}
                    type="button"
                    className={`form-chip ${taskType === type ? "selected" : ""}`}
                    onClick={() => setTaskType(type)}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button className="btn-cancel" type="button" onClick={onClose}>Cancel</button>
            <button className="btn-primary" type="submit" disabled={!title.trim()}>Create task</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function NewProjectModal({ onSubmit, onClose }) {
  const [name, setName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [workflowId, setWorkflowId] = useState("development");

  function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim() || !repoPath.trim()) return;
    onSubmit({ name: name.trim(), repoPath: repoPath.trim(), workflowId });
  }

  return (
    <div className="modal-backdrop visible" onClick={onClose}>
      <div className="modal" style={{ width: "480px" }} onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h3>Register Project</h3>
            <button className="modal-close" type="button" onClick={onClose}>×</button>
          </div>
          <div className="modal-body">
            <div className="form-hint">
              Registers a project in the dashboard database. Use <code>foreman init</code> to scaffold CLAUDE.md and workflow files in the repo.
            </div>
            <div className="form-group">
              <label className="form-label">Project name</label>
              <input
                className="form-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My project"
                autoFocus
              />
            </div>
            <div className="form-group">
              <label className="form-label">Repo path</label>
              <input
                className="form-input"
                type="text"
                value={repoPath}
                onChange={(e) => setRepoPath(e.target.value)}
                placeholder="/path/to/repo"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Workflow</label>
              <select
                className="form-input"
                value={workflowId}
                onChange={(e) => setWorkflowId(e.target.value)}
              >
                {WORKFLOW_OPTIONS.map((w) => (
                  <option key={w.value} value={w.value}>{w.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="modal-footer">
            <button className="btn-cancel" type="button" onClick={onClose}>Cancel</button>
            <button
              className="btn-primary"
              type="submit"
              disabled={!name.trim() || !repoPath.trim()}
            >
              Register project
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
