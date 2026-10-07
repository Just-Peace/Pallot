// The View settings that shape the ballot, kept with the other view settings (storage.js,
// pallot.ui.v1). A switch the voter hasn't set follows VIEW_DEFAULTS, so a new default only
// changes the ballot of a voter who hasn't chosen. Simple and Detailed each set the switches
// in PRESETS; the mode is never stored, it's read from the switches (Custom when they're mixed).
// Every change fires "pallot:view" on document, and another tab's comes as a storage event.

import { UI, setUiPrefs, uiPref } from "./storage.js";

export const VIEW_DEFAULTS = {
  showMap: false, // the map of your districts, folded at first
  showMoney: false, // each race's money box, folded at first
  showPolls: true, // each race's poll box, open at first
  showEndorsements: true, // the candidates' Endorsements and Scorecards lines
  showFunding: true, // the candidates' Funding line
  collapseOnPick: true, // a race folds to one line once it's picked
  hidePicked: false, // only the races not picked yet
};

// How much of the ballot shows. Simple is the defaults, so a new voter starts there.
export const PRESETS = {
  simple: { showMap: false, showMoney: false, showPolls: true, showEndorsements: true, showFunding: true },
  detailed: { showMap: true, showMoney: true, showPolls: true, showEndorsements: true, showFunding: true },
};
export const MODE_NAMES = { simple: "Simple", detailed: "Detailed", custom: "Custom" };

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
