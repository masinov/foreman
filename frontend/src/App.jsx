import { startTransition, useEffect, useRef, useState } from "react";

import {
  EmptyPanel,
  ErrorBanner,
  EventList,
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

  const refreshTimerRef = useRef(null);
  const routeRef = useRef(route);
  const selectedTaskIdRef = useRef(selectedTaskId);
  const lastStreamEventIdRef = useRef(null);

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
    const [projectPayload, sprintPayload] = await Promise.all([
      services.getProject(projectId),
      services.listProjectSprints(projectId),
    ]);
    setCurrentProject(projectPayload);
    setCurrentSprints(sprintPayload.sprints);
    return {
      project: projectPayload,
      sprints: sprintPayload.sprints,
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
    setStreamSeedEventId(lastEventId);
    lastStreamEventIdRef.current = lastEventId;
    setSelectedTaskId((currentValue) => {
      if (currentValue && nextTasks.some((task) => task.id === currentValue)) {
        return currentValue;
      }
      return pickDefaultTaskId(nextTasks);
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
    setErrorMessage("");

    if (refreshTimerRef.current) {
      browser.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    refreshSprintScope(route.sprintId)
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

  async function handleCreateSprint({ title, goal }) {
    if (!route.projectId) return;
    setErrorMessage("");
    try {
      await services.createSprint(route.projectId, { title, goal });
      setNewSprintOpen(false);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
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

  async function handleTransitionSprint(sprintId, status) {
    setErrorMessage("");
    try {
      await services.transitionSprint(sprintId, status);
      await refreshAllVisibleState({ keepSelectedTask: false });
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  const taskIndex = new Map(tasks.map((task) => [task.id, task]));
  const topbarProject = currentProject
    ? {
        ...currentProject,
        sprints: currentSprints,
      }
    : null;

  const topbarSprintTotals = currentSprint?.totals || currentSprints.find((s) => s.status === "active")?.totals || null;
  const topbarProjectTotals = projects.find((p) => p.id === route.projectId)?.totals || null;

  return (
    <div className="app-shell">
      <Topbar
        projects={projects}
        currentProject={topbarProject}
        currentSprint={currentSprint}
        sprintTotals={topbarSprintTotals}
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
        />
      ) : null}
      {!isBootstrapping && route.view === "project" ? (
        currentProject ? (
          <SprintList
            project={currentProject}
            sprints={currentSprints}
            onSelectSprint={(sprintId) => navigateTo(buildSprintPath(route.projectId, sprintId))}
            onOpenNewSprint={() => setNewSprintOpen(true)}
            onTransitionSprint={handleTransitionSprint}
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
                    {currentSprint.title}
                    <span className={`sprint-status-badge ss-${currentSprint.status}`}>{currentSprint.status}</span>
                  </div>
                  <div className="sprint-goal-text">{currentSprint.goal || "No sprint goal recorded."}</div>
                </div>
                <div className="sprint-header-right">
                  <div className="progress-bar" style={{ width: "80px" }} aria-hidden="true">
                    <span className="p-done" style={{ flex: currentSprint.task_counts?.done || 0 }} />
                    <span className="p-wip" style={{ flex: currentSprint.task_counts?.in_progress || 0 }} />
                    <span className="p-blocked" style={{ flex: currentSprint.task_counts?.blocked || 0 }} />
                    <span className="p-todo" style={{ flex: currentSprint.task_counts?.todo || 0 }} />
                  </div>
                  <span className="sprint-stat">
                    <span className="sv">{formatCount(currentSprint.task_counts?.done || 0)}</span>/{formatCount((currentSprint.task_counts?.done || 0) + (currentSprint.task_counts?.in_progress || 0) + (currentSprint.task_counts?.blocked || 0) + (currentSprint.task_counts?.todo || 0))} done
                  </span>
                  <span className="sprint-stat">
                    <span className="sv">{formatCompactCount(currentSprint.totals.total_token_count)}</span> tokens
                  </span>
                  <span className="sprint-stat">
                    <span className="sv">{formatCount(currentSprint.totals.run_count)}</span> runs
                  </span>
                  <button className="btn-action" type="button" onClick={() => setNewTaskOpen(true)}>
                    <span className="plus">+</span> New task
                  </button>
                  {currentSprint.status === "planned" ? (
                    <button
                      className="btn-action"
                      type="button"
                      disabled={isActionPending}
                      onClick={() => handleTransitionSprint(currentSprint.id, "active")}
                    >
                      Start sprint
                    </button>
                  ) : null}
                  {currentSprint.status === "active" ? (
                    <button
                      className="btn-secondary"
                      type="button"
                      disabled={isActionPending}
                      onClick={() => handleTransitionSprint(currentSprint.id, "completed")}
                    >
                      Complete sprint
                    </button>
                  ) : null}
                  <button
                    className="btn-stop"
                    type="button"
                    title="Stop agent"
                    aria-label="Stop agent"
                    disabled={isActionPending}
                    onClick={handleStopAgent}
                  >
                    <svg viewBox="0 0 16 16" width="12" height="12"><rect x="3" y="3" width="10" height="10" rx="1"/></svg>
                    Stop agent
                  </button>
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
                                />
                              ))
                            )}
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
                  <EventList events={events} filterKey={activityFilter} taskIndex={taskIndex} />
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
                  denyNote={denyNote}
                  onClose={() => setSelectedTaskId(null)}
                  onApprove={handleApproveTask}
                  onDenyNoteChange={setDenyNote}
                  onDeny={handleDenyTask}
                />
              </div>
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
