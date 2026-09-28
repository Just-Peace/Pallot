// The Settings page: the web search engine, sources on/off, refresh or clear what each has
// cached, and deleting this browser's picks. Changes that affect the ballot are marked with
// markSettingsChanged(), so an open ballot page reloads when the voter goes back to it.

import { showRememberedAddress } from "./address.js";
import { api } from "./api.js";
import { h } from "./dom.js";
import { clearAllPicks, markSettingsChanged } from "./picks.js";
import { ENGINES, currentEngine, setEngine } from "./search.js";

const list = document.querySelector("#source-list");
const searchStatus = document.querySelector("#search-status");
const sourcesStatus = document.querySelector("#sources-status");
const picksStatus = document.querySelector("#picks-status");
let pollTimer = null; // re-checks the sources while one is refreshing (the TEC's takes minutes)

function say(status, message, kind = "ok") {
  status.className = `status status-${kind}`;
  status.textContent = message;
}

function sourceRow(source) {
  const resets = source.clear_label.startsWith("Reset"); // sources that come with a bundled snapshot
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

  const paused = source.details.some((f) => f.label === "Paused");
  const name = h("span", { class: "source-name" }, source.label);
  return h(
    "div",
    { class: `source-row${source.enabled ? "" : " is-off"}` },
    h("div", { class: "source-row-head" },
      toggle
        ? h("label", { class: "switch", for: `toggle-${source.id}` }, toggle, name)
        : h("span", { class: "source-name-wrap" }, name, h("span", { class: "pill" }, "Always on"))),
    h("p", { class: "source-desc" }, source.description),
    source.notice ? h("p", { class: `source-notice tone-${source.notice_tone || "info"}` }, source.notice) : null,
    paused ? h("p", { class: "source-warning" }, "Paused after Ballotpedia refused a request; it will try again later.") : null,
    h("div", { class: "source-actions" }, refreshButton, clearButton),
    result,
  );
}

function render(overview) {
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
  const select = document.querySelector("#search-engine");
  const selected = currentEngine().id;
  select.replaceChildren(...ENGINES.map((e) => h("option", { value: e.id, selected: e.id === selected }, e.label)));
  select.addEventListener("change", () => {
    setEngine(select.value);
    markSettingsChanged();
    say(searchStatus, `Web search now uses ${currentEngine().label}.`);
  });
}

document.querySelector("#clear-all").addEventListener("click", async () => {
  if (!confirm("Clear every cache? The next lookups will fetch everything again.")) return;
  try {
    const { message } = await api.post("/api/cache/clear");
    await load();
    say(sourcesStatus, message);
  } catch (error) {
    say(sourcesStatus, error.message, "error");
  }
});

document.querySelector("#clear-my-picks").addEventListener("click", () => {
  if (!confirm("Delete all your picks, notes and remembered address from this browser?")) return;
  clearAllPicks();
  markSettingsChanged();
  showRememberedAddress();
  say(picksStatus, "Your picks, notes and remembered address were removed from this browser.");
});

// Back from the ballot, the browser may show this page as it was left; a lookup since then can
// have paused Ballotpedia, so ask the server again.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) load();
});

initSearchEngine();
load();
