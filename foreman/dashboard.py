"""Dashboard web server for Foreman."""

from __future__ import annotations

import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .store import ForemanStore


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Foreman Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600&display=swap');

  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#0c0c0e;--bg-raised:#141417;--bg-card:#1a1a1f;--bg-card-hover:#1f1f25;
    --bg-input:#111114;--border:#2a2a30;--border-subtle:#1f1f25;
    --text-primary:#e8e6e3;--text-secondary:#8a8a8e;--text-tertiary:#5a5a5e;
    --accent:#c9a55a;--accent-dim:#c9a55a22;
    --green:#4a9;--green-dim:#4a922;--red:#c55;--red-dim:#c5522;
    --amber:#c90;--amber-dim:#c9022;--blue:#59b;--blue-dim:#59b22;
    --font-mono:'JetBrains Mono',monospace;--font-serif:'Source Serif 4',serif;
    --radius:3px;--transition:180ms ease;
  }
  html{font-size:14px}
  body{font-family:var(--font-mono);background:var(--bg);color:var(--text-primary);
    line-height:1.5;min-height:100vh;-webkit-font-smoothing:antialiased}

  /* Topbar */
  .topbar{display:flex;align-items:center;justify-content:space-between;
    padding:0 24px;height:48px;border-bottom:1px solid var(--border);
    background:var(--bg);position:sticky;top:0;z-index:100}
  .topbar-left{display:flex;align-items:center;gap:0}
  .logo{font-weight:700;font-size:13px;letter-spacing:.12em;text-transform:uppercase;
    cursor:pointer;transition:var(--transition);padding-right:4px}
  .logo:hover{color:var(--accent)}
  .topbar-right{display:flex;align-items:center;gap:14px}
  .topbar-tokens{font-size:11px;color:var(--text-tertiary);letter-spacing:.04em;font-variant-numeric:tabular-nums}
  .topbar-tokens span{color:var(--text-secondary)}
  .engine-status{display:flex;align-items:center;gap:6px;font-size:10px;
    letter-spacing:.04em;text-transform:uppercase}
  .engine-status .dot{width:6px;height:6px;border-radius:50%}
  .engine-status.running .dot{background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2.5s ease-in-out infinite}
  .engine-status.running{color:var(--green)}
  .engine-status.idle .dot{background:var(--text-tertiary)}
  .engine-status.idle{color:var(--text-tertiary)}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

  /* Breadcrumb */
  .breadcrumb{display:flex;align-items:center;gap:0;font-size:12px}
  .breadcrumb-sep{color:var(--text-tertiary);padding:0 6px;font-size:11px;user-select:none}
  .breadcrumb-link{color:var(--text-secondary);cursor:pointer;padding:4px 8px;
    border-radius:var(--radius);transition:var(--transition);text-decoration:none;
    font-family:var(--font-mono);font-size:12px}
  .breadcrumb-link:hover{color:var(--text-primary);background:var(--bg-raised)}
  .breadcrumb-link.current{color:var(--text-primary);cursor:default}
  .breadcrumb-link.current:hover{background:none}

  /* Views */
  .view{display:none}.view.visible{display:block}

  /* Dashboard */
  .dashboard{padding:24px}
  .page-title{font-family:var(--font-serif);font-size:20px;font-weight:600;margin-bottom:4px}
  .page-subtitle{font-size:11px;color:var(--text-tertiary);margin-bottom:16px}
  .dashboard-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
  .project-card{background:var(--bg-card);border:1px solid var(--border-subtle);
    border-radius:var(--radius);padding:16px;cursor:pointer;transition:var(--transition)}
  .project-card:hover{border-color:var(--border);background:var(--bg-card-hover)}
  .pc-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
  .pc-name{font-family:var(--font-serif);font-size:15px;font-weight:600}
  .pc-status{font-size:9px;font-weight:500;text-transform:uppercase;letter-spacing:.08em;padding:2px 6px;border-radius:2px}
  .s-running{color:var(--green);background:var(--green-dim)}
  .s-idle{color:var(--text-tertiary);background:var(--bg)}
  .s-blocked{color:var(--amber);background:var(--amber-dim)}
  .pc-sprint{font-size:11px;color:var(--text-secondary);margin-bottom:10px}
  .pc-tasks{display:flex;gap:8px;font-size:10px;color:var(--text-tertiary);margin-bottom:8px}
  .pc-tasks .n{color:var(--text-secondary);font-weight:500}
  .progress-bar{display:flex;height:3px;border-radius:1px;overflow:hidden;gap:1px}
  .p-done{background:var(--green)}.p-wip{background:var(--accent)}
  .p-blocked{background:var(--red)}.p-todo{background:var(--border)}
  .pc-footer{display:flex;justify-content:space-between;align-items:center;font-size:10px;
    color:var(--text-tertiary);padding-top:8px;border-top:1px solid var(--border-subtle);font-variant-numeric:tabular-nums}
  .pc-footer span.v{color:var(--text-secondary)}

  /* Project view */
  .project-view{padding:24px}
  .project-info{margin-bottom:16px}
  .project-info h1{font-family:var(--font-serif);font-size:20px;font-weight:600;margin-bottom:4px}
  .project-meta{display:flex;gap:20px;font-size:11px;color:var(--text-tertiary);margin-bottom:4px}
  .project-meta .v{color:var(--text-secondary)}

  /* Sprint toolbar */
  .sprint-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;gap:12px}
  .sprint-toolbar-left{display:flex;align-items:center;gap:8px}
  .sprint-toolbar-right{display:flex;align-items:center;gap:6px}
  .filter-btn{font-family:var(--font-mono);font-size:10px;padding:4px 10px;border-radius:2px;
    border:1px solid var(--border);background:none;color:var(--text-tertiary);cursor:pointer;
    transition:var(--transition);letter-spacing:.02em}
  .filter-btn:hover{border-color:var(--text-tertiary);color:var(--text-secondary)}
  .filter-btn.active{border-color:var(--accent);color:var(--accent);background:var(--accent-dim)}

  /* Sprint list */
  .sprint-list{display:flex;flex-direction:column;gap:2px}
  .sprint-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius);
    padding:8px 14px;display:grid;grid-template-columns:60px 1fr 240px 100px;gap:12px;align-items:center;
    cursor:pointer;transition:var(--transition)}
  .sprint-card:hover{border-color:var(--border);background:var(--bg-card-hover)}
  .sprint-card.active-sprint{border-left:2px solid var(--green)}
  .sc-status{font-size:9px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    padding:2px 6px;border-radius:2px;text-align:center;white-space:nowrap}
  .sc-active{color:var(--green);background:var(--green-dim)}
  .sc-completed{color:var(--text-tertiary);background:var(--bg)}
  .sc-planned{color:var(--blue);background:var(--blue-dim)}
  .sc-body{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden}
  .sc-title{font-size:12px;font-weight:500;white-space:nowrap;flex-shrink:0}
  .sc-goal{font-size:11px;color:var(--text-tertiary);font-family:var(--font-serif);font-style:italic;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
  .sc-tasks-inline{display:flex;gap:8px;font-size:10px;color:var(--text-tertiary);
    white-space:nowrap;align-items:center}
  .sc-tasks-inline .n{color:var(--text-secondary);font-weight:500}
  .sc-stats-inline{display:flex;gap:10px;font-size:10px;color:var(--text-tertiary);
    font-variant-numeric:tabular-nums;white-space:nowrap;justify-content:flex-end}
  .sc-stats-inline span span{color:var(--text-secondary);font-weight:500}

  /* Sprint view */
  .sprint-view-inner{display:flex;flex-direction:column;height:calc(100vh - 48px)}
  .sprint-header{padding:12px 24px;border-bottom:1px solid var(--border-subtle);
    display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
  .sprint-header-left{display:flex;align-items:center;gap:16px}
  .sprint-name{font-size:14px;font-weight:500}
  .sprint-goal-text{font-size:11px;color:var(--text-tertiary);font-family:var(--font-serif);font-style:italic}
  .sprint-header-right{display:flex;align-items:center;gap:12px}
  .sprint-stat{font-size:11px;color:var(--text-tertiary);font-variant-numeric:tabular-nums}
  .sprint-stat .sv{color:var(--text-secondary);font-weight:500}

  .sprint-body{display:grid;grid-template-columns:1fr;flex:1;min-height:0}
  .sprint-body.with-activity{grid-template-columns:1fr 400px}

  .board{padding:16px 24px;overflow-y:auto}
  .sprint-body.with-activity .board{border-right:1px solid var(--border-subtle)}
  .board-columns{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;height:100%}
  .column{display:flex;flex-direction:column;gap:8px;min-height:0}
  .col-header{display:flex;align-items:center;justify-content:space-between;
    padding:0 0 8px;border-bottom:1px solid var(--border-subtle);margin-bottom:4px}
  .col-title{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--text-tertiary)}
  .col-count{font-size:10px;color:var(--text-tertiary);background:var(--bg);padding:1px 6px;border-radius:2px}
  .col-cards{display:flex;flex-direction:column;gap:6px;overflow-y:auto;flex:1}

  .card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius);
    padding:12px;cursor:pointer;transition:var(--transition)}
  .card:hover{background:var(--bg-card-hover);border-color:var(--border)}
  .card.selected{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent-dim)}
  .card-title{font-size:12px;font-weight:500;margin-bottom:8px;line-height:1.4}
  .card-meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
  .card-tag{font-size:9px;font-weight:500;padding:2px 6px;border-radius:2px;letter-spacing:.06em;text-transform:uppercase}
  .tag-feature{background:var(--blue-dim);color:var(--blue)}
  .tag-bug{background:var(--red-dim);color:var(--red)}
  .tag-refactor{background:#a7a22;color:#a7a}
  .tag-chore{background:var(--bg);color:var(--text-tertiary);border:1px solid var(--border)}
  .card-tokens{font-size:10px;color:var(--text-tertiary);margin-left:auto;font-variant-numeric:tabular-nums}
  .card-branch{font-size:10px;color:var(--text-tertiary);margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .card-role{font-size:10px;color:var(--text-tertiary);margin-top:4px}
  .card-blocked{border-left:2px solid var(--amber)}
  .card-blocked-reason{font-size:10px;color:var(--amber);margin-top:6px;padding:4px 6px;background:var(--amber-dim);border-radius:2px}
  .card-actions{display:flex;gap:4px;margin-top:8px}
  .card-actions .btn{font-size:10px;padding:3px 8px}
  .btn{font-family:var(--font-mono);font-size:11px;font-weight:500;padding:6px 14px;
    border-radius:var(--radius);border:1px solid var(--border);background:var(--bg-card);
    color:var(--text-secondary);cursor:pointer;transition:var(--transition)}
  .btn:hover{background:var(--bg-card-hover);color:var(--text-primary);border-color:var(--text-tertiary)}
  .btn-approve{color:var(--green);border-color:#4a933;background:var(--green-dim)}
  .btn-approve:hover{background:#4a933}
  .btn-deny{color:var(--red);border-color:#c5533;background:var(--red-dim)}
  .btn-deny:hover{background:#c5533}

  /* Activity */
  .activity{display:flex;flex-direction:column;height:100%;overflow:hidden}
  .activity-header{padding:8px 12px;border-bottom:1px solid var(--border-subtle);
    display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
  .activity-header-left{display:flex;align-items:center;gap:10px}
  .activity-title{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--text-tertiary)}
  .activity-stream{flex:1;overflow-y:auto;padding:8px 0}
  .event-row{display:grid;grid-template-columns:56px 20px 1fr;gap:8px;padding:5px 16px;
    align-items:start;font-size:11px;transition:var(--transition);cursor:default;min-height:28px}
  .event-row:hover{background:var(--bg-raised)}
  .event-time{color:var(--text-tertiary);font-size:10px;text-align:right;padding-top:1px;font-variant-numeric:tabular-nums}
  .event-icon{width:16px;height:16px;display:flex;align-items:center;justify-content:center;margin-top:1px}
  .event-dot{width:5px;height:5px;border-radius:50%}
  .dot-command{background:var(--accent)}.dot-file{background:var(--blue)}
  .dot-message{background:var(--text-tertiary)}.dot-workflow{background:var(--green)}
  .dot-signal{background:#a7a}.dot-review{background:var(--amber)}.dot-human{background:var(--text-primary)}
  .event-body{color:var(--text-secondary);line-height:1.4}
  .event-body .event-label{color:var(--text-tertiary);font-size:10px}
  .event-body code{color:var(--text-primary);font-size:11px}
  .event-divider{display:flex;align-items:center;gap:8px;padding:8px 16px;font-size:9px;
    color:var(--text-tertiary);letter-spacing:.06em;text-transform:uppercase}
  .event-divider::after{content:'';flex:1;height:1px;background:var(--border-subtle)}

  .done-card{opacity:.6}

  /* Detail panel */
  .detail-overlay{position:fixed;top:0;right:0;bottom:0;width:480px;background:var(--bg-raised);
    border-left:1px solid var(--border);z-index:200;display:flex;flex-direction:column;
    box-shadow:-20px 0 60px rgba(0,0,0,.5);animation:slideIn 200ms ease}
  @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
  .detail-header{padding:16px 20px;border-bottom:1px solid var(--border-subtle);
    display:flex;justify-content:space-between;align-items:flex-start;flex-shrink:0}
  .detail-header h2{font-family:var(--font-serif);font-size:16px;font-weight:600;line-height:1.4;margin-bottom:6px}
  .detail-close{background:none;border:none;color:var(--text-tertiary);cursor:pointer;
    font-size:16px;font-family:var(--font-mono);padding:4px 8px;transition:var(--transition)}
  .detail-close:hover{color:var(--text-primary)}
  .detail-body{flex:1;overflow-y:auto;padding:16px 20px}
  .detail-section{margin-bottom:20px}
  .detail-section-title{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
    color:var(--text-tertiary);margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--border-subtle)}
  .detail-field{display:flex;justify-content:space-between;padding:3px 0;font-size:11px}
  .detail-field-label{color:var(--text-tertiary)}.detail-field-value{color:var(--text-secondary);text-align:right;font-variant-numeric:tabular-nums}
  .detail-criteria{font-size:11px;color:var(--text-secondary);line-height:1.5;font-family:var(--font-serif);padding:8px 0}
  .run-timeline{display:flex;flex-direction:column;gap:2px}
  .run-entry{display:grid;grid-template-columns:52px 1fr auto;gap:10px;padding:8px;font-size:11px;
    border-radius:var(--radius);cursor:pointer;transition:var(--transition)}
  .run-entry:hover{background:var(--bg-card)}
  .run-role{color:var(--text-tertiary);font-size:10px;font-weight:500;text-transform:uppercase;letter-spacing:.04em}
  .run-detail-text{color:var(--text-secondary)}
  .run-outcome{font-size:10px;font-weight:500;padding:1px 6px;border-radius:2px}
  .outcome-done{color:var(--green);background:var(--green-dim)}
  .outcome-steer{color:var(--amber);background:var(--amber-dim)}
  .outcome-failed{color:var(--red);background:var(--red-dim)}
  .run-tokens{font-size:10px;color:var(--text-tertiary);text-align:right;font-variant-numeric:tabular-nums}
  .detail-tag-line{display:flex;gap:8px;align-items:center;margin-top:4px}
  .detail-status{font-size:11px;color:var(--text-tertiary)}

  ::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  ::-webkit-scrollbar-thumb:hover{background:var(--text-tertiary)}
</style>
</head>
<body>

<!-- Topbar -->
<div class="topbar">
  <div class="topbar-left">
    <div class="logo" onclick="navigate('dashboard')">Foreman</div>
    <div class="breadcrumb" id="breadcrumb"></div>
  </div>
  <div class="topbar-right">
    <div class="topbar-tokens" id="topbarTokens"></div>
    <div class="engine-status idle" id="engineStatus"><span class="dot"></span> <span id="engineStatusText">Idle</span></div>
  </div>
</div>

<!-- Dashboard view -->
<div class="view visible" id="view-dashboard">
  <div class="dashboard">
    <div class="page-title">Projects</div>
    <div class="page-subtitle" id="dashboardSubtitle">Loading...</div>
    <div class="dashboard-grid" id="dashboardGrid"></div>
  </div>
</div>

<!-- Project view -->
<div class="view" id="view-project">
  <div class="project-view">
    <div class="project-info">
      <h1 id="projectTitle">Loading...</h1>
      <div class="project-meta" id="projectMeta"></div>
    </div>
    <div class="sprint-toolbar">
      <div class="sprint-toolbar-left">
        <button class="filter-btn active" onclick="filterSprints('all')">All</button>
        <button class="filter-btn" onclick="filterSprints('active')">Active</button>
        <button class="filter-btn" onclick="filterSprints('done')">Done</button>
      </div>
    </div>
    <div class="sprint-list" id="sprintList"></div>
  </div>
</div>

<!-- Sprint view -->
<div class="view" id="view-sprint">
  <div class="sprint-view-inner">
    <div class="sprint-header">
      <div class="sprint-header-left">
        <span class="sprint-name" id="sprintName">Loading...</span>
        <span class="sprint-goal-text" id="sprintGoal"></span>
      </div>
      <div class="sprint-header-right">
        <span class="sprint-stat"><span class="sv" id="sprintProgress">-</span></span>
        <span class="sprint-stat"><span class="sv" id="sprintTokens">-</span> tokens</span>
        <span class="sprint-stat"><span class="sv" id="sprintRuns">-</span> runs</span>
      </div>
    </div>
    <div class="sprint-body with-activity">
      <div class="board">
        <div class="board-columns" id="boardColumns"></div>
      </div>
      <div class="activity">
        <div class="activity-header">
          <div class="activity-header-left"><span class="activity-title">Activity</span></div>
        </div>
        <div class="activity-stream" id="activityStream"></div>
      </div>
    </div>
  </div>
</div>

<!-- Detail panel -->
<div class="detail-overlay" id="detail-panel" style="display:none">
  <div class="detail-header">
    <div>
      <h2 id="detailTitle">Loading...</h2>
      <div class="detail-tag-line">
        <span class="card-tag tag-feature" id="detailTag">feature</span>
        <span class="detail-status" id="detailStatus">status</span>
      </div>
    </div>
    <button class="detail-close" onclick="hideDetail()">&times;</button>
  </div>
  <div class="detail-body">
    <div class="detail-section">
      <div class="detail-section-title">Details</div>
      <div id="detailFields"></div>
    </div>
    <div class="detail-section" id="criteriaSection" style="display:none">
      <div class="detail-section-title">Acceptance Criteria</div>
      <div class="detail-criteria" id="detailCriteria"></div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Run History</div>
      <div class="run-timeline" id="runTimeline"></div>
    </div>
  </div>
</div>

<script>
let currentProject = null;
let currentSprint = null;
let projectData = [];
let sprintData = {};
let taskData = {};
let eventData = [];

function navigate(view, id) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('visible'));

  if (view === 'dashboard') {
    currentProject = null;
    currentSprint = null;
    document.getElementById('view-dashboard').classList.add('visible');
    loadDashboard();
  } else if (view === 'project') {
    currentProject = id;
    currentSprint = null;
    document.getElementById('view-project').classList.add('visible');
    loadProject(id);
  } else if (view === 'sprint') {
    currentSprint = id;
    document.getElementById('view-sprint').classList.add('visible');
    loadSprint(id);
  }
  updateBreadcrumb();
}

function updateBreadcrumb() {
  const bc = document.getElementById('breadcrumb');
  let html = '';

  if (currentProject) {
    const proj = projectData.find(p => p.id === currentProject);
    const projName = proj ? proj.name : currentProject;

    html += '<span class="breadcrumb-sep">/</span>';
    html += `<span class="breadcrumb-link ${currentSprint ? '' : 'current'}" onclick="${currentSprint ? "navigate('project','"+currentProject+"')" : ''}">${projName}</span>`;
  }

  if (currentSprint && currentProject) {
    const sprints = sprintData[currentProject] || [];
    const sprint = sprints.find(s => s.id === currentSprint);
    const sprintName = sprint ? sprint.title : currentSprint;

    html += '<span class="breadcrumb-sep">/</span>';
    html += `<span class="breadcrumb-link current">${sprintName}</span>`;
  }

  bc.innerHTML = html;
}

function formatTokens(count) {
  if (!count) return '0';
  if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
  if (count >= 1000) return (count / 1000).toFixed(0) + 'k';
  return count.toString();
}

function getStatusClass(status) {
  if (status === 'running' || status === 'active') return 's-running';
  if (status === 'blocked') return 's-blocked';
  return 's-idle';
}

function getSprintStatusClass(status) {
  if (status === 'active') return 'sc-active';
  if (status === 'done' || status === 'completed') return 'sc-completed';
  return 'sc-planned';
}

function renderProgressBar(counts) {
  const total = (counts.done || 0) + (counts.in_progress || 0) + (counts.blocked || 0) + (counts.todo || 0);
  if (total === 0) return '';
  let html = '<div class="progress-bar">';
  if (counts.done) html += `<div class="p-done" style="flex:${counts.done}"></div>`;
  if (counts.in_progress) html += `<div class="p-wip" style="flex:${counts.in_progress}"></div>`;
  if (counts.blocked) html += `<div class="p-blocked" style="flex:${counts.blocked}"></div>`;
  if (counts.todo) html += `<div class="p-todo" style="flex:${counts.todo}"></div>`;
  html += '</div>';
  return html;
}

async function loadDashboard() {
  try {
    const resp = await fetch('/api/projects');
    const data = await resp.json();
    projectData = data.projects || [];

    const subtitle = `${projectData.length} projects`;
    document.getElementById('dashboardSubtitle').textContent = subtitle;

    const grid = document.getElementById('dashboardGrid');
    if (projectData.length === 0) {
      grid.innerHTML = '<div style="color:var(--text-tertiary);grid-column:1/-1">No projects found. Use <code>foreman init</code> to create one.</div>';
      return;
    }

    grid.innerHTML = projectData.map(p => `
      <div class="project-card" onclick="navigate('project','${p.id}')">
        <div class="pc-header">
          <div class="pc-name">${p.name}</div>
          <div class="pc-status ${getStatusClass(p.status)}">${p.status}</div>
        </div>
        <div class="pc-sprint">${p.active_sprint ? p.active_sprint.title : 'No active sprint'}</div>
        <div class="pc-tasks">
          <span><span class="n">${p.task_counts.done || 0}</span> done</span>
          <span><span class="n">${p.task_counts.in_progress || 0}</span> in progress</span>
          <span><span class="n">${p.task_counts.blocked || 0}</span> blocked</span>
          <span><span class="n">${p.task_counts.todo || 0}</span> todo</span>
        </div>
        ${renderProgressBar(p.task_counts)}
        <div class="pc-footer">
          <div class="pc-tokens">sprint <span class="v">${formatTokens(p.totals.total_token_count)}</span> tokens</div>
          <div>${p.workflow_id}</div>
        </div>
      </div>
    `).join('');

    // Update engine status
    const hasRunning = projectData.some(p => p.status === 'running');
    const statusEl = document.getElementById('engineStatus');
    const statusTextEl = document.getElementById('engineStatusText');
    if (hasRunning) {
      statusEl.className = 'engine-status running';
      statusTextEl.textContent = 'Running';
    } else {
      statusEl.className = 'engine-status idle';
      statusTextEl.textContent = 'Idle';
    }

  } catch (e) {
    console.error('Failed to load dashboard:', e);
    document.getElementById('dashboardGrid').innerHTML = '<div style="color:var(--red)">Failed to load projects</div>';
  }
}

async function loadProject(projectId) {
  try {
    const [projResp, sprintsResp] = await Promise.all([
      fetch(`/api/projects/${projectId}`),
      fetch(`/api/projects/${projectId}/sprints`)
    ]);
    const projData = await projResp.json();
    const sprintsData = await sprintsResp.json();

    sprintData[projectId] = sprintsData.sprints || [];

    document.getElementById('projectTitle').textContent = projData.name;
    document.getElementById('projectMeta').innerHTML = `
      <span>workflow <span class="v">${projData.workflow_id}</span></span>
      <span>merge target <span class="v">${projData.default_branch}</span></span>
    `;

    renderSprintList(projectId);

  } catch (e) {
    console.error('Failed to load project:', e);
  }
}

function renderSprintList(projectId, filter = 'all') {
  const sprints = sprintData[projectId] || [];
  let filtered = sprints;
  if (filter !== 'all') {
    filtered = sprints.filter(s => s.status === filter);
  }

  const list = document.getElementById('sprintList');
  if (filtered.length === 0) {
    list.innerHTML = '<div style="color:var(--text-tertiary);padding:16px">No sprints found.</div>';
    return;
  }

  list.innerHTML = filtered.map(s => `
    <div class="sprint-card ${s.status === 'active' ? 'active-sprint' : ''}" onclick="navigate('sprint','${s.id}')">
      <div class="sc-status ${getSprintStatusClass(s.status)}">${s.status}</div>
      <div class="sc-body">
        <span class="sc-title">${s.title}</span>
        <span class="sc-goal">${s.goal || ''}</span>
      </div>
      <div class="sc-tasks-inline">
        <span><span class="n">${s.task_counts.done || 0}</span>/<span class="n">${s.task_counts.total || 0}</span> done</span>
        ${renderProgressBar(s.task_counts)}
      </div>
      <div class="sc-stats-inline">
        <span><span>${formatTokens(s.totals.total_token_count)}</span> tok</span>
        <span><span>${s.totals.run_count || 0}</span> runs</span>
      </div>
    </div>
  `).join('');
}

function filterSprints(filter) {
  document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');
  if (currentProject) {
    renderSprintList(currentProject, filter);
  }
}

async function loadSprint(sprintId) {
  try {
    const [sprintResp, tasksResp, eventsResp] = await Promise.all([
      fetch(`/api/sprints/${sprintId}`),
      fetch(`/api/sprints/${sprintId}/tasks`),
      fetch(`/api/sprints/${sprintId}/events?limit=50`)
    ]);
    const sprintData = await sprintResp.json();
    const tasksData = await tasksResp.json();
    const eventsData = await eventsResp.json();

    taskData[sprintId] = tasksData.tasks || [];
    eventData = eventsData.events || [];

    document.getElementById('sprintName').textContent = sprintData.title;
    document.getElementById('sprintGoal').textContent = sprintData.goal || '';

    const counts = sprintData.task_counts || {};
    const total = (counts.done || 0) + (counts.in_progress || 0) + (counts.blocked || 0) + (counts.todo || 0);
    document.getElementById('sprintProgress').textContent = `${counts.done || 0}/${total} done`;
    document.getElementById('sprintTokens').textContent = formatTokens(sprintData.totals?.total_token_count || 0);
    document.getElementById('sprintRuns').textContent = sprintData.totals?.run_count || 0;

    renderBoard(taskData[sprintId]);
    renderActivity(eventData);

  } catch (e) {
    console.error('Failed to load sprint:', e);
  }
}

function renderBoard(tasks) {
  const columns = {
    todo: [],
    in_progress: [],
    blocked: [],
    done: []
  };

  tasks.forEach(t => {
    const status = t.status || 'todo';
    if (columns[status]) {
      columns[status].push(t);
    }
  });

  const container = document.getElementById('boardColumns');
  container.innerHTML = Object.entries(columns).map(([status, statusTasks]) => `
    <div class="column">
      <div class="col-header">
        <span class="col-title">${status.replace('_', ' ')}</span>
        <span class="col-count">${statusTasks.length}</span>
      </div>
      <div class="col-cards">
        ${statusTasks.map(t => renderTaskCard(t)).join('')}
      </div>
    </div>
  `).join('');
}

function renderTaskCard(task) {
  const isBlocked = task.status === 'blocked';
  const isDone = task.status === 'done';

  return `
    <div class="card ${isBlocked ? 'card-blocked' : ''} ${isDone ? 'done-card' : ''}" onclick="showTaskDetail('${task.id}', event)">
      <div class="card-title">${task.title}</div>
      <div class="card-meta">
        <span class="card-tag tag-${task.task_type || 'feature'}">${task.task_type || 'feature'}</span>
        ${task.totals?.total_token_count ? `<span class="card-tokens">${formatTokens(task.totals.total_token_count)} tok</span>` : ''}
      </div>
      ${task.branch_name ? `<div class="card-branch">${task.branch_name}</div>` : ''}
      ${task.assigned_role ? `<div class="card-role">${task.assigned_role}</div>` : ''}
      ${isBlocked && task.blocked_reason ? `<div class="card-blocked-reason">${task.blocked_reason}</div>` : ''}
      ${isBlocked ? `
        <div class="card-actions">
          <button class="btn btn-approve" onclick="approveTask('${task.id}', event)">Approve</button>
          <button class="btn btn-deny" onclick="denyTask('${task.id}', event)">Deny</button>
        </div>
      ` : ''}
    </div>
  `;
}

function renderActivity(events) {
  const container = document.getElementById('activityStream');
  if (events.length === 0) {
    container.innerHTML = '<div style="color:var(--text-tertiary);padding:16px">No activity yet.</div>';
    return;
  }

  container.innerHTML = events.map(e => {
    const time = e.timestamp ? e.timestamp.split('T')[1]?.split('.')[0]?.substring(0, 5) || '' : '';
    const dotClass = getEventDotClass(e.event_type);
    const body = formatEventBody(e);

    return `
      <div class="event-row">
        <span class="event-time">${time}</span>
        <span class="event-icon"><span class="event-dot ${dotClass}"></span></span>
        <span class="event-body">${body}</span>
      </div>
    `;
  }).join('');
}

function getEventDotClass(eventType) {
  if (!eventType) return 'dot-message';
  if (eventType.includes('command')) return 'dot-command';
  if (eventType.includes('file')) return 'dot-file';
  if (eventType.includes('workflow')) return 'dot-workflow';
  if (eventType.includes('signal')) return 'dot-signal';
  if (eventType.includes('review')) return 'dot-review';
  if (eventType.includes('human')) return 'dot-human';
  return 'dot-message';
}

function formatEventBody(event) {
  const payload = event.payload || {};
  const eventType = event.event_type || '';

  let label = eventType.split('.').pop() || eventType;
  let detail = '';

  if (eventType === 'agent.command') {
    detail = `<code>${truncate(payload.command || '', 60)}</code>`;
  } else if (eventType === 'agent.file_change') {
    detail = `<code>${payload.path || ''}</code>`;
  } else if (eventType === 'agent.message') {
    detail = truncate(payload.text || '', 60);
  } else {
    const parts = [];
    for (const key of ['summary', 'note', 'step', 'outcome']) {
      if (payload[key]) {
        parts.push(truncate(String(payload[key]), 40));
      }
    }
    detail = parts.join(' | ');
  }

  return `<span class="event-label">${label}</span> ${detail}`;
}

function truncate(text, limit) {
  if (!text) return '';
  text = String(text).trim();
  if (text.length <= limit) return text;
  return text.substring(0, limit - 3) + '...';
}

async function approveTask(taskId, event) {
  if (event) event.stopPropagation();
  try {
    await fetch(`/api/tasks/${taskId}/approve`, { method: 'POST' });
    if (currentSprint) loadSprint(currentSprint);
  } catch (e) {
    console.error('Failed to approve task:', e);
  }
}

async function denyTask(taskId, event) {
  if (event) event.stopPropagation();
  try {
    await fetch(`/api/tasks/${taskId}/deny`, { method: 'POST' });
    if (currentSprint) loadSprint(currentSprint);
  } catch (e) {
    console.error('Failed to deny task:', e);
  }
}

let currentDetailTask = null;

async function showTaskDetail(taskId, event) {
  if (event) event.stopPropagation();
  currentDetailTask = taskId;

  try {
    const resp = await fetch(`/api/tasks/${taskId}`);
    const data = await resp.json();

    document.getElementById('detailTitle').textContent = data.title || 'Untitled';
    document.getElementById('detailTag').textContent = data.task_type || 'feature';
    document.getElementById('detailTag').className = `card-tag tag-${data.task_type || 'feature'}`;
    document.getElementById('detailStatus').textContent = `${data.status || 'todo'}${data.workflow_current_step ? ' · ' + data.workflow_current_step : ''}`;

    // Build detail fields
    const fieldsHtml = [];
    if (data.branch_name) {
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Branch</span><span class="detail-field-value">${data.branch_name}</span></div>`);
    }
    if (data.created_by) {
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Created by</span><span class="detail-field-value">${data.created_by}</span></div>`);
    }
    if (data.assigned_role) {
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Role</span><span class="detail-field-value">${data.assigned_role}</span></div>`);
    }
    if (data.totals?.total_token_count) {
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Tokens</span><span class="detail-field-value">${formatTokens(data.totals.total_token_count)}</span></div>`);
    }
    if (data.step_visit_counts && Object.keys(data.step_visit_counts).length > 0) {
      const visits = Object.entries(data.step_visit_counts).map(([k, v]) => `${k}: ${v}`).join(', ');
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Step visits</span><span class="detail-field-value">${visits}</span></div>`);
    }
    if (data.blocked_reason) {
      fieldsHtml.push(`<div class="detail-field"><span class="detail-field-label">Blocked reason</span><span class="detail-field-value" style="color:var(--amber)">${data.blocked_reason}</span></div>`);
    }
    document.getElementById('detailFields').innerHTML = fieldsHtml.join('');

    // Acceptance criteria
    const criteriaSection = document.getElementById('criteriaSection');
    if (data.acceptance_criteria) {
      criteriaSection.style.display = 'block';
      document.getElementById('detailCriteria').textContent = data.acceptance_criteria;
    } else {
      criteriaSection.style.display = 'none';
    }

    // Run history
    const runs = data.runs || [];
    const timelineEl = document.getElementById('runTimeline');
    if (runs.length === 0) {
      timelineEl.innerHTML = '<div style="color:var(--text-tertiary);padding:8px 0">No runs yet.</div>';
    } else {
      timelineEl.innerHTML = runs.map(r => {
        const outcomeClass = r.outcome === 'done' ? 'outcome-done' : r.outcome === 'steer' ? 'outcome-steer' : r.outcome === 'failed' ? 'outcome-failed' : '';
        const tokens = r.token_count ? `${formatTokens(r.token_count)} tok` : '';
        const duration = r.duration_ms ? `${Math.round(r.duration_ms / 60000)} min` : '';
        const step = r.workflow_step || '';
        const visit = r.visit_count ? `visit ${r.visit_count}` : '';

        return `
          <div class="run-entry">
            <span class="run-role">${r.role_id || '-'}</span>
            <span class="run-detail-text">${step}${visit ? ' · ' + visit : ''}${duration ? ' · ' + duration : ''}</span>
            <span>
              ${r.outcome ? `<span class="run-outcome ${outcomeClass}">${r.outcome}</span>` : ''}
              ${tokens ? `<div class="run-tokens">${tokens}</div>` : ''}
            </span>
          </div>
        `;
      }).join('');
    }

    document.getElementById('detail-panel').style.display = 'flex';

  } catch (e) {
    console.error('Failed to load task detail:', e);
  }
}

function hideDetail() {
  document.getElementById('detail-panel').style.display = 'none';
  currentDetailTask = null;
}

// Initialize
navigate('dashboard');
</script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for the Foreman dashboard."""

    store: ForemanStore | None = None
    db_path: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Create a thread-local store if db_path is set
        if self.db_path is not None and self.store is None:
            self.__class__.store = ForemanStore(self.db_path)
            self.__class__.store.initialize()
        super().__init__(*args, directory=None, **kwargs)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 404) -> None:
        self._send_json({"error": message}, status)

    def _get_project_status(self, project_id: str) -> str:
        assert self.store is not None
        tasks = self.store.list_tasks(project_id=project_id)
        has_in_progress = any(t.status == "in_progress" for t in tasks)
        has_blocked = any(t.status == "blocked" for t in tasks)
        if has_in_progress:
            return "running"
        if has_blocked:
            return "blocked"
        return "idle"

    def do_GET(self) -> None:
        if self.store is None:
            self._send_error("Store not configured", 500)
            return

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Dashboard HTML
        if path == "/" or path == "/dashboard":
            self._send_html(DASHBOARD_HTML)
            return

        # API: List projects
        if path == "/api/projects":
            projects = self.store.list_projects()
            result = []
            for p in projects:
                active_sprint = self.store.get_active_sprint(p.id)
                task_counts = self.store.task_counts(project_id=p.id)
                totals = self.store.run_totals(project_id=p.id)
                result.append({
                    "id": p.id,
                    "name": p.name,
                    "workflow_id": p.workflow_id,
                    "status": self._get_project_status(p.id),
                    "active_sprint": {
                        "id": active_sprint.id,
                        "title": active_sprint.title,
                    } if active_sprint else None,
                    "task_counts": task_counts,
                    "totals": totals,
                })
            self._send_json({"projects": result})
            return

        # API: Get project
        if path.startswith("/api/projects/"):
            parts = path.split("/")
            if len(parts) == 4:
                project_id = parts[3]
                project = self.store.get_project(project_id)
                if project is None:
                    self._send_error(f"Project not found: {project_id}")
                    return
                self._send_json({
                    "id": project.id,
                    "name": project.name,
                    "workflow_id": project.workflow_id,
                    "default_branch": project.default_branch,
                    "repo_path": project.repo_path,
                    "spec_path": project.spec_path,
                    "methodology": project.methodology,
                })
                return

        # API: List sprints for project
        if path.startswith("/api/projects/") and path.endswith("/sprints"):
            parts = path.split("/")
            if len(parts) == 5:
                project_id = parts[3]
                sprints = self.store.list_sprints(project_id)
                result = []
                for s in sprints:
                    task_counts = self.store.task_counts(sprint_id=s.id)
                    totals = self.store.run_totals(sprint_id=s.id)
                    total_tasks = sum(task_counts.values())
                    result.append({
                        "id": s.id,
                        "title": s.title,
                        "goal": s.goal,
                        "status": s.status,
                        "task_counts": {**task_counts, "total": total_tasks},
                        "totals": totals,
                    })
                self._send_json({"sprints": result})
                return

        # API: Get sprint
        if path.startswith("/api/sprints/"):
            parts = path.split("/")
            if len(parts) == 4:
                sprint_id = parts[3]
                sprint = self.store.get_sprint(sprint_id)
                if sprint is None:
                    self._send_error(f"Sprint not found: {sprint_id}")
                    return
                task_counts = self.store.task_counts(sprint_id=sprint.id)
                totals = self.store.run_totals(sprint_id=sprint.id)
                self._send_json({
                    "id": sprint.id,
                    "title": sprint.title,
                    "goal": sprint.goal,
                    "status": sprint.status,
                    "task_counts": task_counts,
                    "totals": totals,
                })
                return

        # API: List tasks for sprint
        if path.startswith("/api/sprints/") and path.endswith("/tasks"):
            parts = path.split("/")
            if len(parts) == 5:
                sprint_id = parts[3]
                tasks = self.store.list_tasks(sprint_id=sprint_id)
                task_totals = {
                    str(row["task_id"]): row
                    for row in self.store.task_run_totals(sprint_id=sprint_id)
                }
                result = []
                for t in tasks:
                    metrics = task_totals.get(t.id, {})
                    result.append({
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "task_type": t.task_type,
                        "branch_name": t.branch_name,
                        "assigned_role": t.assigned_role,
                        "blocked_reason": t.blocked_reason,
                        "acceptance_criteria": t.acceptance_criteria,
                        "totals": {
                            "total_token_count": metrics.get("total_token_count", 0),
                            "total_cost_usd": metrics.get("total_cost_usd", 0.0),
                            "run_count": metrics.get("run_count", 0),
                        },
                    })
                self._send_json({"tasks": result})
                return

        # API: List events for sprint
        if path.startswith("/api/sprints/") and path.endswith("/events"):
            parts = path.split("/")
            if len(parts) == 5:
                sprint_id = parts[3]
                limit = int(query.get("limit", [50])[0])
                tasks = self.store.list_tasks(sprint_id=sprint_id)
                task_ids = [t.id for t in tasks]
                events = []
                for tid in task_ids:
                    events.extend(self.store.list_events(task_id=tid, limit=limit))
                events.sort(key=lambda e: e.timestamp, reverse=True)
                events = events[:limit]
                events.reverse()
                result = []
                for e in events:
                    result.append({
                        "id": e.id,
                        "event_type": e.event_type,
                        "timestamp": e.timestamp,
                        "role_id": e.role_id,
                        "payload": e.payload,
                    })
                self._send_json({"events": result})
                return

        # API: Get task details
        if path.startswith("/api/tasks/"):
            parts = path.split("/")
            if len(parts) == 4:
                task_id = parts[3]
                task = self.store.get_task(task_id)
                if task is None:
                    self._send_error(f"Task not found: {task_id}")
                    return

                # Get task totals
                totals = self.store.run_totals(task_id=task_id)

                # Get runs for this task
                runs = self.store.list_runs(task_id=task_id)
                runs_data = []
                for r in runs:
                    runs_data.append({
                        "id": r.id,
                        "role_id": r.role_id,
                        "workflow_step": r.workflow_step,
                        "agent_backend": r.agent_backend,
                        "status": r.status,
                        "outcome": r.outcome,
                        "outcome_detail": r.outcome_detail,
                        "token_count": r.token_count,
                        "cost_usd": r.cost_usd,
                        "duration_ms": r.duration_ms,
                        "created_at": r.created_at,
                        "model": r.model,
                    })

                self._send_json({
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "task_type": task.task_type,
                    "branch_name": task.branch_name,
                    "assigned_role": task.assigned_role,
                    "created_by": task.created_by,
                    "blocked_reason": task.blocked_reason,
                    "acceptance_criteria": task.acceptance_criteria,
                    "workflow_current_step": task.workflow_current_step,
                    "step_visit_counts": task.step_visit_counts or {},
                    "totals": totals,
                    "runs": runs_data,
                })
                return

        self._send_error("Not found", 404)

    def do_POST(self) -> None:
        if self.store is None:
            self._send_error("Store not configured", 500)
            return

        parsed = urlparse(self.path)
        path = parsed.path

        # API: Approve task
        if path.endswith("/approve"):
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "api" and parts[2] == "tasks":
                task_id = parts[3]
                # For now, just return success - actual approval handling
                # would require orchestrator integration
                self._send_json({"status": "approved", "task_id": task_id})
                return

        # API: Deny task
        if path.endswith("/deny"):
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "api" and parts[2] == "tasks":
                task_id = parts[3]
                self._send_json({"status": "denied", "task_id": task_id})
                return

        self._send_error("Not found", 404)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default logging
        pass


def run_dashboard(db_path: str, host: str = "localhost", port: int = 8080) -> None:
    """Run the dashboard web server.

    Args:
        db_path: Path to the SQLite database.
        host: Host address to bind to.
        port: Port number to listen on.
    """
    # Set db_path on handler class so each request thread can create its own store
    DashboardHandler.db_path = db_path
    DashboardHandler.store = None

    # Pre-initialize store to verify database is accessible
    init_store = ForemanStore(db_path)
    init_store.initialize()
    init_store.close()

    server = HTTPServer((host, port), DashboardHandler)
    print(f"Foreman dashboard running at http://{host}:{port}/")
    print(f"Database: {db_path}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.shutdown()
