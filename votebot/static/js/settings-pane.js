// Settings, in the left pane: turn sources on/off and refresh or clear what each has cached.

import { api } from "./api.js";
import { formatBytes, h, relativeTime } from "./dom.js";
import { clearAllPicks, loadUi, saveUi } from "./picks.js";

const panel = document.querySelector("#settings");
const list = document.querySelector("#source-list");
const totalSize = document.querySelector("#total-size");
const status = document.querySelector("#settings-status");
let hooks = {};

function say(message, kind = "ok") {
  status.className = `status status-${kind}`;
  status.textContent = message;
}

// The server reports times in UTC ISO form; show them in the viewer's local time.
function localTimes(text) {
  return text.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})/g, (iso) => {
    const date = new Date(iso);
    return Number.isNaN(date.getTime())
      ? iso
      : `${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} (${relativeTime(iso)})`;
  });
}

function stats(source) {
  if (source.id === "trackaipac") return null; // its details say what it holds
  const { cache } = source;
  const parts = [`${cache.entries} cached`, formatBytes(cache.bytes)];
  if (cache.newest) parts.push(`updated ${relativeTime(cache.newest)}`);
  if (cache.expired) parts.push(`${cache.expired} due for refresh`);
  return h("p", { class: "source-stats" }, parts.join(" · "));
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

  const name = h("span", { class: "source-name" }, source.label);
  return h(
    "div",
    { class: `source-row${source.enabled ? "" : " is-off"}` },
    h("div", { class: "source-row-head" },
      toggle
        ? h("label", { class: "switch", for: `toggle-${source.id}` }, toggle, name)
        : h("span", { class: "source-name-wrap" }, name, h("span", { class: "pill" }, "Always on"))),
    h("p", { class: "source-desc" }, source.description),
    stats(source),
    source.details.length
      ? h("dl", { class: "mini-facts" }, source.details.map((f) => [h("dt", {}, f.label), h("dd", {}, localTimes(f.value))]))
      : null,
    h("div", { class: "source-actions" }, refreshButton, clearButton),
    result,
  );
}

function render(overview) {
  totalSize.textContent = `${formatBytes(overview.total_bytes)} cached on this computer. Repeat lookups don't contact these sites again.`;
  list.replaceChildren(...overview.sources.map(sourceRow));
}

async function load() {
  try {
    render(await api.get("/api/sources"));
  } catch (error) {
    say(error.message, "error");
  }
}

// hooks.onSourcesChanged(): a source was turned on/off or refreshed.
// hooks.onPicksCleared(): the browser's picks and notes were deleted.
export function initSettings(callbacks) {
  hooks = callbacks;
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
