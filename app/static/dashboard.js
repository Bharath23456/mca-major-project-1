const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

const pageDefinitions = [
  { id: "overview", label: "Overview" },
  { id: "infrastructure", label: "Infrastructure" },
  { id: "network", label: "Network" },
  { id: "anomalies", label: "Anomaly detection" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "incidents", label: "Incidents" },
  { id: "alerts", label: "Alert history" },
  { id: "model", label: "Model status" },
  { id: "users", label: "User management", roles: ["ADMIN"] },
  { id: "audit", label: "Audit history", roles: ["ADMIN"] },
  { id: "settings", label: "Settings" },
];

const navigationIcons = {
  overview: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="11" width="7" height="10" rx="1"/><rect x="3" y="14" width="8" height="7" rx="1"/>',
  infrastructure: '<rect x="4" y="3" width="16" height="7" rx="1"/><rect x="4" y="14" width="16" height="7" rx="1"/><path d="M7 6.5h.01M7 17.5h.01M10 6.5h7M10 17.5h7"/>',
  network: '<circle cx="6" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="m8 11 8-4M8 13l8 4"/>',
  anomalies: '<path d="M12 3 4 7v5c0 5 3.4 8 8 9 4.6-1 8-4 8-9V7l-8-4Z"/><path d="M12 8v5M12 16h.01"/>',
  diagnostics: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10.5h5M10.5 8v5"/>',
  incidents: '<path d="m12 3 9 17H3L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
  alerts: '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/>',
  model: '<path d="M12 3v18M3 12h18"/><circle cx="12" cy="12" r="8"/><circle cx="12" cy="7" r="1"/><circle cx="17" cy="12" r="1"/><circle cx="12" cy="17" r="1"/><circle cx="7" cy="12" r="1"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-1a6 6 0 0 1 12 0v1M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5v1"/>',
  audit: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.7 1l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.7-1l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-2l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.7-1l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.7 1l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 2Z"/>',
};

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
    return `<article class="metric-card" data-status="${escapeHtml(status || "unknown")}">
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
    return `<article class="metric-card" data-status="${escapeHtml(item?.status || "unknown")}">
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
    return `<article class="metric-card" data-status="${escapeHtml(status)}">
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

function renderDiagnosticReport(report) {
  const incidents = report?.incidents || [];
  $("#diagnostic-report").innerHTML = `
    <p class="diagnostic-report-meta">${escapeHtml(report?.notice || "Diagnostic evidence is unavailable.")}</p>
    ${report?.prometheus_available === false
      ? '<p class="diagnostic-source-warning">Prometheus is unavailable; this report uses stored application events only.</p>'
      : ""}
    ${incidents.length ? incidents.map((incident) => `
      <article class="diagnostic-incident-card">
        <div class="diagnostic-incident-heading">
          <div><p class="eyebrow">${escapeHtml(incident.affected_target)}</p>
            <h3>${escapeHtml(incident.incident_summary)}</h3></div>
          <div>${statusPill(incident.severity)} <span class="pill pill-unknown">${escapeHtml(incident.evidence_level)}</span></div>
        </div>
        <p class="diagnostic-confidence">Evidence level: ${escapeHtml(incident.confidence?.level)} · ${escapeHtml(incident.confidence?.basis)}</p>
        <div class="diagnostic-evidence-grid">
          <section><h4>Related metrics</h4>
            ${incident.related_metrics?.length
              ? `<ul>${incident.related_metrics.map((item) => `<li>${escapeHtml(item.metric)}: ${escapeHtml(item.value)} ${escapeHtml(item.unit || "")} · ${escapeHtml(localTime(item.timestamp))}</li>`).join("")}</ul>`
              : '<p class="muted">No fresh metric samples for this target.</p>'}
          </section>
          <section><h4>Alerts and anomalies</h4>
            ${incident.related_alerts?.length || incident.related_anomalies?.length
              ? `<ul>
                ${(incident.related_alerts || []).map((item) => `<li>Alert: ${escapeHtml(item.name)} (${escapeHtml(item.severity)}) · ${escapeHtml(item.summary || "")}</li>`).join("")}
                ${(incident.related_anomalies || []).map((item) => `<li>Anomaly: ${escapeHtml(item.detector)} (${escapeHtml(item.severity)}) · ${escapeHtml(item.explanation || "")}</li>`).join("")}
              </ul>`
              : '<p class="muted">No stored alert or anomaly events in this window.</p>'}
          </section>
        </div>
        <h4>Possible contributing factors</h4>
        <ul class="diagnostic-factor-list">${incident.possible_contributing_factors.map((factor) => `
          <li><strong>${escapeHtml(factor.description)}</strong><span>${escapeHtml(JSON.stringify(factor.evidence))}</span></li>`).join("")}</ul>
        <h4>Recommended investigation steps</h4>
        <ol>${incident.recommended_investigation_steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
        <p class="diagnostic-logs">${report.logs?.configured
          ? `${escapeHtml(incident.log_events?.length || 0)} log event(s) available.`
          : escapeHtml(report.logs?.note || "No log source is configured.")}</p>
      </article>`).join("")
      : '<p class="empty">No recent diagnostic evidence is available for this window.</p>'}`;
}

function drawLineChart(canvasId, points, unit, message = "Not enough fresh history yet") {
  const canvas = $(`#${canvasId}`);
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const hint = canvas.parentElement.querySelector(".chart-message");
  if (!context) {
    if (hint) hint.textContent = "Chart rendering is unavailable in this browser";
    return;
  }
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  const valid = points.filter((point) => Number.isFinite(point.value));
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
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime())
      ? ""
      : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };
  context.fillStyle = "#a4b2c5";
  context.textAlign = "left";
  context.fillText(formatTime(valid[0].timestamp), pad.left, rect.height - 4);
  context.textAlign = "right";
  context.fillText(formatTime(valid[valid.length - 1].timestamp), rect.width - pad.right, rect.height - 4);
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
    $("#overview-cards").innerHTML = `<article class="metric-card metric-card-unavailable">
      <div class="metric-name">Live overview</div>
      <div class="metric-value">Unavailable</div>
      <div class="metric-detail">Prometheus overview could not be loaded</div>
    </article>`;
    $("#service-status").textContent = "Unavailable";
    $("#service-status").className = "status-chip status-error";
    $("#last-updated").textContent = "Telemetry unavailable";
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
  await Promise.allSettled([
    ...requests.map(([canvas, metric, unit]) => renderHistory(canvas, metric, unit)),
    loadCapacityForecasts(),
  ]);
}

function forecastNumber(value, suffix = "%") {
  return Number.isFinite(value) ? `${value.toFixed(1)}${suffix}` : "—";
}

function renderCapacityForecasts(result) {
  const rows = result.series || [];
  $("#capacity-forecast-summary").textContent =
    `Prometheus · ${result.lookback_hours}h observed · ${result.horizon_hours}h horizon · ` +
    `generated ${localTime(result.generated_at)}. Historical holdout error is descriptive, not a guarantee.`;
  $("#forecast-warning-button").hidden =
    !result.warning_events_enabled || !["ADMIN", "OPERATOR"].includes(currentUser.role);
  $("#capacity-forecast-rows").innerHTML = rows.length ? rows.map((item) => {
    const forecast = item.forecast;
    const backtest = forecast.backtest;
    const status = forecast.status === "forecast_available"
      ? ""
      : ` <span class="cell-detail">${escapeHtml(forecast.message || forecast.status)}</span>`;
    const exhaustion = forecast.time_to_exhaustion_hours === null
      ? "Not projected within horizon"
      : `${forecastNumber(forecast.time_to_exhaustion_hours, "h")}`;
    return `<tr>
      <td>${escapeHtml(item.metric.replace("_percent", ""))}${status}</td>
      <td>${escapeHtml(item.target)}</td>
      <td>${escapeHtml(forecastNumber(forecast.current_value_percent))}</td>
      <td>${escapeHtml(forecastNumber(forecast.trend_percent_per_hour, "%/h"))}</td>
      <td>${escapeHtml(forecastNumber(forecast.predicted_value_percent))}</td>
      <td>${escapeHtml(exhaustion)}</td>
      <td>${backtest
        ? `${escapeHtml(forecastNumber(backtest.mean_absolute_error_percent))} · ${escapeHtml(backtest.actual_samples)} samples`
        : "Not enough history"}</td>
    </tr>`;
  }).join("") : emptyRow(7, "No resource series are available from Prometheus");
}

async function loadCapacityForecasts() {
  try {
    const result = await getJson("/api/aiops/forecasts/capacity");
    renderCapacityForecasts(result);
  } catch (error) {
    $("#capacity-forecast-summary").textContent = `Capacity forecasts unavailable: ${error.message}`;
    $("#forecast-warning-button").hidden = true;
    $("#capacity-forecast-rows").innerHTML = emptyRow(7, "Forecast data unavailable");
  }
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

async function loadDiagnosticsPage() {
  const result = await getJson("/api/aiops/diagnostics");
  $("#diagnostic-status").textContent = result.report?.status === "evidence_available"
    ? "Evidence available"
    : "No current evidence";
  $("#diagnostic-source").textContent = `${result.source}. ${result.notice}`;
  renderSuggestions(result.suggestions || [], "#diagnostic-page-list");
  renderDiagnosticReport(result.report);
}

async function loadSettings() {
  const configuration = await getJson("/api/v1/config/validate");
  const targets = configuration.endpoint_targets || {};
  const thresholds = configuration.configured_thresholds_percent || {};
  const repeatRules = configuration.incident_repeat_rules || {};
  const configurationCards = [
    {
      label: "Configuration",
      get: () => ({
        value: configuration.valid ? "Valid" : "Review required",
        status: configuration.valid ? "healthy" : "critical",
        detail: "Runtime validation",
      }),
    },
    {
      label: "Prometheus",
      get: () => ({
        value: configuration.prometheus_configured ? "Configured" : "Unavailable",
        status: configuration.prometheus_configured ? "healthy" : "critical",
        detail: "Query endpoint",
      }),
    },
    {
      label: "Probe targets",
      get: () => ({
        value: String(targets.count ?? 0),
        status: targets.valid ? "healthy" : "warning",
        detail: targets.valid ? "Authorized file-based targets" : "Target configuration needs review",
      }),
    },
    {
      label: "Incident recurrence",
      get: () => ({
        value: repeatRules.valid ? "Configured" : "Review rules",
        status: repeatRules.valid ? "healthy" : "critical",
        detail: `${repeatRules.warning_count ?? "?"}/${repeatRules.critical_count ?? "?"} repeats`,
      }),
    },
  ];
  renderCards("#settings-cards", configurationCards, configuration);

  const rows = [
    ["CPU threshold", `${thresholds.cpu_percent ?? "Unavailable"}%`],
    ["Memory threshold", `${thresholds.memory_percent ?? "Unavailable"}%`],
    ["Disk threshold", `${thresholds.disk_percent ?? "Unavailable"}%`],
    ["Prometheus configuration", configuration.prometheus_configured ? "Valid HTTP(S) URL" : "Invalid URL"],
    ["Probe target configuration", targets.valid ? `${targets.count ?? 0} target(s) validated` : "Validation errors found"],
    ["Incident repeat rules", repeatRules.valid
      ? `Warning at ${repeatRules.warning_count}; critical at ${repeatRules.critical_count} within ${repeatRules.window_hours}h`
      : "Invalid repeat thresholds"],
  ];
  const errors = configuration.errors || [];
  $("#settings-details").innerHTML = `
    <dl class="configuration-list">${rows.map(([label, value]) => `
      <div class="configuration-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}
    </dl>
    ${errors.length
      ? `<ul class="configuration-errors">${errors.map((error) => `<li>${escapeHtml(error)}</li>`).join("")}</ul>`
      : '<p class="configuration-ok">No configuration errors reported.</p>'}`;
}

function renderIncidentSummary(incidents, container) {
  $(container).innerHTML = incidents.length ? incidents.map((incident) => `
    <tr><td>#${escapeHtml(incident.id)}</td><td>${escapeHtml(incident.title)}</td>
      <td>${statusPill(incident.severity)}</td><td>${priorityDisplay(incident)}</td>
      <td>${escapeHtml(incident.affected_target || "Unknown target")}</td>
      <td>${statusPill(incident.status)}</td><td>${escapeHtml(localTime(incident.last_updated_at))}</td></tr>`).join("")
    : emptyRow(7, "No incidents recorded");
}

function priorityDisplay(incident) {
  const priority = ["urgent", "high", "normal", "low"].includes(incident.priority)
    ? incident.priority
    : "unknown";
  const repeats = Number(incident.recent_target_incident_count) || 0;
  const repeatLabel = repeats === 1 ? "incident" : "incidents";
  const repeatWindow = incident.recent_target_incident_window_hours || 24;
  return `<span class="priority-label priority-${priority}">${escapeHtml(priority)} · ${escapeHtml(incident.priority_score ?? "—")}</span>
    <span class="cell-detail">${repeats} target ${repeatLabel} in ${repeatWindow}h</span>`;
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
      <td>${priorityDisplay(incident)}</td>
      <td>${escapeHtml(incident.affected_target || "Unknown target")}</td>
      <td>${escapeHtml(incident.related_events?.length ?? 0)}</td>
      <td>${escapeHtml(localTime(incident.first_detected_at))}</td>
      <td>${escapeHtml(localTime(incident.last_updated_at))}</td><td>${statusPill(incident.status)}</td>
      <td>${escapeHtml(incident.assigned_operator?.username || "Unassigned")}</td>
      <td>${operatorControls}</td>
    </tr>`;
  }).join("") : emptyRow(11, "No incidents match this filter");
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
  const activeView = document.querySelector(`.page-view[data-view="${currentView}"]`);
  const loadingMessage = $("#page-loading");
  activeView?.setAttribute("aria-busy", "true");
  loadingMessage.textContent = `Loading ${pageDefinitions.find((page) => page.id === currentView)?.label || "page"}…`;
  loadingMessage.hidden = false;
  try {
    if (currentView === "overview") await loadOverview();
    else if (currentView === "infrastructure") await loadInfrastructure();
    else if (currentView === "network") await loadNetwork();
    else if (currentView === "anomalies") await loadAnomalies();
    else if (currentView === "diagnostics") await loadDiagnosticsPage();
    else if (currentView === "incidents") await loadIncidents();
    else if (currentView === "alerts") await loadAlerts();
    else if (currentView === "model") await loadModelStatus();
    else if (currentView === "users") await loadUsers();
    else if (currentView === "audit") await loadAudit();
    else if (currentView === "settings") await loadSettings();
  } catch (error) {
    if (error.status === 401) {
      window.location.assign("/login");
      return;
    }
    showError(`${pageDefinitions.find((page) => page.id === currentView)?.label || "Page"} failed to load: ${error.message}`);
  } finally {
    activeView?.setAttribute("aria-busy", "false");
    loadingMessage.hidden = true;
  }
}

function renderNavigation() {
  const pages = pageDefinitions.filter((page) => !page.roles || page.roles.includes(currentUser.role));
  $("#primary-nav").innerHTML = pages.map((page) => `
    <a class="nav-link${currentView === page.id ? " active" : ""}" href="#/${page.id}"
      ${currentView === page.id ? 'aria-current="page"' : ""}>
      <span class="nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${navigationIcons[page.id]}</svg></span>
      <span>${escapeHtml(page.label)}</span>
    </a>`).join("");
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
  $("#user-info").textContent = currentUser.username;
  $("#user-avatar").textContent = currentUser.username.slice(0, 2).toUpperCase();
  $("#user-role").textContent = currentUser.role;
  $("#user-role").className = `user-role role-${currentUser.role.toLowerCase()}`;
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
$("#forecast-warning-button").addEventListener("click", async () => {
  const button = $("#forecast-warning-button");
  button.disabled = true;
  button.textContent = "Evaluating…";
  try {
    const result = await getJson("/api/aiops/forecasts/capacity/warnings", { method: "POST" });
    button.textContent = `${result.created_count} warning(s) recorded`;
    await loadAnomalies();
  } catch (error) {
    showError(`Capacity warning evaluation failed: ${error.message}`);
    button.textContent = "Evaluate capacity warnings";
  } finally {
    button.disabled = false;
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
  const related = (incident.related_events || []).map((item) => {
    const evidence = [
      item.summary,
      item.correlation_reason ? `Correlation: ${item.correlation_reason}` : "",
      item.metrics ? `Metrics: ${JSON.stringify(item.metrics)}` : "",
      item.labels && Object.keys(item.labels).length ? `Labels: ${JSON.stringify(item.labels)}` : "",
    ].filter(Boolean).join(" · ");
    return `<li><strong>${escapeHtml(item.event_type)} #${escapeHtml(item.event_id)}</strong>
      <span>${escapeHtml(evidence)}</span></li>`;
  }).join("");
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
    <p>${priorityDisplay(incident)}</p>
    <p class="footnote">${escapeHtml(incident.priority_rationale || "")}</p>
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
