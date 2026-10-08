// The view settings that shape the ballot, kept with the other view settings (storage.js,
// pallot.ui.v1). A switch the voter hasn't set follows VIEW_DEFAULTS, so a new default only
// changes the ballot of a voter who hasn't chosen. Simple and Detailed each set the switches
// in PRESETS; the mode is never stored, it's read from the switches (Custom when they're mixed).
// Every change fires "pallot:view" on document, and another tab's comes as a storage event.

import { h } from "./dom.js";
import { UI, setUiPrefs, uiPref } from "./storage.js";

export const VIEW_DEFAULTS = {
  showMap: false, // the map of your districts, folded at first
  showMoney: false, // each race's money box, folded at first
  showPolls: true, // each race's poll box, open at first
  showEndorsements: true, // the candidates' Endorsements and Ratings lines
  showFunding: true, // the candidates' Funding line
  showSources: false, // where When to vote's dates and Your districts come from, behind a link at first
  collapseOnPick: true, // a race folds to one line once it's picked
  hidePicked: false, // only the races not picked yet
};

// How much of the ballot shows. Simple is the defaults, so a new voter starts there.
export const PRESETS = {
  simple: { showMap: false, showMoney: false, showPolls: true, showEndorsements: true, showFunding: true, showSources: false },
  detailed: { showMap: true, showMoney: true, showPolls: true, showEndorsements: true, showFunding: true, showSources: true },
};

export function viewPref(name) {
  const value = uiPref(name);
  return typeof value === "boolean" ? value : VIEW_DEFAULTS[name];
}

const changed = () => document.dispatchEvent(new Event("pallot:view"));

export function setViewPref(name, value) {
  setUiPrefs({ [name]: Boolean(value) });
  changed();
}

// "simple", "detailed", or "custom" when the switches match neither.
export function viewMode() {
  const matches = (preset) => Object.entries(preset).every(([name, value]) => viewPref(name) === value);
  return Object.keys(PRESETS).find((mode) => matches(PRESETS[mode])) || "custom";
}

// Sets every switch of the mode at once, so another tab never sees half of it.
export function setViewMode(mode) {
  setUiPrefs(PRESETS[mode]);
  changed();
}

// The fine print under When to vote and Your districts, saying where they come from, behind a link
// that opens and closes it; it starts open or closed as showSources says.
export function sourceNote(...children) {
  const note = h("p", { class: "fine", tabindex: "-1" }, ...children);
  const more = h("button", { type: "button", class: "link-btn source-more", "aria-expanded": "false", on: { click: () => {
    const open = note.hidden;
    setSourceNoteOpen(box, open);
    if (open) note.focus();
  } } });
  const box = h("div", { class: "source-note" }, more, note);
  setSourceNoteOpen(box, viewPref("showSources"));
  return box;
}

function setSourceNoteOpen(box, open) {
  const more = box.querySelector(".source-more");
  box.querySelector(".fine").hidden = !open;
  more.setAttribute("aria-expanded", String(open));
  more.textContent = open ? "Hide where these come from" : "Where these come from";
}

// After showSources changes: every note on the page follows it.
export function syncSourceNotes() {
  for (const box of document.querySelectorAll(".source-note")) setSourceNoteOpen(box, viewPref("showSources"));
}

// ``callback`` runs after the view settings change, on this page or in another tab.
export function onViewChange(callback) {
  document.addEventListener("pallot:view", callback);
  addEventListener("storage", (event) => {
    if (event.key === null || event.key === UI) callback();
  });
}

// A page's view controls: Simple and Detailed as radios named "view-mode" (neither checked when
// Custom), and a checkbox per switch, data-view="showMap". showViewControls() sets them from
// the settings and returns the mode; bindViewControls() saves what the voter changes under ``root``.
export function showViewControls(root = document) {
  const mode = viewMode();
  for (const input of root.querySelectorAll('input[name="view-mode"]')) input.checked = input.value === mode;
  for (const input of root.querySelectorAll("input[data-view]")) input.checked = viewPref(input.dataset.view);
  return mode;
}

export function bindViewControls(root) {
  root.addEventListener("change", (event) => {
    const input = event.target;
    if (input.name === "view-mode") setViewMode(input.value);
    else if (input.dataset.view) setViewPref(input.dataset.view, input.checked);
  });
}
