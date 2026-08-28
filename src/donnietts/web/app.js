"use strict";

/* Web Awesome components (vendored — no CDN, no build step). */
import "/vendor/wa/components/icon/icon.js";
import "/vendor/wa/components/button/button.js";
import "/vendor/wa/components/switch/switch.js";
import "/vendor/wa/components/tag/tag.js";
import "/vendor/wa/components/tab/tab.js";
import "/vendor/wa/components/tab-panel/tab-panel.js";
import "/vendor/wa/components/tab-group/tab-group.js";
import "/vendor/wa/components/card/card.js";
import "/vendor/wa/components/badge/badge.js";
import "/vendor/wa/components/callout/callout.js";
import { registerIconLibrary } from "/vendor/wa/components/icon/library.js";

const ICONS = {
  "chevron-left": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512"><path d="M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l192 192c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L77.3 256 246.6 86.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-192 192z"/></svg>',
  "chevron-right": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512"><path d="M310.6 233.4c12.5 12.5 12.5 32.8 0 45.3l-192 192c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L242.7 256 73.4 86.6c-12.5-12.5-12.5-32.8-45.3 0l192 192z"/></svg>',
};
registerIconLibrary("default", {
  resolver: (name) => `data:image/svg+xml,${encodeURIComponent(ICONS[name] || ICONS["chevron-right"])}`,
});

const $ = (id) => document.getElementById(id);
const POLL_MS = 5000;
let settings = { announcements_enabled: false, mode: "paused", timezone: "UTC" };
let announcements = [];
let currentTab = "status";
let toastTimer = null;
let scheduleEtag = null;
let loadedScheduleText = "";

async function jsonApi(path, options = {}) {
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
  el.variant = kind === "err" ? "danger" : "success";
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

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

function snippet(text, max = 80) {
  if (!text) return "—";
  const oneLine = String(text).replace(/\s+/g, " ").trim();
  return oneLine.length > max ? oneLine.slice(0, max - 1) + "…" : oneLine;
}

async function refreshStatus() {
  try {
    const status = await jsonApi("/api/v1/status");
    settings.announcements_enabled = !!status.announcements_enabled;
    settings.mode = status.mode || (status.announcements_enabled ? "active" : "paused");
    settings.timezone = status.timezone || settings.timezone;

    const chip = $("controller-chip");
    chip.variant = status.status === "ok" ? "success" : status.status === "degraded" ? "warning" : "danger";
    chip.textContent = status.status === "ok" ? "ONLINE" : status.status === "degraded" ? "DEGRADED" : "DOWN";
    $("version-label").textContent = `v${status.version}`;
    $("tz-label").textContent = status.timezone || "—";
    if (status.schedule && status.schedule.path) $("schedule-path").textContent = status.schedule.path;
    if (status.schedule && status.schedule.status !== "ready") {
      showScheduleError(status.schedule.error || `Schedule is ${status.schedule.status}.`);
    }

    renderMode();
    renderSpeech(status.speech);
    renderDatabase(status.database);
    if (currentTab === "status") renderNextUp();
  } catch {
    const chip = $("controller-chip");
    chip.variant = "danger";
    chip.textContent = "UNREACHABLE";
    $("speech-badge").variant = "danger";
    $("speech-badge").textContent = "controller unreachable";
    $("db-badge").variant = "danger";
    $("db-badge").textContent = "unknown";
  }
}

function renderMode() {
  const toggle = $("mode-toggle");
  const active = !!settings.announcements_enabled;
  if (toggle.checked !== active) toggle.checked = active;
  $("mode-label").textContent = active ? "Announcements active" : "Announcements paused";
  $("mode-hint").textContent = active
    ? "The worker is speaking scheduled announcements."
    : "Due announcements are skipped until you resume.";
}

function renderSpeech(speech) {
  const badge = $("speech-badge");
  const errorEl = $("speech-error");
  $("speech-model").textContent = speech.model || "—";
  $("speech-voice").textContent = speech.voice || "—";
  errorEl.hidden = true;
  if (speech.status === "ready") {
    badge.variant = "success"; badge.textContent = "Ready";
  } else if (speech.status === "warming") {
    badge.variant = "warning"; badge.textContent = "Warming up (model loading)";
  } else {
    badge.variant = "danger"; badge.textContent = speech.status === "misconfigured" ? "Misconfigured" : "Unavailable";
    errorEl.textContent = speech.error || "";
    errorEl.hidden = !speech.error;
  }
}

function renderDatabase(database) {
  const badge = $("db-badge");
  badge.variant = database.status === "ready" ? "success" : "danger";
  badge.textContent = database.status === "ready" ? "Ready" : (database.error || "Unavailable");
}

function nextOccurrences() {
  const tz = settings.timezone;
  const now = new Date();
  const localParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (name) => Number(localParts.find((item) => item.type === name).value);
  const upcoming = [];
  for (const announcement of announcements) {
    if (!announcement.enabled) continue;
    if (announcement.kind === "daily" && announcement.time) {
      const [hour, minute] = announcement.time.split(":").map(Number);
      for (let dayOffset = 0; dayOffset <= 1; dayOffset += 1) {
        const guess = new Date(Date.UTC(part("year"), part("month") - 1, part("day") + dayOffset, hour, minute));
        const formatted = new Intl.DateTimeFormat("en-US", {
          timeZone: tz, timeZoneName: "longOffset", hour: "2-digit",
        }).formatToParts(guess);
        const zone = formatted.find((item) => item.type === "timeZoneName").value;
        const match = zone.match(/GMT([+-])(\d{2}):(\d{2})/);
        const offset = match ? (match[1] === "+" ? 1 : -1) * (Number(match[2]) * 60 + Number(match[3])) : 0;
        const when = guess.getTime() - offset * 60000;
        if (when > Date.now()) { upcoming.push({ a: announcement, when }); break; }
      }
    } else if (announcement.run_at_utc) {
      const when = new Date(announcement.run_at_utc).getTime();
      if (when > Date.now()) upcoming.push({ a: announcement, when });
    }
  }
  return upcoming.sort((left, right) => left.when - right.when).slice(0, 6);
}

function renderNextUp() {
  const list = $("next-list");
  const upcoming = nextOccurrences();
  if (!upcoming.length) {
    list.innerHTML = '<li class="next-text">No upcoming enabled announcements.</li>';
    return;
  }
  list.innerHTML = "";
  for (const { a, when } of upcoming) {
    const li = document.createElement("li");
    const time = document.createElement("span");
    time.className = "next-time";
    time.textContent = new Intl.DateTimeFormat("en-US", {
      timeZone: settings.timezone, hour: "numeric", minute: "2-digit",
    }).format(new Date(when));
    const text = document.createElement("span");
    text.className = "next-text";
    text.textContent = a.kind === "one_off" ? `[one-off] ${snippet(a.template, 60)}` : snippet(a.template, 60);
    const relative = document.createElement("span");
    relative.className = "next-when";
    const minutes = Math.round((when - Date.now()) / 60000);
    relative.textContent = minutes < 60 ? `in ${minutes} min` : `in ${Math.round(minutes / 60)} h`;
    li.append(time, text, relative);
    list.appendChild(li);
  }
}

async function loadAnnouncements() {
  try {
    announcements = await jsonApi("/api/v1/announcements");
    if (currentTab === "status") renderNextUp();
  } catch (error) {
    toast(`Could not load schedule: ${error.message}`, "err");
  }
}

function showScheduleError(message) {
  const error = $("schedule-error");
  error.textContent = message || "";
  error.hidden = !message;
}

function updateDirtyState() {
  $("schedule-dirty").hidden = $("schedule-editor").value === loadedScheduleText;
}

async function loadScheduleEditor({ force = false } = {}) {
  if (!force && $("schedule-editor").value !== loadedScheduleText && loadedScheduleText) {
    if (!confirm("Discard unsaved schedule changes?")) return;
  }
  try {
    const response = await fetch("/api/v1/schedule");
    const text = await response.text();
    if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
    scheduleEtag = response.headers.get("ETag");
    loadedScheduleText = text;
    $("schedule-editor").value = text;
    $("schedule-path").textContent = response.headers.get("X-Schedule-Path") || "schedule.yaml";
    showScheduleError("");
    updateDirtyState();
  } catch (error) {
    showScheduleError(`Could not load schedule: ${error.message}`);
  }
}

async function saveSchedule() {
  const button = $("save-schedule");
  button.disabled = true;
  showScheduleError("");
  try {
    const response = await fetch("/api/v1/schedule", {
      method: "PUT",
      headers: { "Content-Type": "application/yaml", "If-Match": scheduleEtag },
      body: $("schedule-editor").value,
    });
    const text = await response.text();
    if (!response.ok) {
      let message = text;
      try { message = JSON.parse(text).detail || text; } catch { /* plain response */ }
      throw new Error(message || `HTTP ${response.status}`);
    }
    scheduleEtag = response.headers.get("ETag");
    loadedScheduleText = text;
    $("schedule-editor").value = text;
    updateDirtyState();
    toast("Schedule saved and activated.");
    await loadAnnouncements();
    await refreshStatus();
  } catch (error) {
    showScheduleError(error.message);
    toast(`Save failed: ${error.message}`, "err");
  } finally {
    button.disabled = false;
  }
}

const RUN_STATUS_VARIANTS = {
  completed: "success", failed: "danger", interrupted: "danger", planned: "brand",
  ready: "brand", playing: "brand", skipped: "warning", cancelled: "warning",
};

function tagFor(text, variant) {
  const tag = document.createElement("wa-tag");
  tag.variant = variant || "neutral";
  tag.size = "s";
  tag.textContent = text;
  return tag;
}

async function loadRuns() {
  let runs;
  try { runs = await jsonApi("/api/v1/runs"); }
  catch (error) { toast(`Could not load runs: ${error.message}`, "err"); return; }
  const table = $("runs-table");
  const empty = $("runs-empty");
  const body = table.querySelector("tbody");
  body.innerHTML = "";
  if (!runs.length) { table.hidden = true; empty.hidden = false; return; }
  table.hidden = false; empty.hidden = true;
  for (const run of runs) {
    const row = document.createElement("tr");
    const when = document.createElement("td");
    when.className = "mono"; when.textContent = fmtFull(run.scheduled_for_utc, settings.timezone);
    const announcement = document.createElement("td");
    announcement.className = "mono"; announcement.textContent = `#${run.announcement_id ?? "—"}${run.announcement_kind === "one_off" ? " one-off" : ""}`;
    const status = document.createElement("td");
    status.appendChild(tagFor(run.status, RUN_STATUS_VARIANTS[run.status]));
    const outcome = document.createElement("td");
    outcome.className = "snippet";
    const detail = run.error || run.outcome_reason || run.rendered_text || "—";
    outcome.textContent = snippet(detail, 100); outcome.title = detail;
    row.append(when, announcement, status, outcome);
    body.appendChild(row);
  }
}

async function toggleMode() {
  const toggle = $("mode-toggle");
  const target = toggle.checked;
  toggle.disabled = true;
  try {
    await jsonApi("/api/v1/settings", { method: "PATCH", body: { announcements_enabled: target } });
    settings.announcements_enabled = target;
    renderMode();
    toast(target ? "Announcements resumed." : "Announcements paused.");
  } catch (error) {
    toast(`Could not change mode: ${error.message}`, "err");
    renderMode();
  } finally { toggle.disabled = false; }
}

$("mode-toggle").addEventListener("change", toggleMode);
$("refresh-runs").addEventListener("click", loadRuns);
$("reload-schedule").addEventListener("click", () => loadScheduleEditor());
$("save-schedule").addEventListener("click", saveSchedule);
$("schedule-editor").addEventListener("input", updateDirtyState);
$("schedule-editor").addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveSchedule();
  } else if (event.key === "Tab") {
    event.preventDefault();
    const editor = event.target;
    const start = editor.selectionStart;
    editor.setRangeText("  ", start, editor.selectionEnd, "end");
    updateDirtyState();
  }
});

$("tabs").addEventListener("wa-tab-show", (event) => {
  currentTab = event.detail.name;
  if (currentTab === "schedule") loadScheduleEditor();
  if (currentTab === "runs") loadRuns();
  if (currentTab === "status") renderNextUp();
});

refreshStatus();
loadAnnouncements();
loadScheduleEditor({ force: true });
setInterval(refreshStatus, POLL_MS);
