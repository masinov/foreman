function normalizeErrorMessage(status, payload) {
  if (payload && typeof payload === "object" && typeof payload.error === "string") {
    return payload.error;
  }
  return `Request failed (${status})`;
}

async function requestJson(fetchImpl, path, options = {}) {
  const response = await fetchImpl(path, {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(response.status, payload));
  }
  return payload;
}

function buildStreamPath(sprintId, afterEventId) {
  const path = `/api/sprints/${encodeURIComponent(sprintId)}/stream`;
  if (!afterEventId) {
    return path;
  }
  const params = new URLSearchParams({ after: afterEventId });
  return `${path}?${params.toString()}`;
}

export function createDashboardServices({
  fetchImpl = globalThis.fetch,
  EventSourceImpl = globalThis.EventSource,
} = {}) {
  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required for the dashboard frontend.");
  }

  return {
    listProjects() {
      return requestJson(fetchImpl, "/api/projects");
    },
    getProject(projectId) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}`);
    },
    listProjectSprints(projectId) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/sprints`);
    },
    getSprint(sprintId) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}`);
    },
    listSprintTasks(sprintId) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}/tasks`);
    },
    listSprintEvents(sprintId, { afterEventId, beforeEventId, limit } = {}) {
      const params = new URLSearchParams();
      if (afterEventId) params.set("after", afterEventId);
      if (beforeEventId) params.set("before", beforeEventId);
      if (typeof limit === "number") params.set("limit", String(limit));
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}/events${suffix}`);
    },
    getTask(taskId) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}`);
    },
    approveTask(taskId) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}/approve`, {
        method: "POST",
      });
    },
    denyTask(taskId, note) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}/deny`, {
        method: "POST",
        body: { note },
      });
    },
    getProjectSettings(projectId) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/settings`);
    },
    updateProjectSettings(projectId, updates) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/settings`, {
        method: "PATCH",
        body: updates,
      });
    },
    createSprint(projectId, { title, goal, initialTasks }) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/sprints`, {
        method: "POST",
        body: { title, goal, initial_tasks: initialTasks || undefined },
      });
    },
    stopTask(taskId) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}/stop`, {
        method: "POST",
      });
    },
    cancelTask(taskId) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: "POST",
      });
    },
    createTask(sprintId, { title, taskType, acceptanceCriteria }) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}/tasks`, {
        method: "POST",
        body: {
          title,
          task_type: taskType || "feature",
          acceptance_criteria: acceptanceCriteria || undefined,
        },
      });
    },
    transitionSprint(sprintId, status) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "PATCH",
        body: { status },
      });
    },
    updateSprint(sprintId, updates) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "PATCH",
        body: updates,
      });
    },
    updateTask(taskId, updates) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: updates,
      });
    },
    stopAgent(projectId) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/agent/stop`, {
        method: "POST",
      });
    },
    startAgent(projectId, { taskId } = {}) {
      return requestJson(fetchImpl, `/api/projects/${encodeURIComponent(projectId)}/agent/start`, {
        method: "POST",
        body: { task_id: taskId || undefined },
      });
    },
    createProject({ name, repoPath, workflowId }) {
      return requestJson(fetchImpl, "/api/projects", {
        method: "POST",
        body: {
          name,
          repo_path: repoPath,
          workflow_id: workflowId || "development",
        },
      });
    },
    deleteTask(taskId) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "DELETE",
      });
    },
    deleteSprint(sprintId) {
      return requestJson(fetchImpl, `/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "DELETE",
      });
    },
    createHumanMessage(taskId, text) {
      return requestJson(fetchImpl, `/api/tasks/${encodeURIComponent(taskId)}/messages`, {
        method: "POST",
        body: { text },
      });
    },
    openSprintStream(
      sprintId,
      { afterEventId } = {},
      { onEvent, onError } = {},
    ) {
      if (typeof EventSourceImpl !== "function") {
        throw new Error("EventSource is not available in this browser.");
      }

      const stream = new EventSourceImpl(buildStreamPath(sprintId, afterEventId));
      stream.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data);
          onEvent?.(payload);
        } catch (error) {
          onError?.(error);
        }
      };
      stream.onerror = () => {
        onError?.(new Error("Sprint activity stream disconnected."));
      };
      return () => {
        stream.close();
      };
    },
  };
}
