// Getting around the ballot: the progress strip and Next, the left pane's list of sections (and
// which one is on screen), the View menu, the "What matters to you?" card, j and k, where the
// strip's parts go on a phone, with the race on screen, More and the chips that make way while
// scrolling down, and the first-run tips.

import { ballotSections, measureKey } from "./ballot-shared.js";
import { isPaneCollapsed, narrow, onPaneToggle } from "./chrome.js";
import { $, h, onFrame, onReturn, stepText, trackHeight } from "./dom.js";
import { plural } from "./format.js";
import { syncMapShown } from "./district-map.js";
import { initEndorserBar, moreEndorsers, syncEndorserBar } from "./endorser-bar.js";
import { helpLink, showTip } from "./help.js";
import { icon } from "./icons.js";
import { addMoreSection, initMoreSheet, moreAction } from "./more-sheet.js";
import { STILL_LOADING, cardFor, redrawRace, refillCards, setAllCollapsed } from "./race-cards.js";
import { hasPolls, syncBoxes, syncFunding, syncLines } from "./source-cards.js";
import {
  FOCUSES, bindViewControls, dismissFocusAsk, focusAsked, focusChips, focuses, migrateView, onViewChange, setViewPref, showViewControls,
  syncSourceNotes, viewPref,
} from "./view.js";

let page = null; // { ballot, picks }
const result = $("#result");
const strip = $("#progress-strip");
const tools = $("#ballot-tools");
const viewControls = $("#view-controls");
const viewMenu = $("#view-menu");
const viewSummary = $("#view-summary");
const focusAsk = $("#focus-ask");
const nextButton = $("#next-race");
const jump = $("#jump");
const jumpList = $("#jump-list");
const stripRace = $("#strip-race");
const VIEW_MODES = [["minimal", "Minimal"], ["simple", "Simple"], ["detailed", "Detailed"]];
const moreCaption = h("p", { class: "fine mode-caption", id: "more-mode-caption" }, $("#mode-caption").textContent);
const moreView = h("fieldset", { class: "seg", "aria-describedby": "more-mode-caption" }, h("legend", { class: "sr-only" }, "How much detail"),
  VIEW_MODES.map(([value, label]) => h("label", { class: "seg-option" }, h("input", { type: "radio", name: "view-mode", value }), label)));
const moreFocus = focusChips();
const morePrint = moreAction("Print my picks", "printer", () => $("#print-btn").click());
const waitNotes = [$("#wait-note"), h("p", { class: "fine wait-note", hidden: true }, $("#wait-note").textContent)];
const progressInfo = strip.querySelector(".progress-info");
const coarse = matchMedia("(pointer: coarse)");
const SCROLL_GAP = 12; // what a jump leaves between the strip and the section it scrolls to
// The rows' and race heads' parts a focus adds, built again in place.
const refill = () => {
  if (page.ballot) refillCards();
};
// What puts the ballot back to each view switch when it changes, without a reload; each runs once
// however many of its switches changed.
const APPLY = {
  showEndorserBar: syncEndorserBar,
  showMap: syncMapShown,
  showPolls: () => syncBoxes("showPolls"),
  showEndorsements: syncLines,
  openEndorsements: syncLines,
  showFunding: () => {
    syncBoxes("showFunding");
    syncFunding();
  },
  openMoney: () => syncBoxes("openMoney"),
  openPolls: () => syncBoxes("openPolls"),
  showSources: syncSourceNotes,
  hidePicked: () => {
    if (!page.ballot) return;
    applyHidePicked();
    markCurrentSection(); // the marked section may have gone
  },
  fundingFirst: refill,
  compareInHead: refill,
  pollChips: [refill, syncPollMarks],
  stanceLinks: refill,
};
let applied = {}; // the view switches as the page last applied them

let sectionCounts = []; // the left pane's section list: [{ element, keys, maybe, races, mark, matchMark }]
let sectionLinks = []; // and its links: [{ id, link }], the section's id and the link to it
let currentSection = null; // the id of the section marked as the one on screen
let lastJumped = null; // the race "Next race to pick" went to last

const showPickedButton = h("button", { type: "button", class: "link-btn", on: { click: () => setViewPref("hidePicked", false) } }, "Show them");
export const hidingNote = h("p", { class: "notice", hidden: true }, "Races you've picked are hidden. ", showPickedButton);

// The left pane's list of sections, each with how many of its races are picked, with the
// pollChips switch a mark on those with polls, and with the endorser bar how many races match.
export function renderSections() {
  sectionCounts = [];
  sectionLinks = [];
  currentSection = null;
  const items = [];
  const add = (id, label, keys, races = [], maybe = false) => {
    const count = h("span", { class: "count" });
    const mark = h("span", { class: "poll-mark", title: "Has polls", hidden: true }, icon("bars"), h("span", { class: "sr-only" }, " (has polls)"));
    const matchMark = h("span", { class: "match-mark", hidden: true });
    const link = h("a", { href: `#${id}`, class: maybe ? "maybe-link" : null }, h("span", {}, label, mark, matchMark), count);
    sectionCounts.push({ element: count, keys, maybe, races, mark, matchMark });
    sectionLinks.push({ id, link });
    items.push(h("li", {}, link));
  };
  for (const section of ballotSections(page.ballot)) add(section.id, section.title, section.races.map((r) => r.key), section.races, section.maybe);
  if (page.ballot.measures.length) add("measures-section", "Propositions", page.ballot.measures.map(measureKey));
  jumpList.replaceChildren(...items);
  jump.hidden = !items.length;
  syncPollMarks();
  syncChipFades();
}

// The sections' poll marks, after the pollChips switch changes or the cards come.
export function syncPollMarks() {
  const on = viewPref("pollChips");
  for (const { races, mark } of sectionCounts) mark.hidden = !(on && races.some(hasPolls));
}

// The sections' match counts from the endorser bar: ``count(races)``, the races with a match, or
// null while it highlights nothing.
function syncMatchMarks(count) {
  for (const { races, matchMark } of sectionCounts) {
    const n = count ? count(races) : 0;
    matchMark.hidden = !n;
    matchMark.title = n ? `${plural(n, "race")} with a match` : "";
    matchMark.replaceChildren(...(n ? [icon("ring"), String(n), h("span", { class: "sr-only" }, ` (${plural(n, "race")} with a match)`)] : []));
  }
}

// "5 of 12 races · 1 of 2 propositions", one bar for both, and the section counts. The races
// that may not be on the ballot aren't counted.
export function updateProgress() {
  const { ballot, picks } = page;
  const raceKeys = ballot.races.map((r) => r.key);
  const measureKeys = ballot.measures.map(measureKey);
  const done = picks.countPicked(raceKeys);
  const decided = picks.countPicked(measureKeys);
  $("#progress").textContent = [
    `${done} of ${plural(raceKeys.length, "race")}`,
    measureKeys.length ? `${decided} of ${plural(measureKeys.length, "proposition")}` : null,
  ].filter(Boolean).join(" · ");
  const total = raceKeys.length + measureKeys.length;
  $("#progress-bar").style.width = `${total ? Math.round(((done + decided) / total) * 100) : 0}%`;
  const left = done + decided < total;
  nextButton.disabled = !left;
  nextButton.textContent = left ? "Next race to pick" : "All picked ✓";
  for (const { element, keys, maybe } of sectionCounts) {
    const picked = picks.countPicked(keys);
    element.textContent = maybe ? (picked ? `${picked} picked` : String(keys.length)) : `${picked}/${keys.length}`;
    element.classList.toggle("complete", !maybe && picked === keys.length);
  }
  syncChipFades();
  maybeTip();
}

// While the cards are coming, the strip's bar says so, its words changing as the wait goes on, and
// Print, which needs them, waits, in the toolbar and in More, a line under it saying why (the endorser
// bar's Pick them and More rules… wait too). ``failed``: they won't come, so the bar goes but they
// stay off.
const needCards = [$("#print-btn"), morePrint].map((button) => ({ button, title: button.title }));
const cardsLoading = $("#cards-loading");
const CARDS_STEPS = [
  [0, "Loading money, polls and endorsements…"],
  [4000, "Still gathering money, polls and endorsements…"],
  [10000, "A first lookup takes up to a minute; later ones are instant."],
];
let stopCardsSteps = null;

export function setCardsLoading(waiting, { failed = false } = {}) {
  const shown = waiting && !failed;
  stopCardsSteps?.();
  stopCardsSteps = shown ? stepText(cardsLoading.querySelector("span"), CARDS_STEPS) : null;
  cardsLoading.hidden = !shown;
  for (const { button, title } of needCards) {
    button.disabled = waiting;
    button.title = waiting ? STILL_LOADING : title;
  }
  for (const note of waitNotes) note.hidden = !waiting;
  maybeTip();
}

// ---- first-run tips (help.js) ---------------------------------------------------------

// Each points at what it's about, and shows only for a voter whose focus it concerns (all of them
// without a focus): no money tip for a voter who chose only Polls.
const wants = (focus) => !focuses().length || focuses().includes(focus);
const anyPicked = () => [...page.ballot.races.map((r) => r.key), ...page.ballot.measures.map(measureKey)].some((key) => page.picks.has(key));
const TIPS = [
  {
    id: "funding", when: () => viewPref("showFunding") && wants("money"),
    target: () => [...result.querySelectorAll(".funding-line .badge-open")], after: (chip) => chip.closest(".funding-line"),
    text: () => `${coarse.matches ? "Tap" : "Click"} a Funding chip to see who gave.`,
  },
  {
    id: "profile", when: () => wants("stances"),
    target: () => [...result.querySelectorAll(".profile-btn:not(:disabled)")], after: (button) => button.closest(".cand-main"),
    text: () => `${viewPref("stanceLinks") ? "Profile & issues" : "Profile"} shows where each candidate stands, issue by issue.`,
  },
  {
    id: "rule", when: () => wants("endorsements"), target: () => $("#endorser-btn"), after: () => tools,
    text: () => "Help me pick rings who the endorsers you trust endorse, and can pick them for you.",
  },
  {
    id: "next", when: () => anyPicked() && !nextButton.disabled, target: () => nextButton, after: () => progressInfo,
    text: () => (coarse.matches ? "Next race jumps to the next one you haven't picked."
      : "Next race jumps to one you haven't picked; j and k step too."),
  },
  {
    id: "print", when: anyPicked, target: () => $(narrow.matches ? "#more-btn" : "#print-btn"),
    after: () => (narrow.matches ? progressInfo : tools),
    text: () => (narrow.matches ? "Print your picks from More: phones can't be used at Texas voting stations."
      : "Print your picks: phones can't be used at the voting station in Texas."),
  },
];

// A tip, once the ballot and its cards are in, with nothing over them: not while "What matters to
// you?" asks, nor with a dialog open. It runs again after "Got it" and as the voter scrolls, so the
// next tip shows once what it's about is in the window.
function maybeTip() {
  if (!page?.ballot || page.loadingCards || result.hidden || !focusAsk.hidden || document.querySelector("dialog[open]")) return;
  showTip(TIPS, maybeTip);
}

// ---- view: detail and focus, collapse, only unpicked races, next race, j/k ------------

// The View menu's button: "View · Simple", "View · Simple · Funding", "View · Simple · 2 focuses",
// "View · Custom" while the switches are mixed.
function viewLabel(mode) {
  const chosen = focuses();
  const detail = VIEW_MODES.find(([value]) => value === mode)?.[1] || "Custom";
  const focus = chosen.length > 1 ? `${chosen.length} focuses` : chosen.length ? FOCUSES[chosen[0]].short : null;
  return ["View", detail, focus].filter(Boolean).join(" · ");
}

// After any change of the view settings, here or in another tab: the View menu, More's View and the
// question's card show them, and each switch that changed applies to the ballot in place, putting
// back what the voter opened or folded by hand. The page carries the mode (data-view-mode), so a
// phone's candidate rows stay whole in Detailed.
function applyView() {
  const mode = showViewControls(viewControls);
  document.documentElement.dataset.viewMode = mode;
  for (const root of [moreView, moreFocus, focusAsk]) showViewControls(root);
  viewSummary.textContent = viewLabel(mode);
  const runs = new Set();
  for (const [name, apply] of Object.entries(APPLY)) {
    const value = viewPref(name);
    if (name in applied && applied[name] !== value) [apply].flat().forEach((run) => runs.add(run));
    applied[name] = value;
  }
  runs.forEach((run) => run());
  maybeTip();
}

// "What matters to you?": a card at the top of the ballot, right under the strip, so nothing above it
// moves as the ballot changes under it. It shows after a ballot is drawn, until the voter chooses a
// focus or closes it. Its focuses and detail change the ballot at once; it stays until Done or ✕,
// which leave the choice under View.
export function askFocus() {
  focusAsk.hidden = focusAsked();
}

function initFocusAsk() {
  focusAsk.querySelector(".muted").after(focusChips({ hints: true }));
  bindViewControls(focusAsk);
  const close = () => {
    dismissFocusAsk();
    focusAsk.hidden = true;
    viewMenu.querySelector("summary").focus({ preventScroll: true });
    maybeTip();
  };
  $("#focus-ask-done").addEventListener("click", close);
  $("#focus-ask-close").addEventListener("click", close);
}

// "Ask me again", in View and in More: the card again, scrolled to (clear of the strip) with its
// heading focused. Closing it answers the question again.
function showFocusAsk() {
  viewMenu.open = false;
  focusAsk.hidden = false;
  focusAsk.scrollIntoView({ block: "start" });
  $("#focus-ask-title").focus({ preventScroll: true });
}

// "Only races I haven't picked": hides the races picked so far. One picked meanwhile stays
// until this runs again (switching it on, a new ballot), so it doesn't vanish mid-pick.
export function applyHidePicked() {
  const on = viewPref("hidePicked");
  for (const card of result.querySelectorAll(".race")) {
    card.classList.toggle("hidden-picked", on && page.picks.has(card.dataset.race));
  }
  hidingNote.hidden = !on;
  viewMenu.classList.toggle("filtered", on);
}

// Scrolls a race's card to just below the strip and focuses its heading. ``open`` expands
// it first if it's collapsed.
export function goTo(card, { open = false } = {}) {
  const key = card.dataset.race;
  if (open && page.picks.isCollapsed(key)) {
    page.picks.setCollapsed(key, false);
    redrawRace(key);
  }
  card.scrollIntoView({ block: "start" });
  card.querySelector(".race-toggle").focus({ preventScroll: true });
}

// The first race or proposition without a pick, after the one in focus (or the one it went
// to last), round to the start. The races that may not be on the ballot are skipped, as the
// progress skips them, and so are those "Only races with a match" hides.
function nextRace() {
  const { ballot, picks } = page;
  if (!ballot) return;
  const keys = [...ballot.races.map((r) => r.key), ...ballot.measures.map(measureKey)];
  const from = keys.indexOf(document.activeElement?.closest(".race")?.dataset.race ?? lastJumped) + 1;
  for (let i = 0; i < keys.length; i += 1) {
    const key = keys[(from + i) % keys.length];
    const card = cardFor(key);
    if (!picks.has(key) && card && !card.classList.contains("hidden-nomatch")) {
      lastJumped = key;
      goTo(card, { open: true });
      return;
    }
  }
}

// j and k: the next and previous race on the page, from the one in focus, or else from the
// one at the top of the window. Typing in a box, or an open dialog, leaves them alone.
function stepRace(event) {
  if (!page.ballot || result.hidden || (event.key !== "j" && event.key !== "k")) return;
  if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented || document.querySelector("dialog[open]")) return;
  if (event.target.closest?.('textarea, select, [contenteditable], input:not([type="radio"]):not([type="checkbox"])')) return;
  const cards = [...result.querySelectorAll(".race")].filter((card) => card.offsetParent !== null);
  let index = cards.indexOf(document.activeElement?.closest(".race"));
  if (index < 0) {
    const top = strip.getBoundingClientRect().bottom;
    let below = cards.findIndex((card) => card.getBoundingClientRect().top >= top - 1);
    if (below < 0) below = cards.length;
    index = event.key === "j" ? below - 1 : below; // so j lands on that race and k on the one before
  }
  const target = cards[index + (event.key === "j" ? 1 : -1)];
  if (!target) return;
  event.preventDefault();
  goTo(target);
}

// ---- phones ---------------------------------------------------------------------------

// On a phone (or a narrow window) the section chips join the sticky strip, and the toolbar
// (View, Help me pick, Clear picks, Print) moves under the heading, where it
// scrolls away. So what stays in view is the race on screen, the progress, Next, More (which holds
// the toolbar's buttons) and the sections. With the left pane folded, the chips join the strip too.
function placeForWidth() {
  if (narrow.matches) $(".ballot-head").after(tools);
  else strip.append(tools);
  if (narrow.matches || isPaneCollapsed()) strip.append(jump); // the chips' row last (first on a phone, by the CSS)
  else $(".side-bottom").before(jump);
  setChipsAway(false);
  syncChipFades();
}

// More's sections: View's detail (with its caption and "?"), focuses and Ask me again, the toolbar's
// buttons (with the line saying why Print waits), and Expand and Collapse all from View.
function fillMoreSheet() {
  bindViewControls(moreView);
  bindViewControls(moreFocus);
  addMoreSection({ id: "view", label: ["View ", helpLink("view-modes", "focus and views")] }, moreView, moreCaption, moreFocus,
    moreAction("Ask me again", "help", showFocusAsk));
  addMoreSection({ id: "picks", label: "Your picks" }, moreEndorsers, morePrint,
    moreAction("Clear picks", "x", () => $("#clear-picks").click(), { class: "danger" }), waitNotes[1]);
  addMoreSection({ id: "races", label: "Races" },
    moreAction("Expand all", "expand", () => setAllCollapsed(false)),
    moreAction("Collapse all", "collapse", () => setAllCollapsed(true)));
  initMoreSheet($("#more-btn"));
}

// Scrolling down on a phone, the chips' row (at the top of the strip) slides up out of the window,
// leaving the race, the progress and the buttons; any scroll up brings it back. The strip moves
// rather than shrinks, so nothing under it shifts. Only once the strip is stuck to the top.
const SCROLL_STEP = 10; // a scroll shorter than this, a finger's jitter, changes nothing
let lastScrollY = 0;

function setChipsAway(away) {
  if (away && !strip.classList.contains("chips-away")) {
    const info = strip.querySelector(".progress-info");
    strip.style.setProperty("--chips-shift", `${info.offsetTop - parseFloat(getComputedStyle(strip).paddingTop)}px`);
  }
  strip.classList.toggle("chips-away", away);
}

function chipsOnScroll() {
  const y = scrollY;
  if (Math.abs(y - lastScrollY) < SCROLL_STEP) return;
  const down = y > lastScrollY;
  lastScrollY = y;
  const stuck = strip.previousElementSibling.getBoundingClientRect().bottom < 0;
  setChipsAway(down && stuck && narrow.matches && strip.contains(jump) && !jump.hidden && !jump.contains(document.activeElement));
}

// The chips' row scrolls sideways without a scrollbar; a fade at an edge says there's more that way.
function syncChipFades() {
  const end = jumpList.scrollWidth - jumpList.clientWidth;
  jumpList.classList.toggle("fade-start", jumpList.scrollLeft > 2);
  jumpList.classList.toggle("fade-end", jumpList.scrollLeft < end - 2);
}

// On a phone, where the race headings don't stick, the strip names the race at its foot.
function markCurrentRace() {
  const line = strip.getBoundingClientRect().bottom;
  let name = "";
  for (const card of narrow.matches ? result.querySelectorAll(".race") : []) {
    const box = card.getBoundingClientRect();
    if (box.top > line) break;
    if (box.bottom > line + 40) name = card.querySelector(".race-name")?.textContent || "";
  }
  if (stripRace.textContent !== name) stripRace.textContent = name;
}

// The bar between the toolbar's two groups shows only while they share a line, so a narrow
// window doesn't leave it dangling at a line's end or alone on a line of its own.
function watchToolDivider() {
  const divider = tools.querySelector(".tool-divider");
  const [first, second] = tools.querySelectorAll(".tool-group");
  const sync = () => {
    divider.hidden = false;
    divider.hidden = second.getBoundingClientRect().top >= first.getBoundingClientRect().bottom;
  };
  const observer = new ResizeObserver(onFrame(sync));
  [tools, first, second].forEach((element) => observer.observe(element));
}

// ---- the section on screen ------------------------------------------------------------

// Marks the section on screen in the section list: the last one whose top has reached the
// line a jump scrolls to, under the strip (the first until then, the last at the foot of the
// page), so a section jumped to is the one marked. Where the list is a row of chips (a phone),
// the row scrolls sideways to show it. On a phone the strip also names the race on screen.
export function markCurrentSection() {
  if (!page.ballot || result.hidden) return;
  markCurrentRace();
  const shown = sectionLinks.filter(({ id }) => document.getElementById(id)?.offsetParent); // not hidden by the filter
  if (!shown.length) return;
  const line = strip.getBoundingClientRect().bottom + SCROLL_GAP + 4; // a little slack for rounding
  let current = shown[0];
  for (const entry of shown) {
    if (document.getElementById(entry.id).getBoundingClientRect().top <= line) current = entry;
  }
  if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) current = shown[shown.length - 1];
  if (current.id === currentSection) return;
  currentSection = current.id;
  for (const { link } of sectionLinks) {
    if (link === current.link) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  }
  const row = current.link.closest(".jump-list");
  if (row.scrollWidth > row.clientWidth) {
    const [chip, box] = [current.link.getBoundingClientRect(), row.getBoundingClientRect()];
    if (chip.left < box.left || chip.right > box.right) row.scrollLeft += chip.left - box.left - 16;
  }
}

// Wires the strip, the view controls and the keys; the left pane must be drawn (initChrome).
export function initNav(context) {
  page = context;
  migrateView();
  initEndorserBar(page, { sectionMarks: syncMatchMarks });
  $("#view-focus").append(focusChips());
  initFocusAsk();
  bindViewControls(viewControls);
  onViewChange(applyView);
  onReturn(applyView); // back from Settings, a page kept for Back missed its changes
  applyView();
  $("#expand-all").addEventListener("click", () => {
    setAllCollapsed(false);
    viewMenu.open = false;
  });
  $("#collapse-all").addEventListener("click", () => {
    setAllCollapsed(true);
    viewMenu.open = false;
  });
  $("#view-ask-again").addEventListener("click", showFocusAsk);

  // View closes like a menu: a click elsewhere, or Esc.
  document.addEventListener("click", (event) => {
    if (viewMenu.open && !viewMenu.contains(event.target)) viewMenu.open = false;
  });
  viewMenu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !viewMenu.open) return;
    event.preventDefault();
    viewMenu.open = false;
    viewMenu.querySelector("summary").focus();
  });

  nextButton.addEventListener("click", nextRace);
  document.addEventListener("keydown", stepRace);

  narrow.addEventListener("change", placeForWidth);
  onPaneToggle(placeForWidth);
  placeForWidth();
  watchToolDivider();
  fillMoreSheet();

  // Links to a section, Next and j/k scroll to just below the strip, however tall it is, and
  // each race's heading sticks right under it (--strip-h), wider than a phone.
  trackHeight(strip, "--strip-h", (height) => {
    document.documentElement.style.scrollPaddingTop = `${height + SCROLL_GAP}px`;
  });

  const markSoon = onFrame(markCurrentSection);
  const chipsSoon = onFrame(chipsOnScroll);
  const tipSoon = onFrame(maybeTip);
  addEventListener("scroll", () => {
    markSoon();
    chipsSoon();
    tipSoon();
  }, { passive: true });
  addEventListener("resize", markSoon);
  jumpList.addEventListener("scroll", onFrame(syncChipFades), { passive: true });
  new ResizeObserver(onFrame(syncChipFades)).observe(jumpList);
}
