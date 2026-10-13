// The view settings that shape the ballot, kept with the other view settings (storage.js,
// pallot.ui.v1). A switch the voter hasn't set follows VIEW_DEFAULTS, so a new default only
// changes the ballot of a voter who hasn't chosen. Minimal, Simple and Detailed each set the switches
// in PRESETS; the mode is never stored, it's read from the switches (Custom when they're mixed).
// The voter's focuses (FOCUSES) sit on top: viewPref() is the switch as the ballot uses it, the
// stored one with what each chosen focus turns on, and "Keep it simple" turning off the rest of
// Minimal's. Every change fires "pallot:view" on document, and another tab's comes as a storage event.

import { h } from "./dom.js";
import { UI, setUiPrefs, uiPref } from "./storage.js";

export const VIEW_DEFAULTS = {
  showMap: false, // the map of your districts, folded at first
  showPolls: true, // each race's poll box
  showEndorsements: true, // the candidates' Endorsements line
  showFunding: true, // each race's money box, and the candidates' Funding line
  openBoxes: false, // the money and poll boxes open at first, rather than folded to one line
  showSources: false, // where When to vote's dates and Your districts come from, behind a link at first
  collapseOnPick: true, // a race folds to one line once it's picked
  hidePicked: false, // only the races not picked yet
};

// How much of the ballot shows. Simple is the defaults, so a new voter starts there.
export const PRESETS = {
  minimal: { showMap: false, showPolls: false, showEndorsements: false, showFunding: false, openBoxes: false, showSources: false },
  simple: { showMap: false, showPolls: true, showEndorsements: true, showFunding: true, openBoxes: false, showSources: false },
  detailed: { showMap: true, showPolls: true, showEndorsements: true, showFunding: true, openBoxes: true, showSources: true },
};

// What matters to the voter, any number at once, kept with the view settings ("focuses"): each
// turns on its switches, so what shows is the union of what the chosen ones open. "Keep it simple"
// makes the base Minimal and folds a race on pick, so with others it hides only what none of them
// turns on. Besides the stored switches: openMoney and openPolls open one kind of box (else they
// follow openBoxes), fundingFirst puts the Funding line before Endorsements, compareInHead puts
// Compare funding in the race's head, pollChips a "47% in polls" pill on each polled candidate and
// a mark on the sections with polls, stanceLinks "Profile & issues" and "See where they stand",
// and showEndorserBar the endorser bar. The wording never names an issue or a source.
export const FOCUSES = {
  simple: { label: "Keep it simple", on: ["collapseOnPick"] },
  money: { label: "Follow the money", on: ["showFunding", "openMoney", "fundingFirst", "compareInHead"] },
  endorsements: { label: "Endorsements & scorecards", on: ["showEndorsements", "showEndorserBar"] },
  polls: { label: "Polls", on: ["showPolls", "openPolls", "pollChips"] },
  stances: { label: "Where they stand", on: ["stanceLinks"] },
};
const FOLLOWS = { openMoney: "openBoxes", openPolls: "openBoxes" };
const FOCUS_ONLY = new Set(["fundingFirst", "compareInHead", "pollChips", "stanceLinks", "showEndorserBar"]);

// The chosen focuses, in FOCUSES' order.
export function focuses() {
  const chosen = uiPref("focuses");
  return Array.isArray(chosen) ? Object.keys(FOCUSES).filter((id) => chosen.includes(id)) : [];
}

function storedPref(name) {
  const value = uiPref(name);
  return typeof value === "boolean" ? value : VIEW_DEFAULTS[name];
}

export function viewPref(name) {
  const chosen = focuses();
  if (chosen.some((id) => FOCUSES[id].on.includes(name))) return true;
  if (chosen.includes("simple") && (name in PRESETS.minimal || name in FOLLOWS)) return false;
  if (name in FOLLOWS) return viewPref(FOLLOWS[name]);
  if (FOCUS_ONLY.has(name)) return false;
  return storedPref(name);
}

// The label of the focus that decides a stored switch, which then can't be changed by hand, or null.
export function setByFocus(name) {
  const chosen = focuses();
  const id = chosen.find((f) => FOCUSES[f].on.includes(name)) || (chosen.includes("simple") && name in PRESETS.minimal ? "simple" : null);
  return id ? FOCUSES[id].label : null;
}

// The Details tab the candidate's button opens on: Issues for "Where they stand", the money tab for
// "Follow the money", else Profile.
export function focusTab() {
  const chosen = focuses();
  if (chosen.includes("stances")) return "issues";
  return chosen.includes("money") ? "money" : "profile";
}

const changed = () => document.dispatchEvent(new Event("pallot:view"));

export function setViewPref(name, value) {
  setUiPrefs({ [name]: Boolean(value) });
  changed();
}

// Choosing or dropping a focus also answers the ballot's question (focusAsked).
export function setFocus(id, on) {
  const others = focuses().filter((f) => f !== id);
  setUiPrefs({ focuses: on ? [...others, id] : others, focusAsked: true });
  changed();
}

export const focusAsked = () => uiPref("focusAsked") === true;
export const dismissFocusAsk = () => setUiPrefs({ focusAsked: true });

// "minimal", "simple", "detailed", or "custom" when the stored switches match neither; Minimal
// while "Keep it simple" is chosen, which makes it the base.
export function viewMode() {
  if (focuses().includes("simple")) return "minimal";
  const matches = (preset) => Object.entries(preset).every(([name, value]) => storedPref(name) === value);
  return Object.keys(PRESETS).find((mode) => matches(PRESETS[mode])) || "custom";
}

// Sets every switch of the mode at once, so another tab never sees half of it. A mode above
// Minimal drops "Keep it simple", which would hold the ballot at Minimal.
export function setViewMode(mode) {
  const changes = { ...PRESETS[mode] };
  if (mode !== "minimal" && focuses().includes("simple")) changes.focuses = focuses().filter((id) => id !== "simple");
  setUiPrefs(changes);
  changed();
}

// The focuses as a row of chips, checkboxes named "focus", which show and save the choice wherever
// showViewControls() and bindViewControls() run.
export function focusChips() {
  return h("fieldset", { class: "focus-chips" },
    h("legend", { class: "sr-only" }, "What matters to you"),
    Object.entries(FOCUSES).map(([value, focus]) => h("label", { class: "focus-chip" },
      h("input", { type: "checkbox", name: "focus", value }), focus.label)));
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

// A page's view controls: Minimal, Simple and Detailed as radios named "view-mode" (neither checked when
// Custom), a checkbox per switch, data-view="showMap", and the focus chips. showViewControls() sets
// them from the settings and returns the mode; a switch a focus decides is greyed out, its tooltip
// naming the focus. bindViewControls() saves what the voter changes under ``root``.
export function showViewControls(root = document) {
  const mode = viewMode();
  const chosen = focuses();
  for (const input of root.querySelectorAll('input[name="view-mode"]')) input.checked = input.value === mode;
  for (const input of root.querySelectorAll('input[name="focus"]')) input.checked = chosen.includes(input.value);
  for (const input of root.querySelectorAll("input[data-view]")) {
    const by = setByFocus(input.dataset.view);
    input.checked = viewPref(input.dataset.view);
    input.disabled = Boolean(by);
    const label = input.closest("label");
    if (by) label.title = `Set by your focus: ${by}`;
    else label.removeAttribute("title");
  }
  return mode;
}

export function bindViewControls(root) {
  root.addEventListener("change", (event) => {
    const input = event.target;
    if (input.name === "view-mode") setViewMode(input.value);
    else if (input.name === "focus") setFocus(input.value, input.checked);
    else if (input.dataset.view) setViewPref(input.dataset.view, input.checked);
  });
}
