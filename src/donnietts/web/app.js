"use strict";

const $ = (id) => document.getElementById(id);

let settings = { announcements_enabled: false, mode: "paused", timezone: "UTC" };
let announcements = [];
let runs = [];
let currentTab = "status";
const POLL_MS = 5000;
let toastTimer = null;

/* ---------- API ---------- */

async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: {} };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new Error(`Network error talking to the controller (${error.message})`);
  }
  if (response.status === 204) return null;
  let data = null;
  try { data = await response.json(); } catch { /* empty body */ }
  if (!response.ok) {
    let detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    throw new Error(detail);
  }
  return data;
}

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

/* ---------- time helpers (controller timezone) ---------- */

function fmtDate(iso, tz) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz, month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  }).format(date);
}

function fmtFull(iso, tz) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz, year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", second: "2-digit",
  }).format(date);
}

// Returns a Date whose UTC fields equal the wall-clock time in tz.
function wallClock(tz) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date());
  const map = {};
  for (const p of parts) if (p.type !== "literal") map[p.type] = p.value;
  return new Date(Date.UTC(+map.year, +map.month - 1, +map.day, +map.hour, +map.minute, +map.second));
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function snippet(text, max = 80) {
  if (!text) return "—";
  const oneLine = String(text).replace(/\s+/g, " ").trim();
  return oneLine.length > max ? oneLine.slice(0, max - 1) + "…" : oneLine;
}

/* ---------- status ---------- */

async function refreshStatus() {
  try {
    const status = await api("/api/v1/status");
    settings.announcements_enabled = !!status.announcements_enabled;
    settings.mode = status.mode || (status.announcements_enabled ? "active" : "paused");
    settings.timezone = status.timezone || settings.timezone;

    const chip = $("controller-chip");
    chip.className = `chip ${status.status === "ok" ? "ok" : status.status === "degraded" ? "degraded" : "down"}`;
    chip.textContent = status.status === "ok" ? "ONLINE" : status.status === "degraded" ? "DEGRADED" : "DOWN";
    $("version-label").textContent = `v${status.version}`;
    $("tz-label").textContent = status.timezone;

    renderMode();
    renderSpeech(status.speech);
    renderDatabase(status.database);
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    const chip = $("controller-chip");
    chip.className = "chip down";
    chip.textContent = "UNREACHABLE";
    $("speech-dot").className = "dot bad";
    $("speech-status").textContent = "controller unreachable";
    $("db-dot").className = "dot bad";
    $("db-status").textContent = "unknown";
  }
}

function renderMode() {
  const toggle = $("mode-toggle");
  const active = !!settings.announcements_enabled;
  toggle.setAttribute("aria-checked", String(active));
  $("mode-label").textContent = active ? "Announcements active" : "Announcements paused";
  $("mode-hint").textContent = active
    ? "The worker is speaking scheduled announcements."
    : "Due announcements are skipped (reason: announcements paused) until you resume.";
}

function renderSpeech(speech) {
  const dot = $("speech-dot");
  const label = $("speech-status");
  const errorEl = $("speech-error");
  errorEl.textContent = "";
  $("speech-model").textContent = speech.model || "—";
  $("speech-voice").textContent = speech.voice || "—";
  switch (speech.status) {
    case "ready":
      dot.className = "dot ok"; label.textContent = "Ready"; break;
    case "warming":
      dot.className = "dot warn"; label.textContent = "Warming up (model loading)"; break;
    case "misconfigured":
      dot.className = "dot bad"; label.textContent = "Misconfigured"; errorEl.textContent = speech.error || ""; break;
    default:
      dot.className = "dot bad"; label.textContent = "Unavailable"; errorEl.textContent = speech.error || "";
  }
}

function renderDatabase(database) {
  const dot = $("db-dot");
  const label = $("db-status");
  if (database.status === "ready") { dot.className = "dot ok"; label.textContent = "Ready"; }
  else { dot.className = "dot bad"; label.textContent = database.error || "Unavailable"; }
}

/* ---------- next up ---------- */

function nextOccurrences() {
  if (!announcements.length) return [];
  const tz = settings.timezone;
  const now = wallClock(tz);
  const nowMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const upcoming = [];
  for (const a of announcements) {
    if (!a.enabled) continue;
    if (a.kind === "daily" && a.time) {
      const [h, m] = a.time.split(":").map(Number);
      const minute = h * 60 + m;
      const when = today + (minute > nowMinutes ? minute : minute + 24 * 60) * 60000;
      upcoming.push({ a, when });
    } else if (a.kind === "one_off" && a.run_at_utc) {
      const when = new Date(a.run_at_utc).getTime();
      if (when > now.getTime()) upcoming.push({ a, when });
    }
  }
  upcoming.sort((x, y) => x.when - y.when);
  return upcoming.slice(0, 6);
}

function renderNextUp() {
  const list = $("next-list");
  const upcoming = nextOccurrences();
  if (!upcoming.length) {
    list.innerHTML = '<li class="next-text">No upcoming enabled announcements.</li>';
    return;
  }
  const tz = settings.timezone;
  const now = wallClock(tz).getTime();
  list.innerHTML = "";
  for (const { a, when } of upcoming) {
    const li = document.createElement("li");
    const t = document.createElement("span");
    t.className = "next-time";
    const date = new Date(when);
    t.textContent = new Intl.DateTimeFormat("en-US", {
      timeZone: tz, hour: "numeric", minute: "2-digit",
    }).format(date);
    const span = document.createElement("span");
    span.className = "next-text";
    span.textContent = a.kind === "one_off" ? `[one-off] ${snippet(a.template, 60)}` : snippet(a.template, 60);
    const rel = document.createElement("span");
    rel.className = "next-when";
    const delta = Math.round((when - now) / 60000);
    rel.textContent = delta < 60 ? (delta <= 0 ? "now" : `in ${delta} min`) : `in ${Math.round(delta / 60)} h`;
    li.append(t, span, rel);
    list.appendChild(li);
  }
}

/* ---------- schedule ---------- */

async function loadSchedule() {
  try {
    announcements = await api("/api/v1/announcements");
  } catch (error) {
    toast(`Could not load schedule: ${error.message}`, "err");
    return;
  }
  const table = $("schedule-table");
  const empty = $("schedule-empty");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  if (!announcements.length) {
    table.hidden = true; empty.hidden = false; return;
  }
  table.hidden = false; empty.hidden = true;
  const tz = settings.timezone;
  for (const a of announcements) {
    const tr = document.createElement("tr");

    const tdEnabled = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${a.enabled ? "enabled" : "disabled"}`;
    badge.textContent = a.enabled ? "enabled" : "disabled";
    tdEnabled.appendChild(badge);

    const tdTime = document.createElement("td");
    tdTime.className = "mono";
    tdTime.textContent = a.kind === "daily" ? a.time : `one-off ${fmtDate(a.run_at_utc, tz)}`;

    const tdTemplate = document.createElement("td");
    tdTemplate.className = "snippet";
    tdTemplate.textContent = snippet(a.template);
    tdTemplate.title = a.template;

    const tdLead = document.createElement("td");
    tdLead.className = "mono";
    tdLead.textContent = `${a.lead_seconds}s`;

    const tdChanged = document.createElement("td");
    tdChanged.className = "mono";
    tdChanged.textContent = fmtDate(a.updated_at, tz);

    const tdActions = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const toggleBtn = document.createElement("button");
    toggleBtn.className = "btn ghost small";
    toggleBtn.textContent = a.enabled ? "disable" : "enable";
    toggleBtn.onclick = () => patchAnnouncement(a, { enabled: !a.enabled });
    const editBtn = document.createElement("button");
    editBtn.className = "btn ghost small";
    editBtn.textContent = "edit";
    editBtn.onclick = () => openEditDialog(a);
    const delBtn = document.createElement("button");
    delBtn.className = "btn danger small";
    delBtn.textContent = "delete";
    delBtn.onclick = () => deleteAnnouncement(a);
    actions.append(toggleBtn, editBtn, delBtn);
    tdActions.appendChild(actions);

    tr.append(tdEnabled, tdTime, tdTemplate, tdLead, tdChanged, tdActions);
    tbody.appendChild(tr);
  }
}

async function patchAnnouncement(a, changes) {
  try {
    await api(`/api/v1/announcements/${a.id}`, {
      method: "PATCH",
      body: { expected_revision: a.revision, ...changes },
    });
    toast("Announcement updated.");
    await loadSchedule();
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    if (/409|revision|conflict/i.test(error.message)) {
      toast("Announcement changed elsewhere — reloading.", "err");
    } else {
      toast(`Update failed: ${error.message}`, "err");
    }
    await loadSchedule();
  }
}

async function deleteAnnouncement(a) {
  const label = a.kind === "daily" ? `the ${a.time} announcement` : "this one-off announcement";
  if (!confirm(`Delete ${label}?`)) return;
  try {
    await api(`/api/v1/announcements/${a.id}?expected_revision=${a.revision}`, { method: "DELETE" });
    toast("Announcement deleted.");
    await loadSchedule();
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    toast(`Delete failed: ${error.message}`, "err");
    await loadSchedule();
  }
}

/* ---------- add + edit forms ---------- */

$("add-kind").addEventListener("change", () => {
  const oneOff = $("add-kind").value === "one_off";
  $("add-time-label").hidden = oneOff;
  $("add-runat-label").hidden = !oneOff;
  if (oneOff && !$("add-runat").value) {
    const d = new Date(Date.now() + 3600000);
    d.setMinutes(0, 0, 0);
    $("add-runat").value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
});

$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.target.querySelector('button[type="submit"]');
  submit.disabled = true;
  const kind = $("add-kind").value;
  const payload = {
    template: $("add-template").value.trim(),
    enabled: $("add-enabled").checked,
    lead_seconds: Number($("add-lead").value) || 0,
  };
  try {
    if (kind === "daily") {
      payload.time = $("add-time").value;
      await api("/api/v1/announcements/daily", { method: "POST", body: payload });
    } else {
      payload.run_at = new Date($("add-runat").value).toISOString();
      await api("/api/v1/announcements/one-off", { method: "POST", body: payload });
    }
    toast("Announcement added.");
    event.target.reset();
    $("add-template").value = "";
    await loadSchedule();
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    toast(`Add failed: ${error.message}`, "err");
  } finally {
    submit.disabled = false;
  }
});

function openEditDialog(a) {
  const dialog = $("edit-dialog");
  $("edit-id").value = a.id;
  $("edit-revision").value = a.revision;
  $("edit-enabled").checked = !!a.enabled;
  $("edit-lead").value = a.lead_seconds;
  $("edit-template").value = a.template;
  const oneOff = a.kind === "one_off";
  $("edit-time-label").hidden = oneOff;
  $("edit-runat-label").hidden = !oneOff;
  if (oneOff) {
    const d = new Date(a.run_at_utc);
    $("edit-runat").value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  } else {
    $("edit-time").value = a.time || "09:00";
  }
  dialog.showModal();
}

$("edit-cancel").addEventListener("click", () => $("edit-dialog").close());

$("edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const dialog = $("edit-dialog");
  const id = Number($("edit-id").value);
  const revision = Number($("edit-revision").value);
  const oneOff = $("edit-time-label").hidden;
  const changes = { enabled: $("edit-enabled").checked, lead_seconds: Number($("edit-lead").value) || 0 };
  if (oneOff) {
    changes.run_at = new Date($("edit-runat").value).toISOString();
  } else {
    changes.time = $("edit-time").value;
  }
  const template = $("edit-template").value.trim();
  if (template) changes.template = template;
  dialog.close();
  const a = announcements.find((x) => x.id === id);
  await patchAnnouncement(a || { id, revision }, changes);
});

/* ---------- runs ---------- */

async function loadRuns() {
  try {
    runs = await api("/api/v1/runs");
  } catch (error) {
    toast(`Could not load runs: ${error.message}`, "err");
    return;
  }
  const table = $("runs-table");
  const empty = $("runs-empty");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  if (!runs.length) { table.hidden = true; empty.hidden = false; return; }
  table.hidden = false; empty.hidden = true;
  const tz = settings.timezone;
  for (const r of runs) {
    const tr = document.createElement("tr");

    const tdWhen = document.createElement("td");
    tdWhen.className = "mono";
    tdWhen.textContent = fmtFull(r.scheduled_for_utc, tz);

    const tdAnn = document.createElement("td");
    tdAnn.className = "mono";
    tdAnn.textContent = r.announcement_kind === "daily"
      ? (r.announcement_id != null ? `#${r.announcement_id}` : "—")
      : `#${r.announcement_id ?? "—"} one-off`;

    const tdStatus = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge status-${r.status}`;
    badge.textContent = r.status;
    tdStatus.appendChild(badge);

    const tdOutcome = document.createElement("td");
    tdOutcome.className = "snippet";
    let outcome = r.rendered_text || "";
    if (r.status === "failed" && r.error) outcome = `failed: ${r.error}`;
    else if ((r.status === "skipped" || r.status === "cancelled") && r.outcome_reason) outcome = r.outcome_reason;
    tdOutcome.textContent = outcome ? snippet(outcome, 100) : "—";
    tdOutcome.title = outcome;

    tr.append(tdWhen, tdAnn, tdStatus, tdOutcome);
    tbody.appendChild(tr);
  }
}

/* ---------- actions ---------- */

async function toggleMode() {
  const target = !settings.announcements_enabled;
  const toggle = $("mode-toggle");
  toggle.disabled = true;
  try {
    await api("/api/v1/settings", { method: "PATCH", body: { announcements_enabled: target } });
    settings.announcements_enabled = target;
    settings.mode = target ? "active" : "paused";
    renderMode();
    toast(target ? "Announcements resumed." : "Announcements paused.");
  } catch (error) {
    toast(`Could not change mode: ${error.message}`, "err");
  } finally {
    toggle.disabled = false;
  }
}

async function testVoice() {
  const runAt = new Date(Date.now() + 60000).toISOString();
  const button = $("test-voice");
  button.disabled = true;
  try {
    await api("/api/v1/announcements/one-off", {
      method: "POST",
      body: {
        run_at: runAt,
        template: "Testing, testing. This is Donnie checking in.",
        enabled: true,
        lead_seconds: 0,
      },
    });
    toast("Test announcement scheduled for ~1 minute from now.");
    await loadSchedule();
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    toast(`Test failed: ${error.message}`, "err");
  } finally {
    button.disabled = false;
  }
}

$("mode-toggle").addEventListener("click", toggleMode);
$("test-voice").addEventListener("click", testVoice);
$("refresh-schedule").addEventListener("click", loadSchedule);
$("refresh-runs").addEventListener("click", loadRuns);

/* ---------- tabs ---------- */

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    currentTab = tab.dataset.tab;
    $(`tab-${currentTab}`).classList.add("active");
    if (currentTab === "schedule") loadSchedule();
    if (currentTab === "runs") loadRuns();
    if (currentTab === "status") { renderNextUp(); }
  });
});

/* ---------- boot ---------- */

refreshStatus();
setInterval(refreshStatus, POLL_MS);
loadSchedule();
