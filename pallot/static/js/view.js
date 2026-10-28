// The view settings that shape the ballot, kept with the other view settings (storage.js,
// pallot.ui.v1). A switch the voter hasn't set follows VIEW_DEFAULTS, so a new default only
// changes the ballot of a voter who hasn't chosen. Minimal, Simple and Detailed each set the switches
// in PRESETS; the mode is never stored, it's read from the switches (Custom when they're mixed).
// The voter's focuses (FOCUSES) only add: viewPref() is the switch as the ballot uses it, the
// stored one with what each chosen focus turns on. No switch is locked: turning off one a focus
// turns on drops that focus. Every change fires "pallot:view" on document, and another tab's comes
// as a storage event.

import { h } from "./dom.js";
import { UI, setUiPrefs, uiPref } from "./storage.js";

export const VIEW_DEFAULTS = {
  showMap: false, // the map of your districts, folded at first
  showPolls: true, // each race's poll box
  showEndorsements: true, // the candidates' Endorsements line
  showFunding: true, // each race's money box, and the candidates' Funding line
  openBoxes: false, // the money and poll boxes and the Endorsements and Funding lines open at first, rather than folded to one line
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

// Each mode's name, and its hint: what it shows, on hover and to a screen reader (modeChoice).
export const VIEW_MODES = {
  minimal: { label: "Minimal", hint: "Names only" },
  simple: { label: "Simple", hint: "Adds money, polls and endorsements, folded" },
  detailed: { label: "Detailed", hint: "Everything open" },
};

// What matters to the voter, any number at once, kept with the view settings ("focuses"): each
// turns on its switches, so what shows is the mode's with the union of what the chosen ones open.
// Besides the stored switches: openMoney (the money boxes and Funding lines), openPolls and
// openEndorsements open one kind of box or line (else they follow openBoxes), fundingFirst puts
// the Funding line before Endorsements, pollChips a "47% in polls" pill on each polled candidate and a mark on
// the sections with polls, stanceLinks names the candidate's button "Profile & issues", and compareIssues
// puts Compare issues in the race's head. ``hint`` is
// its line in the first lookup's question and in Settings, ``short`` its name in the View menu's summary. The
// wording never names an issue or a source.
export const FOCUSES = {
  money: { label: "Funding", short: "Funding", hint: "Opens the money boxes and Funding chips, and puts Funding first.",
    on: ["showFunding", "openMoney", "fundingFirst"] },
  endorsements: { label: "Endorsements", short: "Endorsements",
    hint: "Shows who endorses each candidate, open.", on: ["showEndorsements", "openEndorsements"] },
  polls: { label: "Polls", short: "Polls", hint: "Opens the poll boxes and shows each candidate's share.",
    on: ["showPolls", "openPolls", "pollChips"] },
  stances: { label: "Where they stand", short: "Stances", hint: "Opens each candidate at their issues, and puts Compare issues in each race.",
    on: ["stanceLinks", "compareIssues"] },
};
const FOLLOWS = { openMoney: "openBoxes", openPolls: "openBoxes", openEndorsements: "openBoxes" };
const FOCUS_ONLY = new Set(["fundingFirst", "compareIssues", "pollChips", "stanceLinks"]);

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
  if (name in FOLLOWS) return viewPref(FOLLOWS[name]);
  if (FOCUS_ONLY.has(name)) return false;
  return storedPref(name);
}

const changed = () => document.dispatchEvent(new Event("pallot:view"));

// Turning off a switch a chosen focus turns on also drops that focus, in the same write, so the
// switch goes off and nothing is ever locked.
export function setViewPref(name, value) {
  const changes = { [name]: Boolean(value) };
  const kept = focuses().filter((id) => !FOCUSES[id].on.includes(name));
  if (!value && kept.length < focuses().length) changes.focuses = kept;
  setUiPrefs(changes);
  changed();
}

export function setFocus(id, on) {
  const others = focuses().filter((f) => f !== id);
  setUiPrefs({ focuses: on ? [...others, id] : others });
  changed();
}

export const focusAsked = () => uiPref("focusAsked") === true;
export const dismissFocusAsk = () => setUiPrefs({ focusAsked: true });

// A browser that chose "Keep it simple", a focus no longer offered, gets what it meant: the Minimal
// mode, with that focus dropped (a race folding on pick is the default). Run by each page before it
// draws its controls, never at import, so the module reads no storage as it loads.
export function migrateView() {
  const chosen = uiPref("focuses");
  if (!Array.isArray(chosen) || !chosen.includes("simple")) return;
  setUiPrefs({ ...PRESETS.minimal, focuses: chosen.filter((id) => id !== "simple"), modeChosen: undefined });
}

// The switches a card's own fold sets (the map's heading): a mode sets them, but opening or folding
// the card isn't a change of the whole view.
const FOLDS = new Set(["showMap"]);

// "minimal", "simple", "detailed", or "custom" when the stored switches match neither, folds aside.
export function viewMode() {
  const matches = (preset) => Object.entries(preset).every(([name, value]) => FOLDS.has(name) || storedPref(name) === value);
  return Object.keys(PRESETS).find((mode) => matches(PRESETS[mode])) || "custom";
}

// Sets every switch of the mode at once, so another tab never sees half of it.
export function setViewMode(mode) {
  setUiPrefs(PRESETS[mode]);
  changed();
}

// The focuses as checkboxes named "focus", which show and save the choice wherever
// showViewControls() and bindViewControls() run: a row of chips, or with ``hints`` a card each
// holding the focus's hint.
export function focusChips({ hints = false } = {}) {
  return h("fieldset", { class: ["focus-chips", hints && "focus-options"] },
    h("legend", { class: "sr-only" }, "What matters to you"),
    Object.entries(FOCUSES).map(([value, focus]) => (hints
      ? h("label", { class: "focus-option" }, h("input", { type: "checkbox", name: "focus", value }),
        h("span", { class: "focus-option-text" }, h("span", { class: "focus-option-label" }, focus.label),
          h("span", { class: "focus-option-hint" }, focus.hint)))
      : h("label", { class: "focus-chip" }, h("input", { type: "checkbox", name: "focus", value }), focus.label))));
}

// Minimal, Simple and Detailed as radios named "view-mode", each with its hint as a title: on the
// label for the pointer, on the radio for its accessible description.
export function modeChoice() {
  return h("fieldset", { class: "seg" }, h("legend", { class: "sr-only" }, "How much detail"),
    Object.entries(VIEW_MODES).map(([value, { label, hint }]) => h("label", { class: "seg-option", title: hint },
      h("input", { type: "radio", name: "view-mode", value, title: hint }), label)));
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
// them from the settings and returns the mode; a switch shows as the ballot uses it, a focus's
// included. bindViewControls() saves what the voter changes under ``root``.
export function showViewControls(root = document) {
  const mode = viewMode();
  const chosen = focuses();
  for (const input of root.querySelectorAll('input[name="view-mode"]')) input.checked = input.value === mode;
  for (const input of root.querySelectorAll('input[name="focus"]')) input.checked = chosen.includes(input.value);
  for (const input of root.querySelectorAll("input[data-view]")) input.checked = viewPref(input.dataset.view);
  return mode;
}

// Any change here answers "What matters to you?" (focusAsked).
export function bindViewControls(root) {
  root.addEventListener("change", (event) => {
    const input = event.target;
    if (input.name === "view-mode" || input.name === "focus" || input.dataset.view) dismissFocusAsk();
    if (input.name === "view-mode") setViewMode(input.value);
    else if (input.name === "focus") setFocus(input.value, input.checked);
    else if (input.dataset.view) setViewPref(input.dataset.view, input.checked);
  });
}
