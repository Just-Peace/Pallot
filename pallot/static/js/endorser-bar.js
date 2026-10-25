// Help me pick, a drop-down in the toolbar beside View, with the same controls in More on a phone:
// under Trust, the endorsers and scorecards the voter trusts, each by its source's own name; under
// Avoid, the amber watchlists, and the voter's own Avoid list (ban-list.js), always avoided, as a chip
// linking to it in Settings. Choosing an endorser picks at once, with Undo, in each race it endorses
// someone in: who any chosen endorser endorses (barMarks in pick-rules.js), never anyone avoided,
// unless they outnumber the seats or the voter picked there by hand. Dropping one takes back the
// picks the endorsers made (picks.auto) that none still chosen endorses. An Avoid chip only outlines.
// While anything is chosen, every race rings who matches, dims the others in a race with a match and
// outlines the ones to avoid, each row saying why in words; a race's head says "2 match" or "No
// match", and the section chips how many races match. More conditions… opens the rule's dialog
// (pick-rule-dialog.js), whose choices these are too, kept in its saved rule in this browser
// (loadBar), and another tab follows them.

import { raceFilled } from "./ballot-shared.js";
import { $, h } from "./dom.js";
import { listed, plural } from "./format.js";
import { helpLink } from "./help.js";
import { icon } from "./icons.js";
import { moreAction } from "./more-sheet.js";
import { syncRuleBanner } from "./pick-rule-dialog.js";
import { allRaces, barMarks, barOptions, endorserPlan, loadBar, saveBar } from "./pick-rules.js";
import { PICK_RULE } from "./storage.js";
import { showToast } from "./toast.js";
import { viewPref } from "./view.js";

let page = null; // { ballot, picks, loadingCards, openRules, renderRaces }
let onSectionMarks = null; // ballot-nav's section chips: given count(races) of the races with a match, or null
const menu = $("#help-menu");
const menuLabel = $("#help-summary");
const panel = $("#help-panel");
const sheet = $("#more-sheet");
export const moreHelp = h("div", { class: "sheet-help" }); // More's copy, in its own section (ballot-nav.js)

// The saved choices among this ballot's chips; one from another ballot stays saved, unused here.
function current(options) {
  const saved = loadBar();
  return {
    ...saved,
    endorsers: saved.endorsers.filter((id) => options.endorsers.some((e) => e.source === id)),
    avoid: saved.avoid.filter((id) => options.avoids.some((a) => a.id === id)),
  };
}

// Saves the choices into the rule, then redraws the controls and the marks; the rule's banner goes,
// as the rule changed.
function save(bar) {
  saveBar(bar);
  syncRuleBanner();
  syncEndorserBar();
}

// Saves ``bar``, the choices with an endorser chosen (``added``) or dropped, and changes the picks as
// endorserPlan() says, with Undo for both. With "Collapse a race when I pick" on, a race it fills
// folds, as More conditions' does; Undo opens it again. ``words(result)``: the toast.
function changeEndorsers(bar, { added = null, words }) {
  const before = loadBar();
  const result = endorserPlan(page.ballot ? allRaces(page.ballot) : [], bar, page.picks, added);
  const { rows } = result;
  const folded = viewPref("collapseOnPick")
    ? rows.filter((row) => row.outcome === "pick" && raceFilled(row.race, row.after) && !page.picks.isCollapsed(row.race.key))
      .map((row) => row.race.key)
    : [];
  const changed = rows.length
    ? page.picks.setMany(Object.fromEntries(rows.map((row) => [row.race.key, row.after])),
      Object.fromEntries(rows.map((row) => [row.race.key, row.auto])))
    : null;
  if (folded.length) page.picks.setCollapsed(folded, true);
  save(bar);
  if (changed) page.renderRaces();
  const undo = () => {
    if (changed) page.picks.setMany(changed.picks, changed.auto);
    if (folded.length) page.picks.setCollapsed(folded, false);
    save(before);
    if (changed) page.renderRaces();
  };
  showToast(words(result), { label: "Undo", run: undo });
}

function pickedWords(label, { picked, kept, many }) {
  return [
    picked ? `Picked ${label}'s candidates in ${plural(picked, "race")}.` : `Ringed ${label}'s candidates; nothing to pick.`,
    kept ? `Kept your own picks in ${plural(kept, "race")}.` : null,
    many ? `Left ${plural(many, "race")} with more matches than seats for you.` : null,
  ].filter(Boolean).join(" ");
}

const droppedWords = (label, { takenBack }) =>
  (takenBack ? `Took back ${plural(takenBack, "pick")} ${label} made.` : `Dropped ${label}.`);

// Turns a chip's choice on or off: an endorser picks or takes back, an amber mark only outlines.
function choose(kind, id, on, label) {
  const saved = loadBar();
  const others = saved[kind].filter((x) => x !== id);
  const bar = { ...saved, [kind]: on ? [...others, id] : others };
  if (kind === "avoid") save(bar);
  else changeEndorsers(bar, { added: on ? id : null, words: (result) => (on ? pickedWords(label, result) : droppedWords(label, result)) });
}

// A candidate's endorsement chip's menu (source-cards.js): chooses its endorser or amber mark.
export function chooseInHelp({ kind, id, label }) {
  if (loadBar()[kind].includes(id)) {
    showToast(`${label} is already chosen in Help me pick.`);
    return;
  }
  choose(kind, id, true, label);
  if (kind === "avoid") showToast(`Outlining everyone marked “${label}”.`, { label: "Undo", run: () => choose(kind, id, false, label) });
}

function clearChoices() {
  const saved = loadBar();
  changeEndorsers({ ...saved, endorsers: [], avoid: [] }, {
    words: ({ takenBack }) => (takenBack ? `Cleared Help me pick, and took back ${plural(takenBack, "pick")} its endorsers made.`
      : "Cleared Help me pick."),
  });
}

function chip(key, label, count, pressed, onToggle, { avoid = false, title }) {
  return h("button", {
    type: "button", class: ["rule-chip", avoid && "bar-chip-avoid"], "aria-pressed": String(pressed), "data-bar-key": key, title,
    on: { click: () => onToggle(!pressed) },
  }, label, h("span", { class: "rule-count" }, String(count)));
}

// Draws the controls in ``root``: the drop-down's panel, or More's copy (``inSheet``), where choosing
// an endorser, Clear and More conditions… close the sheet, so the ballot and the toast's Undo show.
function drawControls(root, choices, options, summary, inSheet) {
  const focused = root.contains(document.activeElement) ? document.activeElement.dataset.barKey : null;
  const id = inSheet ? "more-help" : "help";
  const highlighting = choices.endorsers.length > 0;
  const active = highlighting || choices.avoid.length > 0;
  const done = () => (inSheet ? sheet.close() : null);
  const group = (label, labelId, ...children) =>
    h("div", { class: "menu-group" }, h("p", { class: "menu-label", id: labelId }, label), children);
  const allyNote = options.endorsers.some((e) => e.source === "voteforpeace") ? " Vote for Peace counts the candidates it marks Ally." : "";
  const intro = h("p", { class: "fine help-intro" }, "Trust picks who they endorse. Avoid only marks; nothing is picked or taken back.");
  const trust = group("Trust", `${id}-trust`,
    options.endorsers.length
      ? h("div", { class: "rule-chips", role: "group", "aria-labelledby": `${id}-trust` },
        options.endorsers.map((e) => chip(`e:${e.source}`, e.label, e.count, choices.endorsers.includes(e.source), (on) => {
          done();
          choose("endorsers", e.source, on, e.label);
        }, { title: `${e.label} endorses ${plural(e.count, "candidate")} on this ballot` })))
      : h("p", { class: "muted" }, page.loadingCards ? "Loading endorsements…" : "No endorser or scorecard endorses anyone on this ballot."),
    options.endorsers.length
      ? h("p", { class: "fine" }, `Your own picks stay.${allyNote}`)
      : null);
  // The voter's own list is always avoided, so its chip isn't a choice: it links to the list in Settings.
  const own = options.own
    ? h("a", { class: "rule-chip bar-chip-own", href: "settings.html#ban-title", "data-bar-key": "own",
      title: `${plural(options.own, "candidate")} on this ballot. Trust never picks them. Change the list in Settings.` },
    icon("ban"), "People I've marked", h("span", { class: "rule-count" }, String(options.own)))
    : null;
  const avoids = group("Avoid", `${id}-avoid`,
    options.avoids.length || own
      ? h("div", { class: "rule-chips", role: "group", "aria-labelledby": `${id}-avoid` },
        options.avoids.map((a) => chip(`a:${a.id}`, a.label, a.count, choices.avoid.includes(a.id),
          (on) => choose("avoid", a.id, on, a.label), { avoid: true, title: `${plural(a.count, "candidate")} on this ballot` })),
        own)
      : null,
    h("p", { class: "fine" }, "Trust never picks who you avoid. Avoid on a candidate adds them to your own list."));
  const only = highlighting
    ? h("label", { class: "check" }, h("input", { type: "checkbox", "data-bar-key": "only", checked: choices.onlyMatches,
      on: { change: (event) => save({ ...loadBar(), onlyMatches: event.target.checked }) } }), " Only races with a match")
    : null;
  const status = h("div", { class: "menu-group" }, h("p", { class: "help-summary", "aria-live": "polite" }, summary), only);
  const rulesTitle = page.loadingCards ? "Waits for money, polls and endorsements"
    : "Pick by party, money, polls or incumbents, in every race or one";
  const openRules = () => {
    menu.open = false;
    page.openRules();
  };
  const moreRules = inSheet
    ? moreAction("More conditions…", "filter", openRules, { "data-bar-key": "rules", disabled: page.loadingCards, title: rulesTitle })
    : h("button", { type: "button", class: "btn ghost small with-icon", "data-bar-key": "rules", disabled: page.loadingCards,
      title: rulesTitle, on: { click: openRules } }, icon("filter"), "More conditions…");
  const clear = h("button", { type: "button", class: "btn ghost small", "data-bar-key": "clear", disabled: !active,
    title: "Clears these choices and takes back the picks the endorsers made", on: { click: () => {
      done();
      clearChoices();
    } } }, inSheet ? "Clear choices" : "Clear");
  root.replaceChildren(...[
    intro,
    trust,
    avoids,
    status,
    inSheet ? h("div", { class: "sheet-help-foot" }, clear, moreRules)
      : h("div", { class: "menu-foot" }, moreRules, clear, helpLink("endorsements", "Help me pick")),
  ].filter(Boolean));
  if (focused) root.querySelector(`[data-bar-key="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
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

// Marks every race on the page for ``choices`` (null, or nothing chosen: nothing is marked).
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

// After the ballot, its cards or the choices change: the drop-down and More's copy, its count
// ("Help me pick · 2"), the races' marks, the section chips, and the drop-down's dot while Only races
// with a match hides some.
export function syncEndorserBar() {
  if (!page) return;
  const options = page.ballot ? barOptions(allRaces(page.ballot)) : null;
  const choices = options ? current(options) : null;
  const chosen = choices ? choices.endorsers.length + choices.avoid.length : 0;
  menuLabel.textContent = chosen ? `Help me pick · ${chosen}` : "Help me pick";
  const { matched, avoided } = markRaces(choices, options);
  const highlighting = Boolean(choices?.endorsers.length);
  menu.classList.toggle("filtered", highlighting && choices.onlyMatches);
  if (!choices) return;
  const total = allRaces(page.ballot).length;
  const summary = highlighting
    ? `${matched} of ${plural(total, "race")} ${matched === 1 ? "has" : "have"} a match.${avoided ? ` ${plural(avoided, "candidate")} to avoid.` : ""}`
    : choices.avoid.length ? `${plural(avoided, "candidate")} to avoid, outlined.`
      : "Choose who you trust, or who to avoid.";
  drawControls(panel, choices, options, summary, false);
  drawControls(moreHelp, choices, options, summary, true);
}

export function initEndorserBar(context, { sectionMarks }) {
  page = context;
  onSectionMarks = sectionMarks;
  addEventListener("storage", (event) => {
    if (event.key === null || event.key === PICK_RULE) syncEndorserBar();
  });
}
