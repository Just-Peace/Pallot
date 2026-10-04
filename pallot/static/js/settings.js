// The Settings page: the appearance; the web search engine; the sources, under the groups the
// server puts them in, on/off (one by one, or a whole group), what each has saved and how the last
// lookup used it, refresh or clear; and Data, which clears what this browser keeps, what the server
// saved, or both. Changes that affect the ballot are marked with markSettingsChanged(), so an open
// ballot page reloads when the voter goes back to it. It imports page.js first, which draws the
// left pane.

import "./page.js";
import { showRememberedAddress } from "./address.js";
import { api } from "./api.js";
import { $, h, linkedText, onReturn, setStatus } from "./dom.js";
import { SHORT_DATE, formatBytes, formatDate, plural, relativeTime } from "./format.js";
import { clearBrowserData, clearPicksAndNotes, restoreBrowserData } from "./picks.js";
import { ENGINES, currentEngine, setEngine } from "./search.js";
import { markSettingsChanged, setUiPref, uiPref } from "./storage.js";
import { showToast } from "./toast.js";

const groupList = $("#source-groups");
const summary = $("#sources-summary");
const searchSelect = $("#search-engine");
const searchStatus = $("#search-status");
const sourcesStatus = $("#sources-status");
const dataStatus = $("#data-status");
const clearAllButton = $("#clear-all");
const clearEverythingButton = $("#clear-everything");
let pollTimer = null; // re-checks the sources while one is refreshing (the TEC's takes minutes)
const groups = new Map(); // group id → { list, status, update }
const rows = new Map(); // source id → { row, update }
let prompts = null; // the server words the prompts of "Clear all source caches" and "Clear all my data"

// What the source has saved on the server: "12 saved responses · 3.1 MB · 2 expired · fetched
// 4 days ago to an hour ago". Snapshot sources describe theirs in their details instead, and a
// frozen list saves nothing.
function cacheLine(source) {
  if (source.resettable || source.frozen) return null;
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
  const dated = source.resettable || source.frozen;
  const age = use.as_of ? (dated ? formatDate(use.as_of, SHORT_DATE) : relativeTime(use.as_of)) : null;
  const text = {
    used: dated
      ? `used the ${source.frozen ? "list captured on" : "snapshot of"} ${age}`
      : [use.message, use.calls ? plural(use.calls, "request") : "no requests", age ? `data from ${age}` : null]
        .filter(Boolean).join(" · "),
    stale: `no answer, so it used the copy saved ${age}`,
    error: `failed (${use.message})`,
    unused: use.message || "not needed",
  }[use.status];
  const warn = use.status === "stale" || use.status === "error";
  return h("p", { class: ["source-last", warn && "tone-warn"] }, `Last lookup: ${text}`);
}

function detailList(source) {
  if (!source.details.length) return null;
  return h("dl", { class: "source-facts" }, source.details.map((f) => [h("dt", {}, f.label), h("dd", {}, f.value)]));
}

// A source's row is drawn once and then updated in place (update below), so a change or the
// poll while a refresh runs doesn't take the focus away. What its buttons did shows in its
// group's status line, next to it.
function sourceRow(initial, status) {
  let source = initial;
  const refreshButton = h("button", {
    class: "icon-btn", type: "button", title: source.refresh_label, "aria-label": `${source.refresh_label}: ${source.label}`,
  });
  const clearButton = h("button", {
    class: "icon-btn", type: "button", title: source.clear_label, "aria-label": `${source.clear_label}: ${source.label}`,
  }, source.resettable ? "Reset" : "Clear");
  const toggle = source.toggleable ? h("input", { type: "checkbox", role: "switch", id: `toggle-${source.id}` }) : null;
  const state = h("div", { class: "source-state" });

  function showBusy(busy) {
    refreshButton.disabled = clearButton.disabled = busy;
    refreshButton.textContent = busy ? "Refreshing…" : "↻ Refresh";
  }

  toggle?.addEventListener("change", async () => {
    toggle.disabled = true;
    try {
      render(await api.put(`/api/sources/${source.id}`, { enabled: toggle.checked }));
      markSettingsChanged();
      setStatus(status, `${source.label} turned ${toggle.checked ? "on" : "off"}.`, "ok");
    } catch (error) {
      toggle.checked = !toggle.checked;
      toggle.disabled = false;
      setStatus(status, error.message, "error");
    }
  });

  refreshButton.addEventListener("click", async () => {
    if (source.refresh_confirm && !confirm(source.refresh_confirm)) return; // it sends or downloads a lot
    showBusy(true);
    try {
      const { message } = await api.post(`/api/sources/${source.id}/refresh`);
      markSettingsChanged();
      await load();
      setStatus(status, `${source.label}: ${message}`, "ok");
    } catch (error) {
      showBusy(false);
      setStatus(status, `${source.label}: ${error.message}`, "error");
      load();
    }
  });

  clearButton.addEventListener("click", async () => {
    if (!confirm(source.clear_confirm)) return;
    try {
      const { message } = await api.post(`/api/sources/${source.id}/clear`);
      await load();
      setStatus(status, `${source.label}: ${message}`, "ok");
    } catch (error) {
      setStatus(status, error.message, "error");
    }
  });

  const name = h("span", { class: "source-name" }, source.label);
  const row = h(
    "div",
    { class: "source-row" },
    h("div", { class: "source-row-head" },
      toggle
        ? h("label", { class: "switch", for: `toggle-${source.id}` }, toggle, name)
        : h("span", { class: "source-name-wrap" }, name, h("span", { class: "pill" }, "Always on"))),
    h("p", { class: "source-desc" }, source.description),
    state,
    source.frozen ? null : h("div", { class: "source-actions" }, source.refreshable ? refreshButton : null, clearButton),
  );

  function update(next) {
    source = next;
    row.classList.toggle("is-off", !source.enabled);
    if (toggle) {
      toggle.checked = source.enabled;
      toggle.disabled = source.busy;
    }
    showBusy(source.busy);
    state.replaceChildren(...[
      source.notice ? h("p", { class: ["source-notice", `tone-${source.notice_tone || "info"}`] }, linkedText(source.notice)) : null,
      cacheLine(source),
      detailList(source),
      lastUseLine(source),
    ].filter(Boolean));
  }

  update(source);
  return { row, update };
}

// The groups the voter folded stay folded when they come back (a view choice, kept in this browser).
const foldedGroups = () => new Set(uiPref("foldedSourceGroups") || []);

// A group of sources: a heading that folds it, how many of its sources are on, its description,
// "Turn all on" and "Turn all off" when the server offers them (one request for the whole group),
// its status line and its sources' rows. Drawn once, then updated in place, like the rows.
function sourceGroup(group) {
  const count = h("span", { class: "pill source-group-count" });
  const status = h("p", { class: "status", role: "status", "aria-live": "polite" });
  const list = h("div", { class: "source-list" });
  const allOn = h("button", { class: "btn small", type: "button" }, "Turn all on");
  const allOff = h("button", { class: "btn small", type: "button" }, "Turn all off");
  const panel = h("details", { class: "source-group", open: !foldedGroups().has(group.id) },
    h("summary", {}, h("h3", {}, group.title), count),
    h("p", { class: "source-group-desc" }, group.description),
    group.toggle_all ? h("div", { class: "button-row source-group-actions" }, allOn, allOff) : null,
    status,
    list);
  let switches = [];

  panel.addEventListener("toggle", () => {
    const folded = foldedGroups();
    if (panel.open) folded.delete(group.id);
    else folded.add(group.id);
    setUiPref("foldedSourceGroups", [...folded]);
  });

  async function turnAll(enabled, button, other) {
    allOn.disabled = allOff.disabled = true;
    try {
      render(await api.put(`/api/source-groups/${group.id}`, { enabled }));
      markSettingsChanged();
      setStatus(status, `Every source under ${group.title} turned ${enabled ? "on" : "off"}.`, "ok");
    } catch (error) {
      setStatus(status, error.message, "error");
      showCounts();
    }
    if (document.activeElement === document.body || button.disabled) other.focus(); // the pressed one is now disabled
  }
  allOn.addEventListener("click", () => turnAll(true, allOn, allOff));
  allOff.addEventListener("click", () => turnAll(false, allOff, allOn));

  function showCounts() {
    const on = switches.filter((s) => s.enabled).length;
    count.textContent = `${on} of ${plural(switches.length, "source")} on`;
    const toggleable = switches.filter((s) => s.toggleable);
    allOn.disabled = toggleable.every((s) => s.enabled);
    allOff.disabled = toggleable.every((s) => !s.enabled);
  }

  function update(sources) {
    switches = sources;
    showCounts();
  }

  groupList.append(panel);
  return { list, status, update };
}

function renderSummary(overview) {
  const last = overview.last_lookup;
  const lookup = last
    ? `Last lookup ${relativeTime(last.at)}: ${plural(last.external_calls, "request")} to the sources, `
      + `${last.cache_hits} answered from the saved copies, ${last.elapsed_ms} ms.`
    : "No ballot looked up since Pallot started.";
  summary.textContent = `${lookup} Everything the server has saved takes ${formatBytes(overview.total_bytes)}.`;
  $("#cache-size").textContent = ` (${formatBytes(overview.total_bytes)} now)`;
}

// Clearing everything the server saved is refused while a refresh runs, so its buttons wait too.
function showServerClears(busy) {
  for (const button of [clearAllButton, clearEverythingButton]) {
    button.disabled = busy;
    button.title = busy ? "A refresh is running; try again when it's done." : "";
  }
}

function render(overview) {
  renderSummary(overview);
  prompts = overview;
  for (const group of overview.groups) {
    if (!groups.has(group.id)) groups.set(group.id, sourceGroup(group));
  }
  for (const source of overview.sources) {
    const drawn = rows.get(source.id);
    if (drawn) {
      drawn.update(source);
    } else {
      const group = groups.get(source.group);
      const added = sourceRow(source, group.status);
      rows.set(source.id, added);
      group.list.append(added.row);
    }
  }
  for (const [id, group] of groups) group.update(overview.sources.filter((s) => s.group === id));
  const busy = overview.sources.some((s) => s.busy);
  showServerClears(busy);
  clearTimeout(pollTimer);
  if (busy) pollTimer = setTimeout(load, 5000);
}

async function load() {
  try {
    render(await api.get("/api/sources"));
  } catch (error) {
    setStatus(sourcesStatus, error.message, "error");
  }
}

function initSearchEngine() {
  const selected = currentEngine().id;
  searchSelect.replaceChildren(...ENGINES.map((e) => h("option", { value: e.id, selected: e.id === selected }, e.label)));
  searchSelect.addEventListener("change", () => {
    setEngine(searchSelect.value);
    markSettingsChanged();
    setStatus(searchStatus, `Web search now uses ${currentEngine().label}.`, "ok");
  });
}

// Appearance: theme.js, in every page's <head>, applies it here at once and in other tabs.
const themeChoice = $("#theme");

function showTheme() {
  const theme = ["light", "dark"].includes(uiPref("theme")) ? uiPref("theme") : "system";
  themeChoice.querySelector(`input[value="${theme}"]`).checked = true;
  document.dispatchEvent(new Event("pallot:theme"));
}

themeChoice.addEventListener("change", (event) => {
  setUiPref("theme", event.target.value);
  showTheme();
});

// What's kept in this browser is cleared at once, with Undo to put it back (the server's copies
// can't be put back, so those still ask first).
function clearInBrowser(clear, message, nothing) {
  const removed = clear();
  markSettingsChanged();
  showBrowserData();
  if (!Object.keys(removed).length) {
    showToast(nothing);
    return;
  }
  showToast(message, {
    label: "Undo",
    run: () => {
      restoreBrowserData(removed);
      markSettingsChanged(); // an open ballot reloads again, with them back
      showBrowserData();
    },
  });
}

// The parts of this page that show what the browser keeps: the address, the appearance and the
// search engine.
function showBrowserData() {
  showRememberedAddress();
  showTheme();
  searchSelect.value = currentEngine().id;
}

// Everything the server saved, from every source; true when it was cleared.
async function clearServer() {
  try {
    const { message } = await api.post("/api/cache/clear");
    setStatus(dataStatus, message, "ok");
    return true;
  } catch (error) {
    setStatus(dataStatus, error.message, "error");
    return false;
  } finally {
    await load();
  }
}

$("#clear-my-picks").addEventListener("click", () => {
  clearInBrowser(clearPicksAndNotes, "Your picks, notes, write-ins and pick rule were removed from this browser.", "There were no picks or notes to clear.");
});

$("#clear-browser-data").addEventListener("click", () => {
  clearInBrowser(clearBrowserData, "Everything Pallot kept in this browser was removed.", "Pallot had nothing saved in this browser.");
});

clearAllButton.addEventListener("click", async () => {
  if (prompts && confirm(prompts.clear_all_confirm)) await clearServer();
});

clearEverythingButton.addEventListener("click", async () => {
  if (!prompts || !confirm(prompts.clear_everything_confirm) || !(await clearServer())) return;
  clearInBrowser(clearBrowserData, "Cleared the source caches and everything Pallot kept in this browser. Undo puts back only this browser's data.",
    "Cleared the source caches. Pallot had nothing saved in this browser.");
});

// Back from the ballot (or another tab), a lookup since may have changed what's saved, and may
// have paused a source, so ask the server again. Another tab may have changed the appearance.
onReturn(() => {
  showTheme();
  load();
});

showTheme();
initSearchEngine();
load();
