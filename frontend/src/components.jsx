import { useState } from "react";

import {
  eventMatchesFilter,
  formatCompactCount,
  formatCount,
  formatCurrency,
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
  { key: "cancelled", label: "Cancelled" },
];

export const EVENT_FILTERS = [
  { key: "all", label: "All events" },
  { key: "message", label: "Agent messages" },
  { key: "file", label: "File changes" },
  { key: "workflow", label: "Workflow" },
  { key: "human", label: "Human" },
  { key: "review", label: "Review" },
];

function totalsSummaryLine(totals) {
  if (!totals) {
    return "No run totals yet";
  }
  return `${formatCount(totals.run_count)} runs • ${formatTokenCount(totals.total_token_count)} • ${formatCurrency(totals.total_cost_usd)}`;
}

export function Topbar({
  projects,
  currentProject,
  currentSprint,
  totals,
  projectStatus,
  onOpenDashboard,
  onSelectProject,
  onSelectSprint,
  onToggleSettings,
}) {
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [sprintMenuOpen, setSprintMenuOpen] = useState(false);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="logo-button" type="button" onClick={onOpenDashboard}>
          <span className="logo">FOREMAN</span>
        </button>
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <button className="breadcrumb-link current" type="button" onClick={onOpenDashboard}>
            Projects
          </button>
          {currentProject ? (
            <>
              <span className="breadcrumb-sep">/</span>
              <div className="switcher">
                <button
                  className="breadcrumb-link"
                  type="button"
                  onClick={() => setProjectMenuOpen((open) => !open)}
                >
                  {currentProject.name}
                </button>
                {projectMenuOpen ? (
                  <div className="switcher-menu" role="menu">
                    {projects.map((project) => (
                      <button
                        key={project.id}
                        className={`switcher-item ${project.id === currentProject.id ? "current" : ""}`}
                        type="button"
                        onClick={() => {
                          setProjectMenuOpen(false);
                          onSelectProject(project.id);
                        }}
                      >
                        <span>{project.name}</span>
                        <span className={`ps-status s-${project.status}`}>{formatProjectStatus(project.status)}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
          {currentSprint ? (
            <>
              <span className="breadcrumb-sep">/</span>
              <div className="switcher">
                <button
                  className="breadcrumb-link current"
                  type="button"
                  onClick={() => setSprintMenuOpen((open) => !open)}
                >
                  {currentSprint.title}
                </button>
                {sprintMenuOpen ? (
                  <div className="switcher-menu" role="menu">
                    {(currentProject?.sprints || []).map((sprint) => (
                      <button
                        key={sprint.id}
                        className={`switcher-item ${sprint.id === currentSprint.id ? "current" : ""}`}
                        type="button"
                        onClick={() => {
                          setSprintMenuOpen(false);
                          onSelectSprint(sprint.id);
                        }}
                      >
                        <span>{sprint.title}</span>
                        <span className={`ps-status sc-${sprint.status}`}>{sprint.status}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </nav>
      </div>
      <div className="topbar-right">
        <div className="topbar-tokens">{totalsSummaryLine(totals)}</div>
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

export function ProjectOverview({ projects, onSelectProject }) {
  return (
    <section className="dashboard view visible">
      <div className="page-title">Projects</div>
      <div className="page-subtitle">
        SQLite-backed project state, active sprint summaries, and aggregate engine totals.
      </div>
      <div className="dashboard-grid">
        {projects.map((project) => {
          const totalTasks = Object.values(project.task_counts || {}).reduce((sum, value) => sum + value, 0);
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
                {project.active_sprint ? `Active sprint: ${project.active_sprint.title}` : "No active sprint"}
              </div>
              <div className="pc-tasks">
                <span>
                  <span className="n">{formatCount(project.task_counts.todo)}</span> todo
                </span>
                <span>
                  <span className="n">{formatCount(project.task_counts.in_progress)}</span> in progress
                </span>
                <span>
                  <span className="n">{formatCount(project.task_counts.blocked)}</span> blocked
                </span>
                <span>
                  <span className="n">{formatCount(project.task_counts.done)}</span> done
                </span>
              </div>
              <div className="progress-bar" aria-hidden="true">
                <span className="p-todo" style={{ flex: project.task_counts.todo || 0 }} />
                <span className="p-wip" style={{ flex: project.task_counts.in_progress || 0 }} />
                <span className="p-blocked" style={{ flex: project.task_counts.blocked || 0 }} />
                <span className="p-done" style={{ flex: project.task_counts.done || 0 }} />
              </div>
              <div className="pc-footer">
                <span>
                  Runs <span className="v">{formatCount(project.totals.run_count)}</span>
                </span>
                <span>
                  Tokens <span className="v">{formatCompactCount(project.totals.total_token_count)}</span>
                </span>
                <span>
                  Cost <span className="v">{formatCurrency(project.totals.total_cost_usd)}</span>
                </span>
                <span>
                  Tasks <span className="v">{formatCount(totalTasks)}</span>
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function SprintList({ project, sprints, onSelectSprint, onOpenNewSprint }) {
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
      </div>
      <div className="sprint-toolbar">
        <div className="sprint-toolbar-left">
          <div className="page-subtitle">Sprints are ordered and backed by persisted SQLite state.</div>
        </div>
        {onOpenNewSprint ? (
          <div className="sprint-toolbar-right">
            <button className="btn-action" type="button" onClick={onOpenNewSprint}>
              <span className="plus">+</span> New sprint
            </button>
          </div>
        ) : null}
      </div>
      <div className="sprint-list">
        {sprints.map((sprint) => (
          <button
            key={sprint.id}
            className={`sprint-card ${sprint.status === "active" ? "active-sprint" : ""}`}
            type="button"
            aria-label={`Open sprint ${sprint.title}`}
            onClick={() => onSelectSprint(sprint.id)}
          >
            <div className={`sc-status sc-${sprint.status}`}>{sprint.status}</div>
            <div className="sc-body">
              <div className="sc-title">{sprint.title}</div>
              <div className="sc-goal">{sprint.goal || "No goal recorded."}</div>
            </div>
            <div className="sc-tasks-inline">
              <span>
                <span className="n">{formatCount(sprint.task_counts.todo)}</span> todo
              </span>
              <span>
                <span className="n">{formatCount(sprint.task_counts.in_progress)}</span> in progress
              </span>
              <span>
                <span className="n">{formatCount(sprint.task_counts.blocked)}</span> blocked
              </span>
              <span>
                <span className="n">{formatCount(sprint.task_counts.done)}</span> done
              </span>
            </div>
            <div className="sc-stats-inline">
              <span>
                runs <span>{formatCount(sprint.totals.run_count)}</span>
              </span>
              <span>
                tokens <span>{formatCompactCount(sprint.totals.total_token_count)}</span>
              </span>
              <span>
                cost <span>{formatCurrency(sprint.totals.total_cost_usd)}</span>
              </span>
            </div>
          </button>
        ))}
      </div>
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

export function EventList({ events, filterKey, taskIndex }) {
  const filteredEvents = events.filter((event) => eventMatchesFilter(event, filterKey));
  return (
    <div className="activity-stream" aria-live="polite">
      {filteredEvents.length === 0 ? (
        <div className="empty-panel">No matching activity yet.</div>
      ) : (
        filteredEvents.map((event) => {
          const category = getEventCategory(event.event_type);
          const taskTitle = taskIndex.get(event.task_id)?.title;
          return (
            <div key={event.id} className="event-row">
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
          );
        })
      )}
    </div>
  );
}

export function TaskDetailDrawer({
  task,
  denyNote,
  onClose,
  onApprove,
  onDenyNoteChange,
  onDeny,
}) {
  if (!task) {
    return null;
  }

  return (
    <aside className="detail-overlay" id="detail-panel" aria-label="Task detail">
      <div className="detail-header">
        <div>
          <div className="detail-kicker">{formatTaskStatus(task.status)}</div>
          <h2 className="detail-title">{task.title}</h2>
        </div>
        <button className="detail-close" type="button" onClick={onClose} aria-label="Close task detail">
          ×
        </button>
      </div>
      <div className="detail-section">
        <div className="detail-grid">
          <div>
            <div className="detail-label">Type</div>
            <div className="detail-value">{task.task_type}</div>
          </div>
          <div>
            <div className="detail-label">Role</div>
            <div className="detail-value">{task.assigned_role || "Unassigned"}</div>
          </div>
          <div>
            <div className="detail-label">Branch</div>
            <div className="detail-value">{task.branch_name || "None"}</div>
          </div>
          <div>
            <div className="detail-label">Step visits</div>
            <div className="detail-value">{formatWorkflowCounts(task.step_visit_counts)}</div>
          </div>
          <div>
            <div className="detail-label">Runs</div>
            <div className="detail-value">{formatCount(task.totals.run_count)}</div>
          </div>
          <div>
            <div className="detail-label">Tokens</div>
            <div className="detail-value">{formatTokenCount(task.totals.total_token_count)}</div>
          </div>
        </div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Acceptance Criteria</div>
        <div className="detail-text">
          {task.acceptance_criteria || "No acceptance criteria recorded."}
        </div>
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
          <label className="detail-label" htmlFor="deny-note">
            Denial note
          </label>
          <textarea
            id="deny-note"
            className="detail-textarea"
            value={denyNote}
            onChange={(event) => onDenyNoteChange(event.target.value)}
            placeholder="Explain what needs to change before this task can continue."
          />
        </div>
      ) : null}
      <div className="detail-section detail-section-scroll">
        <div className="detail-section-title">Run History</div>
        <div className="run-list">
          {task.runs.length === 0 ? (
            <div className="empty-panel">No runs recorded for this task yet.</div>
          ) : (
            task.runs.map((run) => (
              <div key={run.id} className="run-card">
                <div className="run-card-header">
                  <div className="run-title">
                    {run.role_id} / {run.workflow_step}
                  </div>
                  <div className={`run-status run-${run.status}`}>{run.status}</div>
                </div>
                <div className="run-meta">
                  <span>{run.agent_backend}</span>
                  <span>{run.model || "default model"}</span>
                  <span>{formatTokenCount(run.token_count)}</span>
                  <span>{formatCurrency(run.cost_usd)}</span>
                  <span>{formatDuration(run.duration_ms)}</span>
                </div>
                {run.outcome_detail ? <div className="detail-text">{run.outcome_detail}</div> : null}
              </div>
            ))
          )}
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
            <div className="settings-section-title">Supervision</div>
            <SettingsToggle
              label="Allow autonomous task selection"
              description="Engine picks the next task instead of waiting for assignment"
              checked={innerSettings.task_selection_mode === "autonomous"}
              onChange={(checked) => handleChange("task_selection_mode", checked ? "autonomous" : "directed")}
            />
          </div>
          <div className="settings-section">
            <div className="settings-section-title">Resource Limits</div>
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

  function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({ title: title.trim(), goal: goal.trim() || undefined });
  }

  return (
    <div className="modal-backdrop visible" onClick={onClose}>
      <div className="modal" style={{ width: "480px" }} onClick={(e) => e.stopPropagation()}>
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

export function NewTaskModal({ onSubmit, onClose }) {
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState("feature");
  const [criteria, setCriteria] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      taskType,
      acceptanceCriteria: criteria.trim() || undefined,
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
              <label className="form-label">Type</label>
              <select className="form-input" value={taskType} onChange={(e) => setTaskType(e.target.value)}>
                <option value="feature">feature</option>
                <option value="fix">fix</option>
                <option value="refactor">refactor</option>
                <option value="docs">docs</option>
                <option value="spike">spike</option>
                <option value="chore">chore</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Acceptance criteria</label>
              <textarea className="form-input" style={{ minHeight: "48px" }} value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="What must be true for this task to be done?" />
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
