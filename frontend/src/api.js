const TOKEN_STORAGE_KEY = "foreman.dashboard.token";

export class UnauthorizedError extends Error {
  constructor(message) {
    super(message);
    this.name = "UnauthorizedError";
    this.status = 401;
  }
}

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

export function getDashboardToken(storage = defaultStorage()) {
  try {
    return storage?.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setDashboardToken(token, storage = defaultStorage()) {
  try {
    if (token) {
      storage?.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      storage?.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // Storage may be unavailable (private mode); the token then lives for the page only.
  }
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function normalizeErrorMessage(status, payload) {
  if (payload && typeof payload === "object" && typeof payload.error === "string") {
    return payload.error;
  }
  return `Request failed (${status})`;
}

async function requestJson(fetchImpl, path, options = {}, tokenProvider = getDashboardToken) {
  const response = await fetchImpl(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(tokenProvider()),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    throw new UnauthorizedError(normalizeErrorMessage(response.status, payload));
  }
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(response.status, payload));
  }
  return payload;
}

export function buildStreamPath(sprintId, afterEventId, token = "") {
  const path = `/api/sprints/${encodeURIComponent(sprintId)}/stream`;
  const params = new URLSearchParams();
  if (afterEventId) params.set("after", afterEventId);
  // EventSource cannot send headers, so the token travels as a query parameter.
  if (token) params.set("token", token);
  return params.size > 0 ? `${path}?${params.toString()}` : path;
}

async function streamNdjson(fetchImpl, path, body, tokenProvider) {
  const response = await fetchImpl(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(tokenProvider()) },
    body: JSON.stringify(body),
  });
  if (response.status === 401) {
    const err = await response.json().catch(() => ({}));
    throw new UnauthorizedError(err.error || "Unauthorized");
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `Request failed: ${response.status}`);
  }
  return response;
}

export function createDashboardServices({
  fetchImpl = globalThis.fetch,
  EventSourceImpl = globalThis.EventSource,
  tokenProvider = getDashboardToken,
} = {}) {
  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required for the dashboard frontend.");
  }
  const request = (path, options) => requestJson(fetchImpl, path, options, tokenProvider);

  return {
    listProjects() {
      return request("/api/projects");
    },
    getProject(projectId) {
      return request(`/api/projects/${encodeURIComponent(projectId)}`);
    },
    listProjectSprints(projectId) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/sprints`);
    },
    getSprint(sprintId) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}`);
    },
    listSprintTasks(sprintId) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}/tasks`);
    },
    listSprintEvents(sprintId, { afterEventId, beforeEventId, limit } = {}) {
      const params = new URLSearchParams();
      if (afterEventId) params.set("after", afterEventId);
      if (beforeEventId) params.set("before", beforeEventId);
      if (typeof limit === "number") params.set("limit", String(limit));
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return request(`/api/sprints/${encodeURIComponent(sprintId)}/events${suffix}`);
    },
    getTask(taskId) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}`);
    },
    approveTask(taskId) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}/approve`, {
        method: "POST",
      });
    },
    denyTask(taskId, note) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}/deny`, {
        method: "POST",
        body: { note },
      });
    },
    getProjectSettings(projectId) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/settings`);
    },
    updateProjectSettings(projectId, updates) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/settings`, {
        method: "PATCH",
        body: updates,
      });
    },
    createSprint(projectId, { title, goal, initialTasks }) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/sprints`, {
        method: "POST",
        body: { title, goal, initial_tasks: initialTasks || undefined },
      });
    },
    stopTask(taskId) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}/stop`, {
        method: "POST",
      });
    },
    cancelTask(taskId) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: "POST",
      });
    },
    createTask(sprintId, { title, taskType, acceptanceCriteria, description, complexity, dependsOn }) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}/tasks`, {
        method: "POST",
        body: {
          title,
          task_type: taskType || "feature",
          acceptance_criteria: acceptanceCriteria || undefined,
          description: description || undefined,
          complexity: complexity || undefined,
          depends_on: dependsOn && dependsOn.length > 0 ? dependsOn : undefined,
        },
      });
    },
    transitionSprint(sprintId, status) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "PATCH",
        body: { status },
      });
    },
    updateSprint(sprintId, updates) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "PATCH",
        body: updates,
      });
    },
    updateTask(taskId, updates) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: updates,
      });
    },
    stopAgent(projectId) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/agent/stop`, {
        method: "POST",
      });
    },
    async *metaMessage(projectId, message) {
      const response = await streamNdjson(
        fetchImpl,
        `/api/projects/${encodeURIComponent(projectId)}/meta/message`,
        { message },
        tokenProvider,
      );
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (line.trim()) {
            try { yield JSON.parse(line); } catch {}
          }
        }
      }
    },
    metaHistory(projectId, { limit, before } = {}) {
      const params = new URLSearchParams();
      if (typeof limit === "number") params.set("limit", String(limit));
      if (before) params.set("before", before);
      const suffix = params.size > 0 ? `?${params.toString()}` : "";
      return request(`/api/projects/${encodeURIComponent(projectId)}/meta/history${suffix}`);
    },
    async *superviseMeta(projectId, eventId) {
      const response = await streamNdjson(
        fetchImpl,
        `/api/projects/${encodeURIComponent(projectId)}/meta/supervise`,
        { event_id: eventId },
        tokenProvider,
      );
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (line.trim()) {
            try { yield JSON.parse(line); } catch {}
          }
        }
      }
    },
    listRoles() {
      return request("/api/roles");
    },
    updateRole(roleId, updates) {
      return request(`/api/roles/${encodeURIComponent(roleId)}`, {
        method: "PATCH",
        body: updates,
      });
    },
    clearMetaSession(projectId) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/meta/session`, {
        method: "DELETE",
      });
    },
    listGates(projectId, { status } = {}) {
      const params = status ? `?status=${encodeURIComponent(status)}` : "";
      return request(`/api/projects/${encodeURIComponent(projectId)}/gates${params}`);
    },
    resolveGate(gateId, { resolution, resolvedBy = "human" } = {}) {
      return request(`/api/gates/${encodeURIComponent(gateId)}`, {
        method: "PATCH",
        body: { resolution, resolved_by: resolvedBy },
      });
    },
    startAgent(projectId, { taskId } = {}) {
      return request(`/api/projects/${encodeURIComponent(projectId)}/agent/start`, {
        method: "POST",
        body: { task_id: taskId || undefined },
      });
    },
    createProject({ name, repoPath, workflowId }) {
      return request("/api/projects", {
        method: "POST",
        body: {
          name,
          repo_path: repoPath,
          workflow_id: workflowId || "development",
        },
      });
    },
    deleteTask(taskId) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "DELETE",
      });
    },
    deleteSprint(sprintId) {
      return request(`/api/sprints/${encodeURIComponent(sprintId)}`, {
        method: "DELETE",
      });
    },
    createHumanMessage(taskId, text) {
      return request(`/api/tasks/${encodeURIComponent(taskId)}/messages`, {
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

      const stream = new EventSourceImpl(buildStreamPath(sprintId, afterEventId, tokenProvider()));
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
