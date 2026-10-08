// Getting around the ballot: the progress strip and Next, the left pane's list of sections (and
// which one is on screen), Simple | Detailed and Options, j and k, and where the strip's parts go on a phone.

import { ballotSections, measureKey } from "./ballot-shared.js";
import { isPaneCollapsed, narrow, onPaneToggle } from "./chrome.js";
import { $, h, onFrame, onReturn, trackHeight } from "./dom.js";
import { plural } from "./format.js";
import { syncMapShown } from "./district-map.js";
import { STILL_LOADING, cardFor, redrawRace, setAllCollapsed } from "./race-cards.js";
import { syncBoxes, syncFunding, syncLines } from "./source-cards.js";
import { bindViewControls, onViewChange, setViewPref, showViewControls, syncSourceNotes, viewPref } from "./view.js";

let page = null; // { ballot, picks }
const result = $("#result");
const strip = $("#progress-strip");
const tools = $("#ballot-tools");
const viewControls = $("#view-controls");
const viewMenu = $("#view-menu");
const nextButton = $("#next-race");
const jump = $("#jump");
const SCROLL_GAP = 12; // what a jump leaves between the strip and the section it scrolls to
// What puts the ballot back to each view switch when it changes, without a reload.
const APPLY = {
  showMap: syncMapShown,
  showPolls: () => syncBoxes("showPolls"),
  showEndorsements: syncLines,
  showFunding: () => {
    syncBoxes("showFunding");
    syncFunding();
  },
  showSources: syncSourceNotes,
  hidePicked: () => {
    if (!page.ballot) return;
    applyHidePicked();
    markCurrentSection(); // the marked section may have gone
  },
};
let applied = {}; // the view switches as the page last applied them

let sectionCounts = []; // the left pane's section list: [{ element, keys, maybe }]
let sectionLinks = []; // and its links: [{ id, link }], the section's id and the link to it
let currentSection = null; // the id of the section marked as the one on screen
let lastJumped = null; // the race "Next race to pick" went to last

const showPickedButton = h("button", { type: "button", class: "link-btn", on: { click: () => setViewPref("hidePicked", false) } }, "Show them");
export const hidingNote = h("p", { class: "notice", hidden: true }, "Races you've picked are hidden. ", showPickedButton);

// The left pane's list of sections, each with how many of its races are picked.
export function renderSections() {
  sectionCounts = [];
  sectionLinks = [];
  currentSection = null;
  const items = [];
  const add = (id, label, keys, maybe = false) => {
    const count = h("span", { class: "count" });
    const link = h("a", { href: `#${id}`, class: maybe ? "maybe-link" : null }, h("span", {}, label), count);
    sectionCounts.push({ element: count, keys, maybe });
    sectionLinks.push({ id, link });
    items.push(h("li", {}, link));
  };
  for (const section of ballotSections(page.ballot)) add(section.id, section.title, section.races.map((r) => r.key), section.maybe);
  if (page.ballot.measures.length) add("measures-section", "Propositions", page.ballot.measures.map(measureKey));
  $("#jump-list").replaceChildren(...items);
  jump.hidden = !items.length;
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
}

// While the cards are coming, the strip's bar says so, and Pick by rule and Print, which need
// them, wait. ``failed``: they won't come, so the bar goes but the two stay off.
const needCards = [$("#rule-btn"), $("#print-btn")].map((button) => ({ button, title: button.title }));

export function setCardsLoading(waiting, { failed = false } = {}) {
  $("#cards-loading").hidden = !waiting || failed;
  for (const { button, title } of needCards) {
    button.disabled = waiting;
    button.title = waiting ? STILL_LOADING : title;
  }
}

// ---- view: Simple or Detailed, collapse, only unpicked races, next race, j/k ----------

// After any change of the view settings, here or in another tab: the toolbar's Simple | Detailed
// and Options show them, and each switch that changed applies to the ballot in place, putting back
// what the voter opened or folded by hand.
function applyView() {
  showViewControls(viewControls);
  for (const [name, apply] of Object.entries(APPLY)) {
    const value = viewPref(name);
    if (name in applied && applied[name] !== value) apply();
    applied[name] = value;
  }
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
// progress skips them.
function nextRace() {
  const { ballot, picks } = page;
  if (!ballot) return;
  const keys = [...ballot.races.map((r) => r.key), ...ballot.measures.map(measureKey)];
  const from = keys.indexOf(document.activeElement?.closest(".race")?.dataset.race ?? lastJumped) + 1;
  for (let i = 0; i < keys.length; i += 1) {
    const key = keys[(from + i) % keys.length];
    if (!picks.has(key)) {
      lastJumped = key;
      goTo(cardFor(key), { open: true });
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
// (Simple | Detailed, Options, Pick by rule, Clear picks, Print) moves under the heading, where it scrolls away. So what stays in view is
// the progress, Next and the sections. With the left pane folded, the chips join the strip too.
function placeForWidth() {
  if (narrow.matches) $(".ballot-head").after(tools);
  else strip.append(tools);
  if (narrow.matches || isPaneCollapsed()) strip.append(jump); // the chips' row last
  else $(".side-bottom").before(jump);
}

// ---- the section on screen ------------------------------------------------------------

// Marks the section on screen in the section list: the last one whose top has reached the
// line a jump scrolls to, under the strip (the first until then, the last at the foot of the
// page), so a section jumped to is the one marked. Where the list is a row of chips (a phone),
// the row scrolls sideways to show it.
export function markCurrentSection() {
  if (!page.ballot || result.hidden) return;
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

  // Options closes like a menu: a click elsewhere, or Esc.
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

  // Links to a section, Next and j/k scroll to just below the strip, however tall it is, and
  // each race's heading sticks right under it (--strip-h).
  trackHeight(strip, "--strip-h", (height) => {
    document.documentElement.style.scrollPaddingTop = `${height + SCROLL_GAP}px`;
  });

  const markSoon = onFrame(markCurrentSection);
  addEventListener("scroll", markSoon, { passive: true });
  addEventListener("resize", markSoon);
}
