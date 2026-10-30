const metricDefinitions = [
  { key: "cpu_percent", label: "CPU utilization", unit: "%", decimals: 1 },
  { key: "memory_percent", label: "Memory utilization", unit: "%", decimals: 1 },
  { key: "disk_percent", label: "Disk utilization", unit: "%", decimals: 1 },
  { key: "network_receive_bytes_per_second", label: "Network received", unit: "B/s", decimals: 0 },
  { key: "network_transmit_bytes_per_second", label: "Network transmitted", unit: "B/s", decimals: 0 },
  { key: "system_uptime_seconds", label: "System uptime", unit: "seconds", decimals: 0 },
];

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));
const localTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
};

async function getJson(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status when the server does not return JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function metricCardValue(series, definition) {
  const fresh = series.filter((item) => item && !item.stale && Number.isFinite(item.value));
  if (!fresh.length) return { text: "No data", detail: "Missing or stale sample", stale: true };
  const values = fresh.map((item) => item.value);
  const value = definition.key === "disk_percent" ? Math.max(...values) :
    values.reduce((total, item) => total + item, 0) / values.length;
  const timestamp = fresh.reduce((latest, item) =>
    !latest || new Date(item.timestamp) > new Date(latest) ? item.timestamp : latest, null);
  return {
    text: `${value.toLocaleString(undefined, { maximumFractionDigits: definition.decimals })} ${definition.unit}`,
    detail: `${fresh.length} series · ${localTime(timestamp)}`,
    stale: false,
  };
}

function renderMetricCards(summary) {
  $("#metric-grid").innerHTML = metricDefinitions.map((definition) => {
    const data = metricCardValue(summary.metrics?.[definition.key] || [], definition);
    if (!data.stale && definition.key === "system_uptime_seconds") {
      const uptime = Math.max(0, Number.parseInt(data.text, 10));
      const days = Math.floor(uptime / 86400);
      const hours = Math.floor((uptime % 86400) / 3600);
      const minutes = Math.floor((uptime % 3600) / 60);
      data.text = `${days}d ${hours}h ${minutes}m`;
    }
    return `<article class="metric-card">
      <div class="metric-name">${escapeHtml(definition.label)}</div>
      <div class="metric-value${data.stale ? " value-stale" : ""}">${escapeHtml(data.text)}</div>
      <div class="metric-detail">${escapeHtml(data.detail)}</div>
    </article>`;
  }).join("");
}

function renderEndpoints(endpoints = []) {
  $("#endpoint-rows").innerHTML = endpoints.length ? endpoints.map((endpoint) => {
    const success = endpoint.success;
    const up = success && !success.stale && success.value === 1;
    const down = success && !success.stale && success.value === 0;
    const state = up ? "UP" : down ? "DOWN" : "STALE";
    const kind = up ? "up" : down ? "down" : "warning";
    const latency = endpoint.latency_seconds;
    const latencyText = latency && !latency.stale && Number.isFinite(latency.value)
      ? `${(latency.value * 1000).toFixed(0)} ms` : "No data";
    const statusCode = endpoint.http_status_code;
    const statusText = statusCode && !statusCode.stale && Number.isFinite(statusCode.value)
      ? String(Math.round(statusCode.value)) : "No data";
    const sampleTime = success && !success.stale ? localTime(success.timestamp) : "Stale";
    return `<tr><td>${escapeHtml(endpoint.endpoint)}</td>
      <td><span class="pill pill-${kind}">${state}</span></td>
      <td>${escapeHtml(latencyText)}</td><td>${escapeHtml(statusText)}</td>
      <td>${escapeHtml(sampleTime)}</td></tr>`;
  }).join("") : '<tr><td colspan="5" class="empty">No endpoint probes available</td></tr>';
}

function renderTargets(targets = []) {
  $("#target-rows").innerHTML = targets.length ? targets.map((target) => {
    const fresh = target.up && !target.up.stale;
    const up = fresh && target.up.value === 1;
    const state = !fresh ? "STALE" : up ? "UP" : "DOWN";
    return `<tr><td>${escapeHtml(target.job)}</td><td>${escapeHtml(target.instance)}</td>
      <td><span class="pill pill-${!fresh ? "warning" : up ? "up" : "down"}">${state}</span></td>
      <td>${escapeHtml(fresh ? localTime(target.up.timestamp) : "Stale")}</td></tr>`;
  }).join("") : '<tr><td colspan="4" class="empty">No monitoring targets available</td></tr>';
}

function renderAlerts(alerts = []) {
  $("#alert-rows").innerHTML = alerts.length ? alerts.map((alert) => `
    <tr>
      <td>${escapeHtml(alert.alertname)}<span class="cell-detail">${escapeHtml(alert.summary)}</span></td>
      <td>${escapeHtml(alert.severity)}</td>
      <td><span class="pill pill-${alert.status === "firing" ? "firing" : "up"}">${escapeHtml(alert.status)}</span></td>
      <td>${escapeHtml(localTime(alert.updated_at))}</td>
    </tr>`).join("") : '<tr><td colspan="4" class="empty">No alert history received</td></tr>';
}

function renderAnomalies(events = []) {
  $("#anomaly-rows").innerHTML = events.length ? events.map((event) => `
    <tr>
      <td>${escapeHtml(localTime(event.timestamp))}</td>
      <td>${escapeHtml(event.detector)}</td>
      <td><span class="pill pill-${event.severity === "critical" ? "critical" : "warning"}">${escapeHtml(event.severity)}</span></td>
      <td title="${escapeHtml(event.explanation)}"><span class="cell-detail">${escapeHtml(event.explanation)}</span></td>
    </tr>`).join("") : '<tr><td colspan="4" class="empty">No anomaly history recorded</td></tr>';
}

function drawLineChart(points) {
  const canvas = $("#cpu-chart");
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  context.scale(ratio, ratio);
  context.clearRect(0, 0, rect.width, rect.height);
  const valid = points.filter((point) => Number.isFinite(point.value));
  if (valid.length < 2) {
    $("#chart-message").textContent = "Not enough fresh history yet";
    return;
  }
  $("#chart-message").textContent = "";
  const pad = { left: 38, right: 12, top: 12, bottom: 24 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const max = Math.max(100, ...valid.map((point) => point.value));
  context.font = "11px system-ui";
  context.fillStyle = "#91a1b7";
  context.strokeStyle = "rgba(145, 161, 183, .2)";
  context.lineWidth = 1;
  [0, 50, 100].forEach((tick) => {
    const y = pad.top + height * (1 - tick / max);
    context.beginPath();
    context.moveTo(pad.left, y);
    context.lineTo(rect.width - pad.right, y);
    context.stroke();
    context.fillText(`${tick}%`, 2, y + 4);
  });
  context.strokeStyle = "#62a7ff";
  context.lineWidth = 2;
  context.beginPath();
  valid.forEach((point, index) => {
    const x = pad.left + (index / (valid.length - 1)) * width;
    const y = pad.top + height * (1 - point.value / max);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();
}

async function refreshDashboard() {
  $("#page-error").hidden = true;
  const [summary, alerts, anomalies, model] = await Promise.allSettled([
    getJson("/api/v1/monitoring/summary"),
    getJson("/api/v1/alerts?limit=10"),
    getJson("/api/v1/anomalies?limit=10"),
    getJson("/api/v1/anomalies/status"),
  ]);
  if (summary.status === "fulfilled") {
    renderMetricCards(summary.value);
    renderEndpoints(summary.value.endpoints);
    renderTargets(summary.value.targets);
    $("#service-status").textContent = "Telemetry connected";
    $("#service-status").className = "status-chip status-ok";
    $("#last-updated").textContent = `Updated ${localTime(summary.value.collected_at)}`;
  } else {
    renderMetricCards({ metrics: {} });
    renderEndpoints([]);
    renderTargets([]);
    $("#service-status").textContent = "Telemetry unavailable";
    $("#service-status").className = "status-chip status-error";
    $("#last-updated").textContent = `Last check failed ${localTime(new Date().toISOString())}`;
    $("#page-error").textContent = `Monitoring summary unavailable: ${summary.reason.message}`;
    $("#page-error").hidden = false;
  }
  if (alerts.status === "fulfilled") renderAlerts(alerts.value);
  if (anomalies.status === "fulfilled") renderAnomalies(anomalies.value);
  if (model.status === "fulfilled") {
    $("#model-status").textContent = `Isolation Forest: ${model.value.isolation_forest}`;
  }
  try {
    const history = await getJson("/api/v1/monitoring/history?metric=cpu_percent&hours=6");
    drawLineChart(history.series[0]?.points || []);
  } catch (error) {
    $("#chart-message").textContent = `History unavailable: ${error.message}`;
  }
}

$("#refresh-button").addEventListener("click", refreshDashboard);
$("#scan-button").addEventListener("click", async () => {
  const button = $("#scan-button");
  button.disabled = true;
  button.textContent = "Analyzing…";
  try {
    await getJson("/api/v1/anomalies/scan", {
      method: "POST",
    });
    await refreshDashboard();
  } catch (error) {
    $("#page-error").textContent = `Anomaly scan failed: ${error.message}`;
    $("#page-error").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Analyze current metrics";
  }
});
window.addEventListener("resize", () => refreshDashboard());
refreshDashboard();
window.setInterval(refreshDashboard, 30000);
