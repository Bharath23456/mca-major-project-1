const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

const pageDefinitions = [
  { id: "overview", label: "Overview" },
  { id: "infrastructure", label: "Infrastructure" },
  { id: "network", label: "Network" },
  { id: "anomalies", label: "AI anomalies" },
  { id: "incidents", label: "Incidents" },
  { id: "alerts", label: "Alert history" },
  { id: "model", label: "Model status" },
  { id: "users", label: "User management", roles: ["ADMIN"] },
  { id: "audit", label: "Audit history", roles: ["ADMIN"] },
];

const metricDefinitions = [
  { key: "cpu_percent", label: "CPU utilization", unit: "%", decimals: 1 },
  { key: "memory_percent", label: "Memory utilization", unit: "%", decimals: 1 },
  { key: "disk_percent", label: "Disk utilization", unit: "%", decimals: 1 },
  { key: "network_receive_bytes_per_second", label: "Network received", unit: "B/s", decimals: 0 },
  { key: "network_transmit_bytes_per_second", label: "Network transmitted", unit: "B/s", decimals: 0 },
];

let currentUser = null;
let currentView = "overview";
let cachedAnomalies = [];
let cachedAlerts = [];
let cachedUsers = [];
let cachedIncidents = [];
let cachedOperators = [];

const localTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
};

function csrfToken() {
  const entry = document.cookie.split("; ").find((cookie) =>
    cookie.startsWith("cloudnetops_csrf="));
  return entry ? decodeURIComponent(entry.slice("cloudnetops_csrf=".length)) : "";
}

async function getJson(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(path, { cache: "no-store", ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status when the server does not return JSON.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function showError(message) {
  $("#page-error").textContent = message;
  $("#page-error").hidden = false;
}

function clearError() {
  $("#page-error").hidden = true;
  $("#page-error").textContent = "";
}

function statusClass(status) {
  const value = String(status || "unknown").toLowerCase();
  if (["healthy", "up", "resolved", "success", "available", "active"].includes(value)) return "up";
  if (["critical", "unavailable", "down", "error", "failure", "inactive"].includes(value)) return "down";
  if (["warning", "stale", "firing", "open", "acknowledged", "not_trained"].includes(value)) {
    return "warning";
  }
  return "unknown";
}

function statusPill(status) {
  return `<span class="pill pill-${statusClass(status)}">${escapeHtml(status || "unknown")}</span>`;
}

function emptyRow(columns, message = "No records available") {
  return `<tr><td class="empty" colspan="${columns}">${escapeHtml(message)}</td></tr>`;
}

function metricText(value, definition) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "No data";
  return `${Number(value).toLocaleString(undefined, {
    maximumFractionDigits: definition.decimals,
  })} ${definition.unit}`;
}

function renderCards(container, definitions, summary) {
  const cards = definitions.map((definition) => {
    const item = definition.key ? summary.metrics?.[definition.key] : definition.get(summary);
    const value = definition.key ? item?.value : item?.value;
    const status = definition.key ? item?.status : item?.status;
    const detail = definition.key
      ? item?.sample_count
        ? `${item.sample_count} fresh series · ${localTime(item.latest_timestamp)}`
        : status === "stale" ? "Telemetry is stale" : "No fresh telemetry"
      : item?.detail || "";
    const display = definition.unit
      ? metricText(value, definition)
      : value === null || value === undefined ? "Unknown" : String(value);
    return `<article class="metric-card">
      <div class="metric-name">${escapeHtml(definition.label)}</div>
      <div class="metric-value${status === "unknown" || status === "stale" ? " value-stale" : ""}">${escapeHtml(display)}</div>
      <div class="metric-detail">${statusPill(status)} ${escapeHtml(detail)}</div>
    </article>`;
  });
  $(container).innerHTML = cards.join("");
}

function overviewCardDefinitions(summary) {
  const countCard = (label, value, state = "healthy", detail = "") => ({
    label,
    value,
    status: state,
    detail,
  });
  return [
    {
      label: "Infrastructure health",
      get: (data) => ({
        value: data.infrastructure_health.status.toUpperCase(),
        status: data.infrastructure_health.status,
        detail: data.infrastructure_health.reason || "Prometheus health summary",
      }),
    },
    ...metricDefinitions.map((definition) => ({ ...definition, key: definition.key })),
    {
      label: "Active alerts",
      get: (data) => countCard("Active alerts", data.alerts.active, data.alerts.active ? "warning" : "healthy", "Firing"),
    },
    {
      label: "Critical alerts",
      get: (data) => countCard("Critical alerts", data.alerts.critical, data.alerts.critical ? "critical" : "healthy", "Firing"),
    },
    {
      label: "Detected anomalies",
      get: (data) => countCard("Detected anomalies", data.anomalies.total, "healthy", "Stored events"),
    },
    {
      label: "Healthy targets",
      get: (data) => countCard("Healthy targets", data.targets.healthy, "healthy", "Fresh scrape samples"),
    },
    {
      label: "Unavailable targets",
      get: (data) => countCard("Unavailable targets", data.targets.unavailable, data.targets.unavailable ? "critical" : "healthy", `${data.targets.stale} stale · ${data.targets.unknown} unknown`),
    },
  ];
}

function renderOverviewCards(summary) {
  const definitions = overviewCardDefinitions(summary).map((definition) => ({
    ...definition,
    get: definition.get || (() => null),
  }));
  const cards = definitions.map((definition) => {
    const item = definition.key ? summary.metrics?.[definition.key] : definition.get(summary);
    const display = definition.unit
      ? metricText(item?.value, definition)
      : item?.value === null || item?.value === undefined ? "No data" : String(item.value);
    const detail = definition.key
      ? item?.sample_count
        ? `${item.sample_count} fresh series · ${localTime(item.latest_timestamp)}`
        : item?.status === "stale" ? "Telemetry is stale" : "No fresh telemetry"
      : item?.detail || "";
    return `<article class="metric-card">
      <div class="metric-name">${escapeHtml(definition.label)}</div>
      <div class="metric-value${["unknown", "stale"].includes(item?.status) ? " value-stale" : ""}">${escapeHtml(display)}</div>
      <div class="metric-detail">${statusPill(item?.status)} ${escapeHtml(detail)}</div>
    </article>`;
  });
  $("#overview-cards").innerHTML = cards.join("");
}

function renderMetricGrid(container, summary, keys) {
  const definitions = keys.map((key) => metricDefinitions.find((item) => item.key === key));
  const html = definitions.map((definition) => {
    const item = summary.metrics?.[definition.key];
    const status = item?.status || "unknown";
    const value = metricText(item?.value, definition);
    const detail = item?.sample_count
      ? `${item.sample_count} fresh series · ${localTime(item.latest_timestamp)}`
      : status === "stale" ? "Telemetry is stale" : "No fresh telemetry";
    return `<article class="metric-card">
      <div class="metric-name">${escapeHtml(definition.label)}</div>
      <div class="metric-value${["unknown", "stale"].includes(status) ? " value-stale" : ""}">${escapeHtml(value)}</div>
      <div class="metric-detail">${statusPill(status)} ${escapeHtml(detail)}</div>
    </article>`;
  });
  $(container).innerHTML = html.join("");
}

function renderTargets(targets, container) {
  $(container).innerHTML = targets.length ? targets.map((target) => {
    const up = target.up || {};
    const state = up.stale ? "stale" : up.value === 1 ? "healthy" : up.value === 0 ? "unavailable" : "unknown";
    return `<tr><td>${escapeHtml(target.job)}</td><td>${escapeHtml(target.instance)}</td>
      <td>${statusPill(state)}</td><td>${escapeHtml(localTime(up.timestamp))}</td></tr>`;
  }).join("") : emptyRow(4, "No monitoring targets available");
}

function renderEndpoints(endpoints, container) {
  $(container).innerHTML = endpoints.length ? endpoints.map((endpoint) => {
    const success = endpoint.success || {};
    const state = success.stale
      ? "stale"
      : success.value === 1 ? "healthy" : success.value === 0 ? "unavailable" : "unknown";
    const latency = endpoint.latency_seconds;
    const latencyText = latency && !latency.stale && Number.isFinite(latency.value)
      ? `${(latency.value * 1000).toFixed(0)} ms` : "No data";
    const code = endpoint.http_status_code;
    const codeText = code && !code.stale && Number.isFinite(code.value)
      ? String(Math.round(code.value)) : "No data";
    return `<tr><td>${escapeHtml(endpoint.endpoint)}</td><td>${statusPill(state)}</td>
      <td>${escapeHtml(latencyText)}</td><td>${escapeHtml(codeText)}</td>
      <td>${escapeHtml(localTime(success.timestamp))}</td></tr>`;
  }).join("") : emptyRow(5, "No endpoint probe data");
}

function renderAlerts(alerts, container) {
  const query = ($("#alert-search")?.value || "").trim().toLowerCase();
  const filtered = alerts.filter((alert) =>
    `${alert.alertname} ${alert.instance} ${alert.summary} ${alert.status}`.toLowerCase().includes(query));
  $(container).innerHTML = filtered.length ? filtered.map((alert) => `
    <tr>
      <td>${escapeHtml(alert.alertname)}<span class="cell-detail">${escapeHtml(alert.description || "")}</span></td>
      <td>${statusPill(alert.severity)}</td>
      <td>${statusPill(alert.status)}</td>
      <td>${escapeHtml(alert.instance || "—")}</td>
      <td>${escapeHtml(alert.summary || "—")}</td>
      <td>${escapeHtml(localTime(alert.starts_at))}</td>
      <td>${escapeHtml(localTime(alert.updated_at))}</td>
    </tr>`).join("") : emptyRow(7, query ? "No alerts match this filter" : "No alert history received");
}

function renderCompactAlerts(alerts, container) {
  $(container).innerHTML = alerts.length ? alerts.map((alert) => `
    <tr><td>${escapeHtml(alert.alertname)}<span class="cell-detail">${escapeHtml(alert.summary || "")}</span></td>
      <td>${statusPill(alert.severity)}</td><td>${statusPill(alert.status)}</td>
      <td>${escapeHtml(localTime(alert.updated_at))}</td></tr>`).join("") : emptyRow(4, "No alert history received");
}

function renderAnomalies(events, container, searchable = false) {
  const query = searchable ? ($("#anomaly-search")?.value || "").trim().toLowerCase() : "";
  const filtered = events.filter((event) =>
    `${event.detector} ${event.target || ""} ${event.explanation}`.toLowerCase().includes(query));
  $(container).innerHTML = filtered.length ? filtered.map((event) => `
    <tr>
      <td>${escapeHtml(localTime(event.timestamp))}</td>
      <td>${escapeHtml(event.detector === "rule" ? "Configured threshold" : "Isolation Forest")}</td>
      <td>${statusPill(event.severity)}</td>
      ${searchable ? `<td>${escapeHtml(event.target || "Unknown target")}</td>` : ""}
      ${searchable ? `<td>${event.score === null ? "—" : escapeHtml(Number(event.score).toFixed(4))}</td>` : ""}
      <td title="${escapeHtml(event.explanation)}"><span class="cell-detail">${escapeHtml(event.explanation)}</span>
        ${searchable ? `<span class="cell-detail">${escapeHtml(JSON.stringify(event.metrics || {}))}</span>` : ""}
      </td>
    </tr>`).join("") : emptyRow(searchable ? 6 : 4, query ? "No anomalies match this filter" : "No anomaly history recorded");
}

function renderSuggestions(suggestions, container) {
  $(container).innerHTML = suggestions.length ? suggestions.map((item) => `
    <article class="suggestion-card">
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.suggestion)}</p>
      <ul>${(item.evidence || []).map((evidence) =>
        `<li>${escapeHtml(JSON.stringify(evidence))}</li>`).join("")}</ul>
    </article>`).join("") : '<p class="empty">No evidence-based suggestions at this time.</p>';
}

function drawLineChart(canvasId, points, unit, message = "Not enough fresh history yet") {
  const canvas = $(`#${canvasId}`);
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  const valid = points.filter((point) => Number.isFinite(point.value));
  const hint = canvas.parentElement.querySelector(".chart-message");
  if (valid.length < 2) {
    if (hint) hint.textContent = message;
    return;
  }
  if (hint) hint.textContent = "";
  const pad = { left: 48, right: 12, top: 12, bottom: 24 };
  const width = Math.max(1, rect.width - pad.left - pad.right);
  const height = Math.max(1, rect.height - pad.top - pad.bottom);
  const max = unit === "percent" ? 100 : Math.max(1, ...valid.map((point) => point.value));
  const min = unit === "percent" ? 0 : Math.min(0, ...valid.map((point) => point.value));
  context.font = "11px system-ui";
  context.fillStyle = "#91a1b7";
  context.strokeStyle = "rgba(145, 161, 183, .2)";
  context.lineWidth = 1;
  [0, 0.5, 1].forEach((ratioValue) => {
    const value = min + (max - min) * ratioValue;
    const y = pad.top + height * (1 - ratioValue);
    context.beginPath();
    context.moveTo(pad.left, y);
    context.lineTo(rect.width - pad.right, y);
    context.stroke();
    context.fillText(`${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit === "percent" ? "%" : ""}`, 2, y + 4);
  });
  context.strokeStyle = "#62a7ff";
  context.lineWidth = 2;
  context.beginPath();
  valid.forEach((point, index) => {
    const x = pad.left + (index / (valid.length - 1)) * width;
    const y = pad.top + height * (1 - (point.value - min) / (max - min || 1));
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();
}

async function renderHistory(canvasId, metric, unit = "percent") {
  const result = await getJson(`/api/v1/monitoring/history?metric=${encodeURIComponent(metric)}&hours=6`);
  drawLineChart(canvasId, result.series[0]?.points || [], unit);
}

async function loadOverview() {
  const [overview, diagnostics, alerts, anomalies, incidents] = await Promise.allSettled([
    getJson("/api/aiops/overview"),
    getJson("/api/aiops/diagnostics"),
    getJson("/api/v1/alerts?limit=10"),
    getJson("/api/aiops/anomalies?limit=10"),
    getJson("/api/incidents?limit=5"),
  ]);
  if (overview.status === "fulfilled") {
    const data = overview.value;
    renderOverviewCards(data);
    $("#service-status").textContent = data.infrastructure_health.status;
    $("#service-status").className = `status-chip status-${statusClass(data.infrastructure_health.status)}`;
    $("#last-updated").textContent = data.infrastructure_health.collected_at
      ? `Updated ${localTime(data.infrastructure_health.collected_at)}`
      : "Telemetry unavailable";
  } else {
    showError(`Overview unavailable: ${overview.reason.message}`);
  }
  if (diagnostics.status === "fulfilled") {
    renderSuggestions(diagnostics.value.suggestions, "#overview-diagnostics");
  } else {
    $("#overview-diagnostics").innerHTML = `<p class="empty">Diagnostic data unavailable: ${escapeHtml(diagnostics.reason.message)}</p>`;
  }
  if (alerts.status === "fulfilled") {
    renderCompactAlerts(alerts.value, "#overview-alert-rows");
  } else {
    $("#overview-alert-rows").innerHTML = emptyRow(4, `Alert history unavailable: ${alerts.reason.message}`);
  }
  if (anomalies.status === "fulfilled") {
    renderAnomalies(anomalies.value, "#overview-anomaly-rows");
  } else {
    $("#overview-anomaly-rows").innerHTML = emptyRow(4, `Anomaly history unavailable: ${anomalies.reason.message}`);
  }
  if (incidents.status === "fulfilled") {
    renderIncidentSummary(incidents.value, "#overview-incident-rows");
  } else {
    $("#overview-incident-rows").innerHTML = emptyRow(6, `Incident data unavailable: ${incidents.reason.message}`);
  }
  try {
    await renderHistory("overview-cpu-chart", "cpu_percent");
  } catch (error) {
    $("#overview-chart-message").textContent = `History unavailable: ${error.message}`;
  }
}

async function loadInfrastructure() {
  const overview = await getJson("/api/aiops/overview");
  const keys = ["cpu_percent", "memory_percent", "disk_percent"];
  renderMetricGrid("#infrastructure-cards", overview, keys);
  renderTargets(overview.monitoring?.targets || [], "#infrastructure-target-rows");
  const requests = [
    ["chart-cpu", "cpu_percent", "percent"],
    ["chart-memory", "memory_percent", "percent"],
    ["chart-disk", "disk_percent", "percent"],
  ];
  await Promise.allSettled(requests.map(([canvas, metric, unit]) => renderHistory(canvas, metric, unit)));
}

async function loadNetwork() {
  const overview = await getJson("/api/aiops/overview");
  renderMetricGrid("#network-cards", overview, [
    "network_receive_bytes_per_second",
    "network_transmit_bytes_per_second",
  ]);
  renderEndpoints(overview.monitoring?.endpoints || [], "#network-endpoint-rows");
  await Promise.allSettled([
    renderHistory("chart-receive", "network_receive_bytes_per_second", "bytes/second"),
    renderHistory("chart-transmit", "network_transmit_bytes_per_second", "bytes/second"),
  ]);
}

async function loadAnomalies() {
  const [events, diagnostics, model] = await Promise.all([
    getJson("/api/aiops/anomalies?limit=200"),
    getJson("/api/aiops/diagnostics"),
    getJson("/api/aiops/model-status"),
  ]);
  cachedAnomalies = events;
  renderAnomalies(cachedAnomalies, "#anomaly-rows", true);
  renderSuggestions(diagnostics.suggestions, "#diagnostic-list");
  $("#anomaly-model-summary").textContent =
    `Threshold rules: ${model.rule_based_detection} · Isolation Forest: ${model.isolation_forest}`;
  $("#anomaly-model-note").textContent = model.model_error || model.training_note;
}

function renderIncidentSummary(incidents, container) {
  $(container).innerHTML = incidents.length ? incidents.map((incident) => `
    <tr><td>#${escapeHtml(incident.id)}</td><td>${escapeHtml(incident.title)}</td>
      <td>${statusPill(incident.severity)}</td><td>${escapeHtml(incident.affected_target || "Unknown target")}</td>
      <td>${statusPill(incident.status)}</td><td>${escapeHtml(localTime(incident.last_updated_at))}</td></tr>`).join("")
    : emptyRow(6, "No incidents recorded");
}

function renderIncidents(incidents) {
  const filter = $("#incident-status-filter").value;
  const filtered = incidents.filter((incident) => !filter || incident.status === filter);
  $("#incident-rows").innerHTML = filtered.length ? filtered.map((incident) => {
    const operatorControls = currentUser.role === "VIEWER" ? "" : [
      incident.status === "OPEN"
        ? `<button class="button table-action" data-action="acknowledge" data-id="${incident.id}">Acknowledge</button>`
        : "",
      incident.status !== "RESOLVED"
        ? `<button class="button table-action" data-action="resolve" data-id="${incident.id}">Resolve</button>`
        : "",
    ].join("");
    return `<tr>
      <td><button class="text-button" data-action="details" data-id="${escapeHtml(incident.id)}">#${escapeHtml(incident.id)}</button></td>
      <td>${escapeHtml(incident.title)}</td><td>${statusPill(incident.severity)}</td>
      <td>${escapeHtml(incident.affected_target || "Unknown target")}</td>
      <td>${escapeHtml(incident.related_events?.length ?? 0)}</td>
      <td>${escapeHtml(localTime(incident.first_detected_at))}</td>
      <td>${escapeHtml(localTime(incident.last_updated_at))}</td><td>${statusPill(incident.status)}</td>
      <td>${escapeHtml(incident.assigned_operator?.username || "Unassigned")}</td>
      <td>${operatorControls}</td>
    </tr>`;
  }).join("") : emptyRow(10, "No incidents match this filter");
}

async function loadIncidents() {
  const requests = [getJson("/api/incidents?limit=200")];
  if (currentUser.role !== "VIEWER") requests.push(getJson("/api/incidents/operators"));
  const [incidents, operators] = await Promise.all(requests);
  cachedIncidents = incidents;
  cachedOperators = operators || [];
  renderIncidents(cachedIncidents);
}

async function loadAlerts() {
  cachedAlerts = await getJson("/api/v1/alerts?limit=200");
  renderAlerts(cachedAlerts, "#alert-rows");
}

async function loadModelStatus() {
  const model = await getJson("/api/aiops/model-status");
  const status = model.model_availability || model.isolation_forest;
  const features = (model.features || []).map(escapeHtml).join(", ");
  $("#model-details").innerHTML = `
    <article class="model-card"><h2>Isolation Forest</h2><dl>
      <dt>Availability</dt><dd>${statusPill(status)}</dd>
      <dt>Model type</dt><dd>${escapeHtml(model.model_type || "Not available")}</dd>
      <dt>Model version</dt><dd>${escapeHtml(model.model_version || "Not available")}</dd>
      <dt>Training timestamp</dt><dd>${escapeHtml(localTime(model.training_timestamp))}</dd>
      <dt>Feature schema</dt><dd>${features || "Not available"}</dd>
      <dt>Last inference</dt><dd>${escapeHtml(model.last_inference?.status || "Not run")}</dd>
      <dt>Last inference time</dt><dd>${escapeHtml(localTime(model.last_inference?.timestamp))}</dd>
      <dt>Last inference model</dt><dd>${escapeHtml(model.last_inference?.model_status || "Not run")}</dd>
      <dt>Model diagnostic</dt><dd>${escapeHtml(model.model_error || "No load error reported")}</dd>
    </dl></article>
    <article class="model-card"><h2>Threshold detector</h2><dl>
      <dt>Availability</dt><dd>${statusPill(model.rule_based_detection)}</dd>
      <dt>Detection source</dt><dd>Configured CPU, memory, and disk thresholds</dd>
      <dt>Model accuracy</dt><dd>Not reported</dd>
      <dt>Training note</dt><dd>${escapeHtml(model.training_note || "Not available")}</dd>
    </dl></article>`;
}

function filteredUsers() {
  const query = ($("#user-search")?.value || "").trim().toLowerCase();
  return cachedUsers.filter((user) =>
    `${user.username} ${user.email} ${user.role} ${user.is_active}`.toLowerCase().includes(query));
}

function renderUsers() {
  const users = filteredUsers();
  $("#user-rows").innerHTML = users.length ? users.map((user) => `
    <tr>
      <td>${escapeHtml(user.username)}</td><td>${escapeHtml(user.email)}</td>
      <td><select class="user-role-select search-input" data-user-role="${user.id}" aria-label="Role for ${escapeHtml(user.username)}">
        ${["ADMIN", "OPERATOR", "VIEWER"].map((role) =>
          `<option ${user.role === role ? "selected" : ""}>${role}</option>`).join("")}
      </select></td>
      <td>${statusPill(user.is_active ? "active" : "inactive")}</td>
      <td>${escapeHtml(localTime(user.created_at))}</td>
      <td><button class="button table-action" data-user-status="${user.id}" data-active="${user.is_active}">
        ${user.is_active ? "Deactivate" : "Activate"}</button></td>
    </tr>`).join("") : emptyRow(6, "No users match this filter");
}

async function loadUsers() {
  cachedUsers = await getJson("/api/users?limit=200");
  renderUsers();
}

async function loadAudit() {
  const action = $("#audit-action-filter").value;
  const query = ($("#audit-search").value || "").trim().toLowerCase();
  const path = `/api/audit-logs?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`;
  const entries = await getJson(path);
  const filtered = entries.filter((entry) =>
    `${entry.action} ${entry.resource_type} ${entry.resource_id} ${entry.result} ${JSON.stringify(entry.details)}`.toLowerCase().includes(query));
  $("#audit-rows").innerHTML = filtered.length ? filtered.map((entry) => `
    <tr><td>${escapeHtml(localTime(entry.timestamp))}</td><td>${escapeHtml(entry.user_id ?? "System/unknown")}</td>
      <td>${escapeHtml(entry.action)}</td>
      <td>${escapeHtml(entry.resource_type)} ${escapeHtml(entry.resource_id || "")}</td>
      <td>${statusPill(entry.result)}</td><td>${escapeHtml(JSON.stringify(entry.details))}</td></tr>`).join("")
    : emptyRow(6, "No audit events match this filter");
}

async function loadCurrentView() {
  clearError();
  try {
    if (currentView === "overview") await loadOverview();
    else if (currentView === "infrastructure") await loadInfrastructure();
    else if (currentView === "network") await loadNetwork();
    else if (currentView === "anomalies") await loadAnomalies();
    else if (currentView === "incidents") await loadIncidents();
    else if (currentView === "alerts") await loadAlerts();
    else if (currentView === "model") await loadModelStatus();
    else if (currentView === "users") await loadUsers();
    else if (currentView === "audit") await loadAudit();
  } catch (error) {
    if (error.status === 401) {
      window.location.assign("/login");
      return;
    }
    showError(`${pageDefinitions.find((page) => page.id === currentView)?.label || "Page"} failed to load: ${error.message}`);
  }
}

function renderNavigation() {
  const pages = pageDefinitions.filter((page) => !page.roles || page.roles.includes(currentUser.role));
  $("#primary-nav").innerHTML = pages.map((page) =>
    `<a class="nav-link${currentView === page.id ? " active" : ""}" href="#/${page.id}">${escapeHtml(page.label)}</a>`).join("");
  document.querySelectorAll(".page-view").forEach((view) => {
    view.hidden = view.dataset.view !== currentView;
  });
}

async function navigateTo(view, updateHash = true) {
  const allowed = pageDefinitions.some((page) =>
    page.id === view && (!page.roles || page.roles.includes(currentUser.role)));
  currentView = allowed ? view : "overview";
  if (updateHash && window.location.hash !== `#/${currentView}`) {
    window.history.replaceState(null, "", `#/${currentView}`);
  }
  renderNavigation();
  await loadCurrentView();
}

async function initializeDashboard() {
  try {
    currentUser = await getJson("/api/auth/me");
  } catch (error) {
    if (error.status === 401) {
      window.location.assign("/login");
      return;
    }
    showError(`Authentication check failed: ${error.message}`);
    return;
  }
  $("#user-info").textContent = `${currentUser.username} · ${currentUser.role}`;
  $("#scan-button").hidden = !["ADMIN", "OPERATOR"].includes(currentUser.role);
  const initialView = window.location.hash.replace(/^#\//, "") || "overview";
  await navigateTo(initialView, false);
}

$("#refresh-button").addEventListener("click", loadCurrentView);
$("#logout-button").addEventListener("click", async () => {
  const button = $("#logout-button");
  button.disabled = true;
  try {
    await getJson("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  } catch (error) {
    showError(`Sign out failed: ${error.message}`);
    button.disabled = false;
  }
});
$("#scan-button").addEventListener("click", async () => {
  const button = $("#scan-button");
  button.disabled = true;
  button.textContent = "Analyzing…";
  try {
    await getJson("/api/v1/anomalies/scan", { method: "POST" });
    await loadAnomalies();
  } catch (error) {
    showError(`Anomaly scan failed: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Analyze current metrics";
  }
});
$("#anomaly-search").addEventListener("input", () =>
  renderAnomalies(cachedAnomalies, "#anomaly-rows", true));
$("#alert-search").addEventListener("input", () =>
  renderAlerts(cachedAlerts, "#alert-rows"));
$("#incident-status-filter").addEventListener("change", () => renderIncidents(cachedIncidents));
$("#user-search").addEventListener("input", renderUsers);
$("#audit-search").addEventListener("input", () => loadAudit().catch((error) => showError(error.message)));
$("#audit-action-filter").addEventListener("change", () => loadAudit().catch((error) => showError(error.message)));
$("#incident-close").addEventListener("click", () => { $("#incident-detail").hidden = true; });
$("#user-create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  const message = $("#user-create-message");
  message.textContent = "Creating account…";
  try {
    await getJson("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    form.reset();
    message.textContent = "User created.";
    await loadUsers();
  } catch (error) {
    message.textContent = error.message;
  }
});

document.addEventListener("change", async (event) => {
  const target = event.target;
  if (target.matches("[data-user-role]")) {
    const user = cachedUsers.find((item) => item.id === Number(target.dataset.userRole));
    if (!user || user.role === target.value) return;
    if (!window.confirm(`Change ${user.username}'s role from ${user.role} to ${target.value}?`)) {
      target.value = user.role;
      return;
    }
    try {
      await getJson(`/api/users/${user.id}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: target.value }),
      });
      await loadUsers();
    } catch (error) {
      showError(`Role update failed: ${error.message}`);
      target.value = user.role;
    }
  }
});

document.addEventListener("click", async (event) => {
  const statusButton = event.target.closest("[data-user-status]");
  if (statusButton) {
    const userId = Number(statusButton.dataset.userStatus);
    const user = cachedUsers.find((item) => item.id === userId);
    const isActive = statusButton.dataset.active === "true";
    if (!user || !window.confirm(`${isActive ? "Deactivate" : "Activate"} ${user.username}?`)) return;
    try {
      await getJson(`/api/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !isActive }),
      });
      await loadUsers();
    } catch (error) {
      showError(`User status update failed: ${error.message}`);
    }
    return;
  }

  const incidentAction = event.target.closest("[data-action]");
  if (!incidentAction) return;
  const id = Number(incidentAction.dataset.id);
  const action = incidentAction.dataset.action;
  if (action === "details") {
    try {
      const incident = await getJson(`/api/incidents/${id}`);
      renderIncidentDetails(incident);
    } catch (error) {
      showError(`Incident details unavailable: ${error.message}`);
    }
    return;
  }
  if (!window.confirm(`${action === "resolve" ? "Resolve" : "Acknowledge"} incident #${id}?`)) return;
  try {
    await getJson(`/api/incidents/${id}/${action}`, { method: "POST" });
    await loadIncidents();
  } catch (error) {
    showError(`Incident update failed: ${error.message}`);
  }
});

function renderIncidentDetails(incident) {
  $("#incident-detail").hidden = false;
  $("#incident-detail-title").textContent = `#${incident.id} · ${incident.title}`;
  const related = (incident.related_events || []).map((item) =>
    `<li>${escapeHtml(item.event_type)} #${escapeHtml(item.event_id)} · ${escapeHtml(item.summary || item.correlation_reason || "")}</li>`).join("");
  const notes = (incident.notes || []).map((note) =>
    `<li>${escapeHtml(localTime(note.created_at))} · ${escapeHtml(note.author_username)}: ${escapeHtml(note.note)}</li>`).join("");
  const assignment = currentUser.role === "VIEWER" ? "" : `
    <form id="incident-assignment-form" class="assignment-form">
      <label for="incident-operator">Assigned operator</label>
      <select id="incident-operator" name="operator_id">
        <option value="">Unassigned</option>
        ${cachedOperators.map((operator) => `<option value="${operator.id}" ${incident.assigned_operator?.id === operator.id ? "selected" : ""}>${escapeHtml(operator.username)}</option>`).join("")}
      </select>
      <button class="button" type="submit">Save assignment</button>
    </form>`;
  $("#incident-detail-content").innerHTML = `
    <p>${statusPill(incident.status)} ${statusPill(incident.severity)} · Target: ${escapeHtml(incident.affected_target || "Unknown")}</p>
    <p>First detected ${escapeHtml(localTime(incident.first_detected_at))} · Last updated ${escapeHtml(localTime(incident.last_updated_at))}</p>
    <h3>Related events</h3><ul class="incident-event-list">${related || "<li>No related events.</li>"}</ul>
    <h3>Incident notes</h3><ul class="incident-event-list">${notes || "<li>No notes.</li>"}</ul>
    ${assignment}
    ${currentUser.role === "VIEWER" ? "" : `<form id="incident-note-form" class="note-form"><textarea name="note" maxlength="4000" required aria-label="Incident note" placeholder="Add an operational note"></textarea><button class="button" type="submit">Add note</button></form>`}`;
  const assignmentForm = $("#incident-assignment-form");
  if (assignmentForm) {
    assignmentForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const operatorValue = new FormData(assignmentForm).get("operator_id");
      const operatorId = operatorValue ? Number(operatorValue) : null;
      const selectedOperator = cachedOperators.find((operator) => operator.id === operatorId);
      const label = selectedOperator?.username || "Unassigned";
      if (!window.confirm(`Assign incident #${incident.id} to ${label}?`)) return;
      try {
        await getJson(`/api/incidents/${incident.id}/assign`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operator_id: operatorId }),
        });
        await loadIncidents();
        renderIncidentDetails(await getJson(`/api/incidents/${incident.id}`));
      } catch (error) {
        showError(`Incident assignment failed: ${error.message}`);
      }
    });
  }
  const form = $("#incident-note-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const note = new FormData(form).get("note");
      try {
        await getJson(`/api/incidents/${incident.id}/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note }),
        });
        const updated = await getJson(`/api/incidents/${incident.id}`);
        renderIncidentDetails(updated);
      } catch (error) {
        showError(`Incident note failed: ${error.message}`);
      }
    });
  }
}

window.addEventListener("hashchange", () => {
  if (currentUser) navigateTo(window.location.hash.replace(/^#\//, "") || "overview", false);
});
window.addEventListener("resize", () => {
  if (currentView === "overview") renderHistory("overview-cpu-chart", "cpu_percent").catch(() => {});
});
window.setInterval(() => {
  if (currentUser && !document.hidden) loadCurrentView();
}, 30000);
initializeDashboard();
