// The endorser bar, "Help me pick", under the progress strip: the voter chooses the endorsers and
// scorecards they trust, each by its source's own name, combined as Any of or All of, and the amber
// marks to avoid. While it shows with something chosen, every race rings who matches (barMarks in
// pick-rules.js: the rule Pick by rule would apply), dims the others in a race with a match and
// outlines the ones to avoid, each row saying why in words; a race's head says "2 match" or "No
// match", and the section chips how many races match. Pick them opens Pick by rule with the bar's
// rule, and More rules… opens it as it was, for party, money and poll rules. The choices stay in
// this browser (loadBar), and another tab follows them.

import { $, h } from "./dom.js";
import { listed, plural } from "./format.js";
import { helpLink } from "./help.js";
import { icon } from "./icons.js";
import { moreAction } from "./more-sheet.js";
import { allRaces, barMarks, barOptions, barRule, loadBar, loadRule, saveBar } from "./pick-rules.js";
import { ENDORSER_BAR } from "./storage.js";
import { showToast } from "./toast.js";
import { onViewChange, setViewPref, viewPref } from "./view.js";

let page = null; // { ballot, picks, loadingCards, openRules }
let onSectionMarks = null; // ballot-nav's section chips: given count(races) of the races with a match, or null
const bar = $("#endorser-bar");
const toggleButton = $("#endorser-btn");
const viewMenu = $("#view-menu");
const summary = h("p", { class: "bar-summary", "aria-live": "polite" });
export const moreEndorsers = moreAction("Help me pick", "ring", () => toggleBar());

// The saved choices among this ballot's chips; one from another ballot stays saved, unused here.
function current(options) {
  const saved = loadBar();
  return {
    ...saved,
    endorsers: saved.endorsers.filter((id) => options.endorsers.some((e) => e.source === id)),
    avoid: saved.avoid.filter((id) => options.avoids.some((a) => a.id === id)),
  };
}

const showing = () => Boolean(page?.ballot) && viewPref("showEndorserBar");

function toggleBar() {
  const on = !viewPref("showEndorserBar");
  setViewPref("showEndorserBar", on);
  if (!on || bar.hidden) return;
  bar.scrollIntoView({ block: "start" });
  bar.querySelector("h2").focus({ preventScroll: true });
}

// Turns a chip's choice on or off in the saved bar.
function choose(kind, id, on) {
  const saved = loadBar();
  saveBar({ ...saved, [kind]: on ? [...saved[kind].filter((x) => x !== id), id] : saved[kind].filter((x) => x !== id) });
}

function clearChoices() {
  const before = loadBar();
  saveBar({ ...before, endorsers: [], avoid: [] });
  showToast("Cleared your endorser choices.", { label: "Undo", run: () => saveBar(before) });
}

// The toolbar's Help me pick and More's row: pressed while the bar shows.
function syncToggle() {
  const on = viewPref("showEndorserBar");
  toggleButton.setAttribute("aria-pressed", String(on));
  moreEndorsers.lastChild.textContent = on ? "Hide Help me pick" : "Help me pick";
}

function chip(key, label, count, pressed, onToggle, { avoid = false, title }) {
  return h("button", {
    type: "button", class: ["rule-chip bar-chip", avoid && "bar-chip-avoid"], "aria-pressed": String(pressed), "data-bar-key": key, title,
    on: { click: () => onToggle(!pressed) },
  }, label, h("span", { class: "rule-count" }, String(count)));
}

function drawBar(choices, options) {
  const focused = bar.contains(document.activeElement) ? document.activeElement.dataset.barKey : null;
  const highlighting = choices.endorsers.length > 0;
  const active = highlighting || choices.avoid.length > 0;
  const close = h("button", { type: "button", class: "icon-btn close", "aria-label": "Hide Help me pick", "data-bar-key": "close",
    on: { click: () => setViewPref("showEndorserBar", false) } }, "✕");
  const mode = options.endorsers.length > 1
    ? h("fieldset", { class: "seg bar-mode" }, h("legend", { class: "sr-only" }, "How several combine"),
      [["any", "Any of"], ["all", "All of"]].map(([value, text]) => h("label", { class: "seg-option" },
        h("input", { type: "radio", name: "bar-mode", value, "data-bar-key": `mode-${value}`, checked: (value === "all") === choices.all,
          on: { change: () => saveBar({ ...loadBar(), all: value === "all" }) } }), text)))
    : null;
  const endorsers = h("div", { class: "bar-row" }, h("span", { class: "bar-label", id: "bar-trust-label" }, "Endorsers you trust"),
    options.endorsers.length
      ? h("div", { class: "rule-chips", role: "group", "aria-labelledby": "bar-trust-label" },
        options.endorsers.map((e) => chip(`e:${e.source}`, e.label, e.count, choices.endorsers.includes(e.source),
          (on) => choose("endorsers", e.source, on), { title: `${e.label} endorses ${plural(e.count, "candidate")} on this ballot` })))
      : h("p", { class: "muted" }, page.loadingCards ? "Loading endorsements…" : "No endorser or scorecard endorses anyone on this ballot."));
  const avoids = options.avoids.length
    ? h("div", { class: "bar-row" }, h("span", { class: "bar-label", id: "bar-avoid-label" }, "Avoid"),
      h("div", { class: "rule-chips", role: "group", "aria-labelledby": "bar-avoid-label" },
        options.avoids.map((a) => chip(`a:${a.id}`, a.label, a.count, choices.avoid.includes(a.id),
          (on) => choose("avoid", a.id, on), { avoid: true, title: `${plural(a.count, "candidate")} on this ballot` }))))
    : null;
  const pickThem = h("button", {
    type: "button", class: "btn primary small", "data-bar-key": "pick", disabled: !active || page.loadingCards,
    title: "Opens Pick by rule set to these choices; nothing is picked until you press Apply",
    on: { click: () => page.openRules({ preset: barRule(choices, loadRule().keepMine) }) },
  }, "Pick them");
  const moreRules = h("button", {
    type: "button", class: "btn ghost small", "data-bar-key": "rules", disabled: page.loadingCards,
    title: "Pick by party, endorsements, money and polls", on: { click: () => page.openRules() },
  }, "More rules…");
  const clear = h("button", { type: "button", class: "btn ghost small", "data-bar-key": "clear", disabled: !active, on: { click: clearChoices } }, "Clear");
  const only = highlighting
    ? h("label", { class: "check" }, h("input", { type: "checkbox", "data-bar-key": "only", checked: choices.onlyMatches,
      on: { change: (event) => saveBar({ ...loadBar(), onlyMatches: event.target.checked }) } }), " Only races with a match")
    : null;
  const allyNote = options.endorsers.some((e) => e.source === "voteforpeace") ? " Vote for Peace counts the candidates it marks Ally." : "";
  bar.replaceChildren(
    h("div", { class: "bar-head" }, h("h2", { id: "endorser-bar-title", tabindex: "-1" }, "Help me pick"),
      helpLink("endorsements", "Help me pick"), mode, close),
    endorsers,
    avoids,
    summary,
    h("div", { class: "bar-actions" }, pickThem, moreRules, clear, only),
    h("p", { class: "fine" }, `Kept in this browser.${allyNote}`),
  );
  if (focused) bar.querySelector(`[data-bar-key="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
}

// A race's head: "2 match" or "No match" (null takes it away).
function markHead(card, text) {
  let tag = card.querySelector(":scope > .race-head > .match-tag");
  if (!text) {
    tag?.remove();
    return;
  }
  if (!tag) {
    tag = h("span", { class: "match-tag" });
    card.querySelector(":scope > .race-head > h3").after(tag);
  }
  tag.textContent = text;
  tag.classList.toggle("none", text === "No match");
}

// A candidate's row: ringed when they match, dimmed when someone else in the race does, outlined
// when to avoid, with a line saying so: "Matches: endorsed by A and B", "To avoid: …".
function markRow(row, marks, dimOthers) {
  const key = row.dataset.cand;
  const match = Boolean(marks?.matches.has(key));
  const reasons = marks?.avoid.get(key);
  const by = marks?.by.get(key);
  row.classList.toggle("bar-match", match);
  row.classList.toggle("bar-dim", dimOthers && !match);
  row.classList.toggle("bar-avoid", Boolean(reasons));
  row.querySelector(":scope > .bar-why")?.remove();
  if (!by && !reasons) return;
  row.querySelector(":scope > .cand-main").after(h("p", { class: "bar-why" },
    by ? h("span", { class: "bar-by" }, icon("ring"), `${match ? "Matches: endorsed" : "Endorsed"} by ${listed(by)}`) : null,
    reasons ? h("span", { class: "bar-avoid-why" }, `To avoid: ${listed(reasons)}`) : null));
}

// Marks every race on the page for ``choices`` (null: the bar is hidden, so nothing is marked).
// Returns how many races have a match, and how many candidates are to avoid.
function markRaces(choices, options) {
  const highlighting = Boolean(choices?.endorsers.length);
  const active = highlighting || Boolean(choices?.avoid.length);
  const labels = new Map((options?.endorsers || []).map((e) => [e.source, e.label]));
  const matched = new Set();
  let avoided = 0;
  for (const race of page?.ballot ? allRaces(page.ballot) : []) {
    const card = document.querySelector(`#result .race[data-race="${CSS.escape(race.key)}"]`);
    if (!card) continue;
    const marks = active ? barMarks(race, choices, labels) : null;
    const hit = highlighting && marks.matches.size > 0;
    if (hit) matched.add(race.key);
    avoided += marks?.avoid.size || 0;
    markHead(card, highlighting ? (hit ? `${marks.matches.size} match` : "No match") : null);
    card.classList.toggle("hidden-nomatch", highlighting && choices.onlyMatches && !hit);
    for (const row of card.querySelectorAll(".cand[data-cand]:not(.write-in)")) markRow(row, marks, hit);
  }
  onSectionMarks?.(highlighting ? (races) => races.filter((r) => matched.has(r.key)).length : null);
  return { matched: matched.size, avoided };
}

// After the ballot, its cards, the bar's choices or the view change: the bar, the races' marks, the
// section chips, and the View menu's dot while Only races with a match hides some.
export function syncEndorserBar() {
  if (!page) return;
  syncToggle();
  const on = showing();
  bar.hidden = !on;
  const options = on ? barOptions(allRaces(page.ballot)) : null;
  const choices = on ? current(options) : null;
  if (on) drawBar(choices, options);
  const { matched, avoided } = markRaces(choices, options);
  const highlighting = Boolean(choices?.endorsers.length);
  const total = page.ballot ? allRaces(page.ballot).length : 0;
  summary.textContent = !choices ? ""
    : highlighting ? `${matched} of ${plural(total, "race")} ${matched === 1 ? "has" : "have"} a match.${avoided ? ` ${plural(avoided, "candidate")} to avoid.` : ""}`
      : choices.avoid.length ? `${plural(avoided, "candidate")} to avoid, outlined.`
        : "Choose any to see who they endorse in every race.";
  viewMenu.classList.toggle("filtered-match", highlighting && choices.onlyMatches);
}

export function initEndorserBar(context, { sectionMarks }) {
  page = context;
  onSectionMarks = sectionMarks;
  toggleButton.addEventListener("click", toggleBar);
  document.addEventListener("pallot:bar", syncEndorserBar);
  addEventListener("storage", (event) => {
    if (event.key === null || event.key === ENDORSER_BAR) syncEndorserBar();
  });
  onViewChange(syncToggle);
  syncToggle();
}
