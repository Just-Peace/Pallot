// Settings, in the left pane: turn sources on/off and refresh or clear what each has cached.

import { api } from "./api.js";
import { h } from "./dom.js";
import { clearAllPicks, loadUi, saveUi } from "./picks.js";
import { ENGINES, currentEngine, setEngine } from "./search.js";

const panel = document.querySelector("#settings");
const list = document.querySelector("#source-list");
const status = document.querySelector("#settings-status");
let hooks = {};

function say(message, kind = "ok") {
  status.className = `status status-${kind}`;
  status.textContent = message;
}

function sourceRow(source) {
  const result = h("p", { class: "action-result", "aria-live": "polite" });
  const refreshButton = h("button", {
    class: "icon-btn", type: "button", title: source.refresh_label,
    "aria-label": `${source.refresh_label}: ${source.label}`, disabled: source.busy,
  }, source.busy ? "Refreshing…" : "↻ Refresh");
  const clearButton = h("button", {
    class: "icon-btn", type: "button", title: source.clear_label,
    "aria-label": `${source.clear_label}: ${source.label}`, disabled: source.busy,
  }, source.id === "trackaipac" ? "Reset" : "Clear");
  const toggle = source.toggleable
    ? h("input", { type: "checkbox", role: "switch", id: `toggle-${source.id}`, checked: source.enabled, disabled: source.busy })
    : null;

  toggle?.addEventListener("change", async () => {
    toggle.disabled = true;
    try {
      render(await api.put(`/api/sources/${source.id}`, { enabled: toggle.checked }));
      say(`${source.label} turned ${toggle.checked ? "on" : "off"}.`);
      hooks.onSourcesChanged?.();
    } catch (error) {
      toggle.checked = !toggle.checked;
      toggle.disabled = false;
      say(error.message, "error");
    }
  });

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    clearButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
    result.textContent = "";
    try {
      const { message } = await api.post(`/api/sources/${source.id}/refresh`);
      await load();
      say(`${source.label}: ${message}`);
      hooks.onSourcesChanged?.();
    } catch (error) {
      refreshButton.disabled = false;
      clearButton.disabled = false;
      refreshButton.textContent = "↻ Refresh";
      result.textContent = error.message;
    }
  });

  clearButton.addEventListener("click", async () => {
    const question = source.id === "trackaipac"
      ? "Throw away refreshed TrackAIPAC data and go back to the bundled snapshot?"
      : `Clear everything cached from ${source.label}? The next lookup will fetch it again.`;
    if (!confirm(question)) return;
    try {
      const { message } = await api.post(`/api/sources/${source.id}/clear`);
      await load();
      say(`${source.label}: ${message}`);
    } catch (error) {
      say(error.message, "error");
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
    paused ? h("p", { class: "source-warning" }, "Paused after Ballotpedia refused a request; it will try again later.") : null,
    h("div", { class: "source-actions" }, refreshButton, clearButton),
    result,
  );
}

function render(overview) {
  list.replaceChildren(...overview.sources.map(sourceRow));
}

async function load() {
  try {
    render(await api.get("/api/sources"));
  } catch (error) {
    say(error.message, "error");
  }
}

function initSearchEngine() {
  const select = document.querySelector("#search-engine");
  const selected = currentEngine().id;
  select.replaceChildren(...ENGINES.map((e) => h("option", { value: e.id, selected: e.id === selected }, e.label)));
  select.addEventListener("change", () => {
    setEngine(select.value);
    say(`Web search now uses ${currentEngine().label}.`);
    hooks.onSearchEngineChanged?.();
  });
}

// hooks.onSearchEngineChanged(): the web search engine was changed.
// hooks.onSourcesChanged(): a source was turned on/off or refreshed.
// hooks.onPicksCleared(): the browser's picks and notes were deleted.
export function initSettings(callbacks) {
  hooks = callbacks;
  initSearchEngine();
  panel.addEventListener("toggle", () => {
    saveUi({ ...loadUi(), settingsOpen: panel.open });
    if (panel.open) load();
  });
  panel.open = Boolean(loadUi().settingsOpen); // fires "toggle" (and loads) when it opens

  document.querySelector("#clear-all").addEventListener("click", async () => {
    if (!confirm("Clear every cache? The next lookups will fetch everything again.")) return;
    try {
      const { message } = await api.post("/api/cache/clear");
      await load();
      say(message);
    } catch (error) {
      say(error.message, "error");
    }
  });

  document.querySelector("#clear-my-picks").addEventListener("click", () => {
    if (!confirm("Delete all your picks, notes and remembered address from this browser?")) return;
    clearAllPicks();
    say("Your picks, notes and remembered address were removed from this browser.");
    hooks.onPicksCleared?.();
  });
}
