import { startTransition, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  EmptyPanel,
  ErrorBanner,
  EventList,
  NewProjectModal,
  NewSprintModal,
  NewTaskModal,
  ProjectOverview,
  SettingsPanel,
  SprintList,
  STATUS_COLUMNS,
  TaskCard,
  TaskDetailDrawer,
  Topbar,
} from "./components";
import { formatCompactCount, formatCount } from "./format";
import { buildDashboardPath, buildProjectPath, buildSprintPath, parseRoute } from "./routing";

const INITIAL_EVENTS_LIMIT = 50;
const STREAM_REFRESH_DELAY_MS = 250;

function pickDefaultTaskId(tasks) {
  if (tasks.length === 0) {
    return null;
  }
  const preferred = ["in_progress", "blocked", "todo", "done"];
  for (const status of preferred) {
    const task = tasks.find((item) => item.status === status);
    if (task) {
      return task.id;
    }
  }
  return tasks[0].id;
}

function appendEvent(existingEvents, nextEvent) {
  if (existingEvents.some((event) => event.id === nextEvent.id)) {
    return existingEvents;
  }
  const nextEvents = [...existingEvents, nextEvent];
  return nextEvents.slice(-200);
}

export default function App({ services, browser }) {
  const [route, setRoute] = useState(() => parseRoute(browser.location.pathname));
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [currentSprints, setCurrentSprints] = useState([]);
  const [currentSprint, setCurrentSprint] = useState(null);
  const [pendingGates, setPendingGates] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [taskDetail, setTaskDetail] = useState(null);
  const [activityFilter, setActivityFilter] = useState("all");
  const [activityCollapsed, setActivityCollapsed] = useState(false);
  const [messageText, setMessageText] = useState("");
  const [denyNote, setDenyNote] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isActionPending, setIsActionPending] = useState(false);
  const [streamSeedEventId, setStreamSeedEventId] = useState(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projectSettings, setProjectSettings] = useState(null);
  const [newSprintOpen, setNewSprintOpen] = useState(false);
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [hasMoreEvents, setHasMoreEvents] = useState(false);
  const [isLoadingMoreEvents, setIsLoadingMoreEvents] = useState(false);
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalDraft, setGoalDraft] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");

  const refreshTimerRef = useRef(null);
  const routeRef = useRef(route);
  const selectedTaskIdRef = useRef(selectedTaskId);
  const lastStreamEventIdRef = useRef(null);
  const activityListRef = useRef(null);
  const atActivityBottomRef = useRef(true);

  useEffect(() => {
    routeRef.current = route;
  }, [route]);

  useEffect(() => {
    selectedTaskIdRef.current = selectedTaskId;
  }, [selectedTaskId]);

  useEffect(() => {
    function handlePopState() {
      startTransition(() => {
        setRoute(parseRoute(browser.location.pathname));
      });
    }

    browser.addEventListener("popstate", handlePopState);
    return () => {
      browser.removeEventListener("popstate", handlePopState);
    };
  }, [browser]);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) {
        browser.clearTimeout(refreshTimerRef.current);
      }
    };
  }, [browser]);

  async function refreshProjects() {
    const payload = await services.listProjects();
    setProjects(payload.projects);
    return payload.projects;
  }

  async function refreshProjectScope(projectId) {
    if (!projectId) {
      setCurrentProject(null);
      setCurrentSprints([]);
      return null;
    }
    const [projectPayload, sprintPayload, gatesPayload] = await Promise.all([
      services.getProject(projectId),
      services.listProjectSprints(projectId),
      services.listGates(projectId, { status: "pending" }).catch(() => ({ gates: [] })),
    ]);
    setCurrentProject(projectPayload);
    setCurrentSprints(sprintPayload.sprints);
    setPendingGates(gatesPayload.gates || []);
    return {
      project: projectPayload,
      sprints: sprintPayload.sprints,
      gates: gatesPayload.gates || [],
    };
  }

  async function refreshSprintScope(sprintId) {
    if (!sprintId) {
      setCurrentSprint(null);
      setTasks([]);
      setEvents([]);
      setSelectedTaskId(null);
      setStreamSeedEventId(undefined);
      lastStreamEventIdRef.current = null;
      return null;
    }

    const [sprintPayload, taskPayload, eventPayload] = await Promise.all([
      services.getSprint(sprintId),
      services.listSprintTasks(sprintId),
      services.listSprintEvents(sprintId, { limit: INITIAL_EVENTS_LIMIT }),
    ]);

    const nextTasks = taskPayload.tasks;
    const nextEvents = eventPayload.events;
    const lastEventId = nextEvents.length > 0 ? nextEvents[nextEvents.length - 1].id : null;

    setCurrentSprint(sprintPayload);
    setTasks(nextTasks);
    setEvents(nextEvents);
    setHasMoreEvents(eventPayload.has_more ?? false);
    setStreamSeedEventId(lastEventId);
    lastStreamEventIdRef.current = lastEventId;
    setSelectedTaskId((currentValue) => {
      if (currentValue && nextTasks.some((task) => task.id === currentValue)) {
        return currentValue;
      }
      return null;
    });
    return {
      sprint: sprintPayload,
      tasks: nextTasks,
      events: nextEvents,
    };
  }
  async function refreshTaskDetail(taskId) {
    if (!taskId) {
      setTaskDetail(null);
      return null;
    }
    const payload = await services.getTask(taskId);
    setTaskDetail(payload);
    return payload;
  }

  useEffect(() => {
    let cancelled = false;
    setIsBootstrapping(true);
    setErrorMessage("");

    refreshProjects()
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsBootstrapping(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [services]);

  useEffect(() => {
    let cancelled = false;
    setErrorMessage("");

    refreshProjectScope(route.projectId)
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [route.projectId]);

  useEffect(() => {
    let cancelled = false;

    if (refreshTimerRef.current) {
      browser.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    refreshSprintScope(route.sprintId)
      .then(() => {
        if (!cancelled) {
          setErrorMessage("");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [browser, route.sprintId]);

  useEffect(() => {
    let cancelled = false;
    setDenyNote("");

    refreshTaskDetail(selectedTaskId)
      .catch((error) => {
        if (!cancelled) {
          setTaskDetail(null);
          setErrorMessage(error.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedTaskId]);

  useEffect(() => {
    if (!route.sprintId || streamSeedEventId === undefined) {
      return undefined;
    }

    const closeStream = services.openSprintStream(
      route.sprintId,
      { afterEventId: streamSeedEventId },
      {
        onEvent: (payload) => {
          if (!payload || payload.type !== "event" || !payload.event) {
            return;
          }

          setEvents((currentEvents) => appendEvent(currentEvents, payload.event));
          lastStreamEventIdRef.current = payload.event.id;

          if (refreshTimerRef.current) {
            browser.clearTimeout(refreshTimerRef.current);
          }
          refreshTimerRef.current = browser.setTimeout(async () => {
            const activeRoute = routeRef.current;
            try {
              await refreshProjects();
              await refreshSprintScope(activeRoute.sprintId);
              if (selectedTaskIdRef.current) {
                await refreshTaskDetail(selectedTaskIdRef.current);
              }
            } catch (error) {
              setErrorMessage(error.message);
            }
          }, STREAM_REFRESH_DELAY_MS);
        },
        onError: (error) => {
          setErrorMessage(error.message);
        },
      },
    );

    return () => {
      closeStream();
    };
  }, [browser, route.sprintId, services, streamSeedEventId]);

  function navigateTo(pathname) {
    if (browser.location.pathname !== pathname) {
      browser.history.pushState({}, "", pathname);
    }
    startTransition(() => {
      setRoute(parseRoute(pathname));
    });
  }

  async function refreshAllVisibleState({ keepSelectedTask = true } = {}) {
    try {
      await refreshProjects();
      await refreshProjectScope(routeRef.current.projectId);
      await refreshSprintScope(routeRef.current.sprintId);
      if (keepSelectedTask && selectedTaskIdRef.current) {
        await refreshTaskDetail(selectedTaskIdRef.current);
      }
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleApproveTask(taskId) {
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.approveTask(taskId);
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleDenyTask(taskId) {
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.denyTask(taskId, denyNote);
      setDenyNote("");
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleSendHumanMessage() {
    if (!selectedTaskId || !messageText.trim()) {
      return;
    }

    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.createHumanMessage(selectedTaskId, messageText.trim());
      setMessageText("");
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleOpenSettings() {
    if (!route.projectId) return;
    setErrorMessage("");
    try {
      const payload = await services.getProjectSettings(route.projectId);
      setProjectSettings(payload);
      setSettingsOpen(true);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleUpdateSettings(updates) {
    if (!route.projectId) return;
    setErrorMessage("");
    try {
      const payload = await services.updateProjectSettings(route.projectId, updates);
      setProjectSettings(payload);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleCreateSprint({ title, goal, initialTasks }) {
    if (!route.projectId) return;
    setErrorMessage("");
    try {
      await services.createSprint(route.projectId, { title, goal, initialTasks });
      setNewSprintOpen(false);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleLoadMoreEvents() {
    if (!route.sprintId || events.length === 0) return;
    setIsLoadingMoreEvents(true);
    try {
      const oldestEventId = events[0].id;
      const payload = await services.listSprintEvents(route.sprintId, {
        beforeEventId: oldestEventId,
        limit: INITIAL_EVENTS_LIMIT,
      });
      if (payload.events.length > 0) {
        setEvents((prev) => [...payload.events, ...prev]);
        setHasMoreEvents(payload.has_more ?? false);
      } else {
        setHasMoreEvents(false);
      }
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsLoadingMoreEvents(false);
    }
  }

  async function handleStopTask(taskId) {
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.stopTask(taskId);
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleCancelTask(taskId) {
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.cancelTask(taskId);
      setSelectedTaskId(null);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleCreateTask({ title, taskType, acceptanceCriteria }) {
    if (!route.sprintId) return;
    setErrorMessage("");
    try {
      await services.createTask(route.sprintId, { title, taskType, acceptanceCriteria });
      setNewTaskOpen(false);
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleStopAgent() {
    if (!route.projectId) return;
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.stopAgent(route.projectId);
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleStartAgent() {
    if (!route.projectId) return;
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.startAgent(route.projectId);
      await refreshAllVisibleState();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleResolveGate(gateId, resolution) {
    setErrorMessage("");
    try {
      await services.resolveGate(gateId, { resolution });
      await refreshProjectScope(routeRef.current.projectId);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleCreateProject({ name, repoPath, workflowId }) {
    setErrorMessage("");
    try {
      const payload = await services.createProject({ name, repoPath, workflowId });
      setNewProjectOpen(false);
      await refreshProjects();
      navigateTo(buildProjectPath(payload.id));
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleTransitionSprint(sprintId, status) {
    setErrorMessage("");
    try {
      await services.transitionSprint(sprintId, status);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleSaveTask(taskId, updates) {
    setErrorMessage("");
    try {
      await services.updateTask(taskId, updates);
      await refreshTaskDetail(taskId);
      await refreshSprintScope(routeRef.current.sprintId);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleUpdateSprintGoal(sprintId, goal) {
    setErrorMessage("");
    try {
      await services.updateSprint(sprintId, { goal });
      setEditingGoal(false);
      const sprintPayload = await services.getSprint(sprintId);
      setCurrentSprint(sprintPayload);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleUpdateSprintTitle(sprintId, title) {
    if (!title.trim()) return;
    setErrorMessage("");
    try {
      await services.updateSprint(sprintId, { title: title.trim() });
      setEditingTitle(false);
      const sprintPayload = await services.getSprint(sprintId);
      setCurrentSprint(sprintPayload);
      await refreshProjectScope(routeRef.current.projectId);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function handleDeleteTask(taskId) {
    if (!window.confirm("Delete this task? All run history will be removed. This cannot be undone.")) return;
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.deleteTask(taskId);
      setSelectedTaskId(null);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleDeleteSprint(sprintId) {
    if (!window.confirm("Delete this sprint and all its tasks? This cannot be undone.")) return;
    setIsActionPending(true);
    setErrorMessage("");
    try {
      await services.deleteSprint(sprintId);
      setCurrentSprint(null);
      if (routeRef.current.sprintId === sprintId) {
        navigateTo(buildProjectPath(routeRef.current.projectId));
        await refreshProjectScope(routeRef.current.projectId);
      } else {
        await refreshAllVisibleState({ keepSelectedTask: false });
      }
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleReorderSprints(orderedIds) {
    const sprintMap = new Map(currentSprints.map((s) => [s.id, s]));
    const updates = orderedIds
      .map((id, i) => ({ id, order_index: i, prev: sprintMap.get(id)?.order_index ?? 0 }))
      .filter(({ order_index, prev }) => order_index !== prev);

    if (updates.length === 0) return;

    setErrorMessage("");
    try {
      await Promise.all(updates.map(({ id, order_index }) =>
        services.updateSprint(id, { order_index }),
      ));
      await refreshProjectScope(routeRef.current.projectId);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  // Auto-scroll activity panel to bottom when new events arrive (if already at bottom)
  useLayoutEffect(() => {
    const el = activityListRef.current;
    if (!el) return;
    if (atActivityBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events]);

  const taskIndex = new Map(tasks.map((task) => [task.id, task]));
  const topbarProject = currentProject
    ? {
        ...currentProject,
        sprints: currentSprints,
      }
    : null;

  const topbarProjectTotals = currentProject?.totals || projects.find((p) => p.id === route.projectId)?.totals || null;

  return (
    <div className="app-shell">
      <Topbar
        projects={projects}
        currentProject={topbarProject}
        currentSprint={currentSprint}
        projectTotals={topbarProjectTotals}
        projectStatus={projects.find((project) => project.id === route.projectId)?.status}
        onOpenDashboard={() => navigateTo(buildDashboardPath())}
        onSelectProject={(projectId) => navigateTo(buildProjectPath(projectId))}
        onSelectSprint={(sprintId) => navigateTo(buildSprintPath(route.projectId, sprintId))}
        onToggleSettings={route.projectId ? handleOpenSettings : undefined}
      />
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage("")} />
      {isBootstrapping ? (
        <EmptyPanel title="Loading dashboard" message="Reading projects and sprint state from SQLite." />
      ) : null}
      {!isBootstrapping && route.view === "dashboard" ? (
        <ProjectOverview
          projects={projects}
          onSelectProject={(projectId) => navigateTo(buildProjectPath(projectId))}
          onNewProject={() => setNewProjectOpen(true)}
        />
      ) : null}
      {!isBootstrapping && route.view === "project" ? (
        currentProject ? (
          <SprintList
            project={currentProject}
            sprints={currentSprints}
            pendingGates={pendingGates}
            onSelectSprint={async (sprintId) => { await refreshSprintScope(sprintId); navigateTo(buildSprintPath(route.projectId, sprintId)); }}
            onOpenNewSprint={() => setNewSprintOpen(true)}
            onTransitionSprint={handleTransitionSprint}
            onDeleteSprint={handleDeleteSprint}
            onReorderSprints={handleReorderSprints}
            onStartAgent={handleStartAgent}
            onStopAgent={handleStopAgent}
            onResolveGate={handleResolveGate}
            onSprintsChanged={() => refreshProjectScope(route.projectId)}
            services={services}
            isActionPending={isActionPending}
            autonomyLevel={currentProject.autonomy_level || "supervised"}
          />
        ) : (
          <EmptyPanel title="Project not found" message="The requested project could not be loaded." />
        )
      ) : null}
      {!isBootstrapping && route.view === "sprint" ? (
        currentProject && currentSprint ? (
          <section className="sprint-view view visible">
            <div className="sprint-view-inner">
              <header className="sprint-header">
                <div className="sprint-header-left">
                  <div className="sprint-name">
                    {editingTitle ? (
                      <div className="sprint-title-edit">
                        <input
                          className="sprint-title-input"
                          value={titleDraft}
                          onChange={(e) => setTitleDraft(e.target.value)}
                          aria-label="Sprint title"
                          autoFocus
                        />
                        <button
                          className="btn-save-goal"
                          type="button"
                          onClick={() => handleUpdateSprintTitle(currentSprint.id, titleDraft)}
                          disabled={!titleDraft.trim()}
                        >
                          Save
                        </button>
                        <button
                          className="btn-cancel-goal"
                          type="button"
                          onClick={() => setEditingTitle(false)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <span className="sprint-title-text" title={currentSprint.title} onDoubleClick={() => { setTitleDraft(currentSprint.title); setEditingTitle(true); }}>{currentSprint.title}</span>
                        <span className={`sprint-status-badge ss-${currentSprint.status}`}>{currentSprint.status}</span>
                      </>
                    )}
                  </div>
                  {editingGoal ? (
                    <div className="sprint-goal-edit">
                      <input
                        className="sprint-goal-input"
                        value={goalDraft}
                        onChange={(e) => setGoalDraft(e.target.value)}
                        aria-label="Sprint goal"
                        autoFocus
                      />
                      <button
                        className="btn-save-goal"
                        type="button"
                        onClick={() => handleUpdateSprintGoal(currentSprint.id, goalDraft)}
                      >
                        Save
                      </button>
                      <button
                        className="btn-cancel-goal"
                        type="button"
                        onClick={() => setEditingGoal(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="sprint-goal-text" onDoubleClick={() => { setGoalDraft(currentSprint.goal || ""); setEditingGoal(true); }} title={currentSprint.goal || undefined}>
                      {currentSprint.goal || "No sprint goal recorded."}
                    </div>
                  )}
                </div>
                <div className="sprint-header-right">
                  {currentSprint.status === "planned" ? (
                    <>
                      <button
                        className="btn-action"
                        type="button"
                        disabled={isActionPending}
                        onClick={() => handleTransitionSprint(currentSprint.id, "active")}
                      >
                        Start
                      </button>
                      <button
                        className="btn-danger-sm"
                        type="button"
                        disabled={isActionPending}
                        onClick={() => handleTransitionSprint(currentSprint.id, "cancelled")}
                        title="Cancel sprint"
                      >
                        Cancel
                      </button>
                      <button
                        className="btn-danger-sm"
                        type="button"
                        disabled={isActionPending}
                        onClick={() => handleDeleteSprint(currentSprint.id)}
                        title="Delete sprint"
                      >
                        Delete
                      </button>
                    </>
                  ) : null}
                  {currentSprint.status === "active" ? (
                    <>
                      <button
                        className="btn-stop"
                        type="button"
                        disabled={isActionPending || currentProject?.status !== "running"}
                        title="Stop agent"
                        aria-label="Stop agent"
                        onClick={handleStopAgent}
                      >
                        <svg viewBox="0 0 16 16" width="12" height="12"><rect x="3" y="3" width="10" height="10" rx="1"/></svg>
                        Stop
                      </button>
                      <button
                        className="btn-secondary"
                        type="button"
                        disabled={isActionPending}
                        onClick={() => handleTransitionSprint(currentSprint.id, "completed")}
                        title="Complete sprint"
                      >
                        Complete
                      </button>
                      <button
                        className="btn-danger-sm"
                        type="button"
                        disabled={isActionPending}
                        onClick={() => handleTransitionSprint(currentSprint.id, "cancelled")}
                        title="Cancel sprint"
                      >
                        Cancel
                      </button>
                    </>
                  ) : null}
                  {currentSprint.status === "done" || currentSprint.status === "cancelled" ? (
                    <button
                      className="btn-danger-sm"
                      type="button"
                      disabled={isActionPending}
                      onClick={() => handleDeleteSprint(currentSprint.id)}
                      title="Delete sprint"
                    >
                      Delete
                    </button>
                  ) : null}
                </div>
              </header>
              <div className={`sprint-body ${activityCollapsed ? "activity-hidden" : "with-activity"}`}>
                <div className="board">
                  <div className="board-columns">
                    {STATUS_COLUMNS.map((column) => {
                      const columnTasks = tasks.filter((task) => task.status === column.key);
                      return (
                        <div key={column.key} className="column">
                          <div className="col-header">
                            <div className="col-title">{column.label}</div>
                            <div className="col-count">{formatCount(columnTasks.length)}</div>
                          </div>
                          <div className="col-cards">
                            {columnTasks.length === 0 ? (
                              <div className="empty-panel compact-empty">No tasks.</div>
                            ) : (
                              columnTasks.map((task) => (
                                <TaskCard
                                  key={task.id}
                                  task={task}
                                  selected={task.id === selectedTaskId}
                                  onSelect={setSelectedTaskId}
                                  onApprove={handleApproveTask}
                                  onDeny={handleDenyTask}
                                  onStop={handleStopTask}
                                />
                              ))
                            )}
                            {column.key === "todo" ? (
                              <button
                                className="btn-new-task-col"
                                type="button"
                                onClick={() => setNewTaskOpen(true)}
                              >
                                + New task
                              </button>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <aside className="activity">
                  <div className="activity-header">
                    <div className="activity-header-left">
                      <span className="activity-title">Activity</span>
                      <button className="activity-collapse" type="button" onClick={() => setActivityCollapsed(true)}>
                        »
                      </button>
                    </div>
                    <label>
                      <span className="visually-hidden">Filter activity</span>
                      <select
                        className="activity-filter"
                        value={activityFilter}
                        onChange={(event) => setActivityFilter(event.target.value)}
                      >
                        <option value="all">All events</option>
                        <option value="message">Agent messages</option>
                        <option value="file">File changes</option>
                        <option value="workflow">Workflow</option>
                        <option value="human">Human</option>
                        <option value="review">Review</option>
                      </select>
                    </label>
                  </div>
                  {hasMoreEvents ? (
                    <button
                      className="load-more-btn"
                      type="button"
                      disabled={isLoadingMoreEvents}
                      onClick={handleLoadMoreEvents}
                    >
                      {isLoadingMoreEvents ? "Loading…" : "Load older events"}
                    </button>
                  ) : null}
                  <EventList
                    events={events}
                    filterKey={activityFilter}
                    taskIndex={taskIndex}
                    containerRef={activityListRef}
                    onScroll={(e) => {
                      const el = e.currentTarget;
                      atActivityBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
                    }}
                  />
                  <div className={`activity-input ${selectedTaskId ? "" : "disabled"}`}>
                    <label className="visually-hidden" htmlFor="human-message">
                      Human guidance
                    </label>
                    <textarea
                      id="human-message"
                      value={messageText}
                      onChange={(event) => setMessageText(event.target.value)}
                      placeholder={selectedTaskId ? "Send guidance to the selected task." : "Select a task to send guidance."}
                      disabled={!selectedTaskId || isActionPending}
                    />
                    <button type="button" onClick={handleSendHumanMessage} disabled={!selectedTaskId || isActionPending}>
                      Send
                    </button>
                  </div>
                </aside>
                {activityCollapsed ? (
                  <button className="activity-tab" type="button" onClick={() => setActivityCollapsed(false)}>
                    Activity
                  </button>
                ) : null}
                <TaskDetailDrawer
                  task={taskDetail}
                  taskIndex={taskIndex}
                  denyNote={denyNote}
                  onClose={() => setSelectedTaskId(null)}
                  onApprove={handleApproveTask}
                  onDenyNoteChange={setDenyNote}
                  onDeny={handleDenyTask}
                  onStop={handleStopTask}
                  onCancel={handleCancelTask}
                  onSave={handleSaveTask}
                  onDelete={handleDeleteTask}
                />
              </div>
              <footer className="sprint-statusbar">
                <span className="sprint-stat">
                  <span className="sv">{formatCompactCount(currentSprint.totals.total_token_count)}</span> tokens
                </span>
                <span className="sprint-stat">
                  <span className="sv">{formatCount(currentSprint.totals.run_count)}</span> runs
                </span>
                <span className="sprint-stat">
                  <span className="sv">{formatCount(currentSprint.task_counts?.done || 0)}</span>/{formatCount((currentSprint.task_counts?.done || 0) + (currentSprint.task_counts?.in_progress || 0) + (currentSprint.task_counts?.blocked || 0) + (currentSprint.task_counts?.todo || 0))} tasks
                </span>
                <span className="sprint-statusbar-sep" aria-hidden="true">·</span>
                <span className="sprint-stat">
                  <span className={`sprint-status-badge ss-${currentSprint.status}`}>{currentSprint.status}</span>
                </span>
              </footer>
            </div>
          </section>
        ) : (
          <EmptyPanel title="Sprint not found" message="The requested sprint could not be loaded." />
        )
      ) : null}
      {settingsOpen ? (
        <SettingsPanel
          settings={projectSettings}
          onUpdate={handleUpdateSettings}
          onClose={() => setSettingsOpen(false)}
        />
      ) : null}
      {newProjectOpen ? (
        <NewProjectModal
          onSubmit={handleCreateProject}
          onClose={() => setNewProjectOpen(false)}
        />
      ) : null}
      {newSprintOpen ? (
        <NewSprintModal
          onSubmit={handleCreateSprint}
          onClose={() => setNewSprintOpen(false)}
        />
      ) : null}
      {newTaskOpen ? (
        <NewTaskModal
          onSubmit={handleCreateTask}
          onClose={() => setNewTaskOpen(false)}
        />
      ) : null}
    </div>
  );
}
