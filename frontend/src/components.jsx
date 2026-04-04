import { useEffect, useMemo, useRef, useState } from "react";

import {
  eventMatchesFilter,
  formatCompactCount,
  formatCount,
  formatDate,
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

function totalsSummaryLine(projectTotals) {
  const project = projectTotals?.total_token_count ? formatCompactCount(projectTotals.total_token_count) : null;
  if (project) {
    return `${project} tokens`;
  }
  return "No tokens used yet";
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
        <div className="topbar-tokens">{totalsSummaryLine(projectTotals)}</div>
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
  { key: "planned", label: "Planned" },
  { key: "active", label: "Active" },
  { key: "done", label: "Done" },
];

function DecisionGateBanner({ gate, sprints, onResolve }) {
  const [expanded, setExpanded] = useState(false);
  const sprintIndex = new Map((sprints || []).map((s) => [s.id, s]));

  const suggestedTitles = (gate.suggested_order || []).map(
    (id, i) => `${i + 1}. ${sprintIndex.get(id)?.title || id}`
  );

  return (
    <div className="gate-banner">
      <div className="gate-banner-header">
        <span className="gate-banner-icon">⚠</span>
        <span className="gate-banner-title">Agent paused — ordering conflict detected</span>
        <button
          className="gate-banner-toggle"
          type="button"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide details" : "Show details"}
        </button>
      </div>
      <p className="gate-banner-desc">{gate.conflict_description}</p>
      {expanded ? (
        <div className="gate-banner-detail">
          {gate.suggested_reason ? (
            <p className="gate-banner-reason">{gate.suggested_reason}</p>
          ) : null}
          {suggestedTitles.length > 0 ? (
            <div className="gate-banner-order">
              <span className="gate-banner-order-label">Suggested order:</span>
              <ol className="gate-banner-order-list">
                {suggestedTitles.map((t, i) => <li key={i}>{t}</li>)}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="gate-banner-actions">
        {gate.suggested_order?.length > 0 ? (
          <button
            className="gate-btn gate-btn-accept"
            type="button"
            onClick={() => onResolve?.(gate.id, "accepted")}
          >
            Accept suggested order
          </button>
        ) : null}
        <button
          className="gate-btn gate-btn-reject"
          type="button"
          onClick={() => onResolve?.(gate.id, "rejected")}
        >
          Keep current order
        </button>
        <button
          className="gate-btn gate-btn-dismiss"
          type="button"
          onClick={() => onResolve?.(gate.id, "dismissed")}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

export function SprintList({ project, sprints, pendingGates, onSelectSprint, onOpenNewSprint, onTransitionSprint, onDeleteSprint, onReorderSprint, onStartAgent, onStopAgent, onResolveGate, onSprintsChanged, services, isActionPending, autonomyLevel }) {
  const [filterKey, setFilterKey] = useState("all");
  const [newestFirst, setNewestFirst] = useState(false);
  const [viewMode, setViewMode] = useState("list");
  const [metaOpen, setMetaOpen] = useState(false);

  const visibleSprints = useMemo(() => {
    const STATUS_RANK = { active: 0, completed: 1, done: 1, cancelled: 2, planned: 3 };
    const filtered = filterKey === "all" ? sprints : sprints.filter((s) => s.status === filterKey);
    return filtered.slice().sort((a, b) => {
      const rankA = STATUS_RANK[a.status] ?? 3;
      const rankB = STATUS_RANK[b.status] ?? 3;
      if (rankA !== rankB) return rankA - rankB;
      const orderA = a.order_index ?? 0;
      const orderB = b.order_index ?? 0;
      return newestFirst ? orderB - orderA : orderA - orderB;
    });
  }, [sprints, filterKey, newestFirst]);

  function renderCard(sprint, { reorderable } = {}) {
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
            <div className="sc-body-main">
              <span className="sc-title">{sprint.title}</span>
              <span className="sc-goal">{sprint.goal || "No goal recorded."}</span>
            </div>
            {sprint.started_at || sprint.completed_at ? (
              <div className="sc-dates">
                {sprint.started_at ? <span>started {formatDate(sprint.started_at)}</span> : null}
                {sprint.completed_at ? <span>closed {formatDate(sprint.completed_at)}</span> : null}
              </div>
            ) : null}
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
        {(onTransitionSprint || onDeleteSprint || reorderable) ? (
          <div className="sc-actions" onClick={(e) => e.stopPropagation()}>
            {reorderable && onReorderSprint ? (
              <>
                <button
                  className="sc-action-btn sc-action-order"
                  type="button"
                  title="Move earlier in queue"
                  onClick={() => onReorderSprint(sprint.id, newestFirst ? "down" : "up")}
                >
                  ↑
                </button>
                <button
                  className="sc-action-btn sc-action-order"
                  type="button"
                  title="Move later in queue"
                  onClick={() => onReorderSprint(sprint.id, newestFirst ? "up" : "down")}
                >
                  ↓
                </button>
                {(onTransitionSprint || onDeleteSprint) ? (
                  <div className="sc-action-sep" />
                ) : null}
              </>
            ) : null}
            {onTransitionSprint && sprint.status === "planned" && autonomyLevel !== "autonomous" ? (
              <button
                className="sc-action-btn"
                type="button"
                title={autonomyLevel === "supervised" ? "Promote to active (bypasses queue order)" : undefined}
                onClick={() => onTransitionSprint(sprint.id, "active")}
              >
                {autonomyLevel === "supervised" ? "Promote" : "Start"}
              </button>
            ) : null}
            {onTransitionSprint && sprint.status === "active" ? (
              <button
                className="sc-action-btn"
                type="button"
                onClick={() => onTransitionSprint(sprint.id, "completed")}
              >
                Complete
              </button>
            ) : null}
            {onTransitionSprint && (sprint.status === "planned" || sprint.status === "active") ? (
              <button
                className="sc-action-btn sc-action-danger"
                type="button"
                onClick={() => onTransitionSprint(sprint.id, "cancelled")}
              >
                Cancel
              </button>
            ) : null}
            {onDeleteSprint ? (
              <button
                className="sc-action-btn sc-action-danger"
                type="button"
                onClick={() => onDeleteSprint(sprint.id)}
              >
                Delete
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  const runStopButton = project.status === "running" ? (
    <button
      className="btn-stop"
      type="button"
      title="Stop agent"
      aria-label="Stop agent"
      disabled={isActionPending}
      onClick={onStopAgent}
    >
      <svg viewBox="0 0 16 16" width="12" height="12"><rect x="3" y="3" width="10" height="10" rx="1"/></svg>
      Stop
    </button>
  ) : (
    <button
      className="btn-action"
      type="button"
      title="Run agent"
      aria-label="Run agent"
      disabled={isActionPending}
      onClick={onStartAgent}
    >
      ▶ Run
    </button>
  );

  const viewToggle = (
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
  );

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

      {pendingGates && pendingGates.length > 0 ? (
        <div className="gate-banners">
          {pendingGates.map((gate) => (
            <DecisionGateBanner
              key={gate.id}
              gate={gate}
              sprints={sprints}
              onResolve={onResolveGate}
            />
          ))}
        </div>
      ) : null}

      <div className="sprint-page-bar">
        {runStopButton}
        {viewToggle}
        {services ? (
          <button
            className={`meta-toggle-btn${metaOpen ? " active" : ""}`}
            type="button"
            title="Open meta agent"
            onClick={() => setMetaOpen((v) => !v)}
          >
            Meta agent
          </button>
        ) : null}
      </div>

      {viewMode === "list" ? (() => {
        const executedSprints = visibleSprints.filter((s) => s.status !== "planned");
        const plannedSprints = visibleSprints.filter((s) => s.status === "planned");

        return (
          <>
            <div className="sprint-executed-panel">
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
              </div>
              <div className="sprint-executed-list">
                {executedSprints.length > 0
                  ? executedSprints.map((s) => renderCard(s, { reorderable: false }))
                  : <p className="sprint-executed-empty">No sprints have been run yet.</p>}
              </div>
            </div>

            {filterKey === "all" ? (
              <div className="sprint-list-divider"><span>planned</span></div>
            ) : null}

            <div className="sprint-list">
              {plannedSprints.map((s) => renderCard(s, { reorderable: true }))}
            </div>

            {onOpenNewSprint ? (
              <button className="sprint-add-btn" type="button" onClick={onOpenNewSprint}>
                + New sprint
              </button>
            ) : null}
          </>
        );
      })() : (
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
                  {col.key === "planned" && onOpenNewSprint ? (
                    <button className="sprint-add-btn" type="button" onClick={onOpenNewSprint}>
                      + New sprint
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
      )}
      {services && metaOpen ? (
        <MetaAgentPanel
          projectId={project.id}
          services={services}
          onSprintsChanged={onSprintsChanged}
          onClose={() => setMetaOpen(false)}
        />
      ) : null}
    </section>
  );
}

export function TaskCard({ task, selected, onSelect, onApprove, onDeny, onStop }) {
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
      {task.status === "in_progress" && onStop ? (
        <div className="card-actions" onClick={(event) => event.stopPropagation()}>
          <button className="btn btn-stop-task" type="button" onClick={() => onStop(task.id)}>
            Stop
          </button>
        </div>
      ) : null}
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
  onStop,
  onCancel,
  onSave,
  onDelete,
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
        {onStop && task.status === "in_progress" ? (
          <div className="detail-section">
            <button
              className="btn btn-stop-task"
              type="button"
              onClick={() => onStop(task.id)}
            >
              Stop task
            </button>
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
        {onDelete ? (
          <div className="detail-section">
            <button
              className="btn btn-delete-task"
              type="button"
              onClick={() => onDelete(task.id)}
            >
              Delete task
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

const AUTONOMY_LEVEL_OPTIONS = [
  {
    value: "directed",
    label: "Directed",
    description: "You control everything. Activate sprints manually; agent runs only the active sprint and stops when done.",
  },
  {
    value: "supervised",
    label: "Supervised",
    description: "Agent follows your queue order strictly. It auto-advances between sprints but stops and notifies you if it detects a conflict it can't resolve.",
  },
  {
    value: "autonomous",
    label: "Autonomous",
    description: "Agent manages sprint sequencing entirely. Your queue order is a hint, not a contract. You can still stop it at any time.",
  },
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
            <div className="form-group">
              <label className="form-label">Autonomy level</label>
              <div className="autonomy-options">
                {AUTONOMY_LEVEL_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={`autonomy-option${(current.autonomy_level || "supervised") === opt.value ? " selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="autonomy_level"
                      value={opt.value}
                      checked={(current.autonomy_level || "supervised") === opt.value}
                      onChange={() => handleTopLevel("autonomy_level", opt.value)}
                    />
                    <span className="autonomy-option-label">{opt.label}</span>
                    <span className="autonomy-option-desc">{opt.description}</span>
                  </label>
                ))}
              </div>
            </div>
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
            <div className="settings-section-title">Meta Agent</div>
            <div className="form-group">
              <label className="form-label">Backend</label>
              <select
                className="form-input"
                value={innerSettings.meta_agent_backend || "claude"}
                onChange={(e) => handleChange("meta_agent_backend", e.target.value)}
              >
                <option value="claude">Claude Code</option>
                <option value="codex">Codex</option>
              </select>
            </div>
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

export function MetaAgentPanel({ projectId, services, onSprintsChanged, onClose }) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const bottomRef = useRef(null);

  // Load history when panel mounts
  useEffect(() => {
    if (historyLoaded) return;
    services.metaHistory(projectId)
      .then((payload) => {
        const rawTurns = payload.turns || [];
        setTurns(rawTurns.map((t) => ({
          role: t.role,
          text: t.text || "",
          toolUses: (t.tool_uses || []).map((u) => ({ name: u.name, status: "done" })),
          done: true,
        })));
        setHistoryLoaded(true);
      })
      .catch(() => setHistoryLoaded(true));
  }, [historyLoaded, projectId, services]);

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  async function handleSend() {
    const msg = input.trim();
    if (!msg || streaming) return;
    setInput("");
    setError("");

    setTurns((prev) => [...prev, { role: "user", text: msg, toolUses: [], done: true }]);
    const assistantTurn = { role: "assistant", text: "", toolUses: [], done: false };
    setTurns((prev) => [...prev, assistantTurn]);
    setStreaming(true);

    try {
      for await (const event of services.metaMessage(projectId, msg)) {
        if (event.type === "text_delta") {
          setTurns((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };
            last.text = last.text + event.text;
            next[next.length - 1] = last;
            return next;
          });
          scrollToBottom();
        } else if (event.type === "tool_use") {
          setTurns((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };
            last.toolUses = [...last.toolUses, { name: event.name, status: "running" }];
            next[next.length - 1] = last;
            return next;
          });
        } else if (event.type === "done") {
          onSprintsChanged?.();
        } else if (event.type === "error") {
          setError(event.message);
        }
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setStreaming(false);
      setTurns((prev) => {
        const next = [...prev];
        const last = { ...next[next.length - 1] };
        last.done = true;
        // Mark any still-running tools as done
        last.toolUses = last.toolUses.map((t) =>
          t.status === "running" ? { ...t, status: "done" } : t,
        );
        next[next.length - 1] = last;
        return next;
      });
      scrollToBottom();
    }
  }

  async function handleClear() {
    try {
      await services.clearMetaSession(projectId);
      setTurns([]);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="meta-panel">
      <div className="meta-panel-header">
        <div className="meta-panel-title-row">
          <span className="meta-panel-title">Meta agent</span>
          <span className="meta-panel-subtitle">Claude Code — project operator</span>
        </div>
        <div className="meta-panel-actions">
          <button className="meta-action-btn" type="button" onClick={handleClear} title="Clear session">
            Clear
          </button>
          <button className="meta-action-btn" type="button" onClick={onClose} title="Close">
            ✕
          </button>
        </div>
      </div>

      <div className="meta-panel-body">
        {!historyLoaded ? (
          <div className="meta-panel-empty">Loading…</div>
        ) : turns.length === 0 ? (
          <div className="meta-panel-empty">
            Ask me to inspect the codebase, run tests, create branches, reorder sprints, or make changes directly.
          </div>
        ) : (
          turns.map((turn, i) => (
            <div key={i} className={`meta-turn meta-turn-${turn.role}`}>
              {turn.toolUses.length > 0 ? (
                <div className="meta-tool-uses">
                  {turn.toolUses.map((t, j) => (
                    <span key={j} className={`meta-tool-chip meta-tool-${t.status}`}>
                      {t.status === "running" ? "⟳" : "✓"} {t.name}
                    </span>
                  ))}
                </div>
              ) : null}
              {turn.text ? <p className="meta-turn-text">{turn.text}</p> : null}
              {streaming && i === turns.length - 1 && !turn.done ? (
                <span className="meta-cursor" />
              ) : null}
            </div>
          ))
        )}
        {error ? <div className="meta-error">{error}</div> : null}
        <div ref={bottomRef} />
      </div>

      <div className="meta-input-row">
        <textarea
          className="meta-input"
          rows={3}
          placeholder="Describe a change, ask a question, or give a directive…"
          value={input}
          disabled={streaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="meta-send-btn"
          type="button"
          disabled={streaming || !input.trim()}
          onClick={handleSend}
        >
          {streaming ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
