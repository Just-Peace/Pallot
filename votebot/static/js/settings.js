// The Settings page: the web search engine; sources on/off, what each has saved and how the
// last lookup used it, refresh or clear; and deleting what this browser keeps. Changes that
// affect the ballot are marked with markSettingsChanged(), so an open ballot page reloads
// when the voter goes back to it.

import { showRememberedAddress } from "./address.js";
import { api } from "./api.js";
import { formatBytes, formatDate, h, linkedText, relativeTime } from "./dom.js";
import { clearBrowserData, clearPicksAndNotes, markSettingsChanged } from "./picks.js";
import { ENGINES, currentEngine, setEngine } from "./search.js";

const list = document.querySelector("#source-list");
const summary = document.querySelector("#sources-summary");
const searchSelect = document.querySelector("#search-engine");
const searchStatus = document.querySelector("#search-status");
const sourcesStatus = document.querySelector("#sources-status");
const picksStatus = document.querySelector("#picks-status");
let pollTimer = null; // re-checks the sources while one is refreshing (the TEC's takes minutes)

function say(status, message, kind = "ok") {
  status.className = `status status-${kind}`;
  status.textContent = message;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// What the source has saved on the server: "12 saved responses · 3.1 MB · 2 expired · fetched
// 4 days ago to an hour ago". Snapshot sources describe theirs in their details instead.
function cacheLine(source) {
  if (source.resettable) return null;
  const { entries, bytes, expired, oldest, newest } = source.cache;
  if (!entries) return h("p", { class: "source-cache" }, "Nothing saved yet.");
  const [from, to] = [relativeTime(oldest), relativeTime(newest)];
  const span = from === to ? from : `${from} to ${to}`;
  return h("p", { class: "source-cache" },
    [plural(entries, "saved response"), formatBytes(bytes), expired ? `${expired} expired` : null, `fetched ${span}`]
      .filter(Boolean).join(" · "));
}

// How the last ballot lookup used the source: how many requests it made, and how old the data was.
function lastUseLine(source) {
  const use = source.last_use;
  if (!use || use.status === "off") return null;
  const age = use.as_of ? (source.resettable ? formatDate(use.as_of) : relativeTime(use.as_of)) : null;
  const text = {
    used: source.resettable
      ? `used the snapshot of ${age}`
      : [use.message, use.calls ? plural(use.calls, "request") : "no requests", age ? `data from ${age}` : null]
        .filter(Boolean).join(" · "),
    stale: `no answer, so it used the copy saved ${age}`,
    error: `failed (${use.message})`,
    unused: use.message || "not needed",
  }[use.status];
  const warn = use.status === "stale" || use.status === "error";
  return h("p", { class: `source-last${warn ? " tone-warn" : ""}` }, `Last lookup: ${text}`);
}

function detailList(source) {
  if (!source.details.length) return null;
  return h("dl", { class: "source-facts" }, source.details.map((f) => [h("dt", {}, f.label), h("dd", {}, f.value)]));
}

function sourceRow(source) {
  const resets = source.resettable; // comes with a bundled snapshot, which "clear" goes back to
  const result = h("p", { class: "action-result", "aria-live": "polite" });
  const refreshButton = h("button", {
    class: "icon-btn", type: "button", title: source.refresh_label,
    "aria-label": `${source.refresh_label}: ${source.label}`, disabled: source.busy,
  }, source.busy ? "Refreshing…" : "↻ Refresh");
  const clearButton = h("button", {
    class: "icon-btn", type: "button", title: source.clear_label,
    "aria-label": `${source.clear_label}: ${source.label}`, disabled: source.busy,
  }, resets ? "Reset" : "Clear");
  const toggle = source.toggleable
    ? h("input", { type: "checkbox", role: "switch", id: `toggle-${source.id}`, checked: source.enabled, disabled: source.busy })
    : null;

  toggle?.addEventListener("change", async () => {
    toggle.disabled = true;
    try {
      render(await api.put(`/api/sources/${source.id}`, { enabled: toggle.checked }));
      markSettingsChanged();
      say(sourcesStatus, `${source.label} turned ${toggle.checked ? "on" : "off"}.`);
    } catch (error) {
      toggle.checked = !toggle.checked;
      toggle.disabled = false;
      say(sourcesStatus, error.message, "error");
    }
  });

  refreshButton.addEventListener("click", async () => {
    if (source.refresh_confirm && !confirm(source.refresh_confirm)) return; // it sends or downloads a lot
    refreshButton.disabled = true;
    clearButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
    result.textContent = "";
    try {
      const { message } = await api.post(`/api/sources/${source.id}/refresh`);
      markSettingsChanged();
      await load();
      say(sourcesStatus, `${source.label}: ${message}`);
    } catch (error) {
      refreshButton.disabled = false;
      clearButton.disabled = false;
      refreshButton.textContent = "↻ Refresh";
      result.textContent = error.message;
      say(sourcesStatus, `${source.label}: ${error.message}`, "error"); // the row may have been redrawn meanwhile
      load();
    }
  });

  clearButton.addEventListener("click", async () => {
    const question = resets
      ? `Throw away refreshed ${source.label} data and go back to the bundled snapshot?`
      : `Clear everything cached from ${source.label}? The next lookup will fetch it again.`;
    if (!confirm(question)) return;
    try {
      const { message } = await api.post(`/api/sources/${source.id}/clear`);
      await load();
      say(sourcesStatus, `${source.label}: ${message}`);
    } catch (error) {
      say(sourcesStatus, error.message, "error");
    }
  });

  const name = h("span", { class: "source-name" }, source.label);
  return h(
    "div",
    { class: `source-row${source.enabled ? "" : " is-off"}` },
    h("div", { class: "source-row-head" },
      toggle
        ? h("label", { class: "switch", for: `toggle-${source.id}` }, toggle, name)
        : h("span", { class: "source-name-wrap" }, name, h("span", { class: "pill" }, "Always on"))),
    h("p", { class: "source-desc" }, source.description),
    source.notice ? h("p", { class: `source-notice tone-${source.notice_tone || "info"}` }, linkedText(source.notice)) : null,
    cacheLine(source),
    detailList(source),
    lastUseLine(source),
    h("div", { class: "source-actions" }, refreshButton, clearButton),
    result,
  );
}

function renderSummary(overview) {
  const last = overview.last_lookup;
  const lookup = last
    ? `Last lookup ${relativeTime(last.at)}: ${plural(last.external_calls, "request")} to the sources, `
      + `${last.cache_hits} answered from the saved copies, ${last.elapsed_ms} ms.`
    : "No ballot looked up since VoteBot started.";
  summary.textContent = `${lookup} Everything the server has saved takes ${formatBytes(overview.total_bytes)}.`;
}

function render(overview) {
  renderSummary(overview);
  list.replaceChildren(...overview.sources.map(sourceRow));
  clearTimeout(pollTimer);
  if (overview.sources.some((s) => s.busy)) pollTimer = setTimeout(load, 5000);
}

async function load() {
  try {
    render(await api.get("/api/sources"));
  } catch (error) {
    say(sourcesStatus, error.message, "error");
  }
}

function initSearchEngine() {
  const selected = currentEngine().id;
  searchSelect.replaceChildren(...ENGINES.map((e) => h("option", { value: e.id, selected: e.id === selected }, e.label)));
  searchSelect.addEventListener("change", () => {
    setEngine(searchSelect.value);
    markSettingsChanged();
    say(searchStatus, `Web search now uses ${currentEngine().label}.`);
  });
}

document.querySelector("#clear-all").addEventListener("click", async () => {
  if (!confirm("Clear everything the server saved from every source, and reset TrackAIPAC and the Texas Ethics Commission "
    + "to the data that came with VoteBot? A refreshed Texas Ethics Commission snapshot is thrown away. "
    + "The next lookups will fetch everything again.")) return;
  try {
    const { message } = await api.post("/api/cache/clear");
    await load();
    say(sourcesStatus, message);
  } catch (error) {
    say(sourcesStatus, error.message, "error");
  }
});

document.querySelector("#clear-my-picks").addEventListener("click", () => {
  if (!confirm("Delete all your picks, notes and write-ins from this browser?")) return;
  clearPicksAndNotes();
  markSettingsChanged();
  say(picksStatus, "Your picks, notes and write-ins were removed from this browser.");
});

document.querySelector("#clear-browser-data").addEventListener("click", () => {
  if (!confirm("Delete everything VoteBot keeps in this browser: your picks, notes, write-ins, address and search engine?")) return;
  clearBrowserData();
  markSettingsChanged();
  showRememberedAddress();
  searchSelect.value = currentEngine().id;
  say(picksStatus, "Everything VoteBot kept in this browser was removed.");
});

// Back from the ballot, the browser may show this page as it was left; a lookup since then has
// changed what's saved (and may have paused a source), so ask the server again.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) load();
});

initSearchEngine();
load();
