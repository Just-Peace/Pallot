// Details: a candidate's Issues (stances.js), a tab per source, and one Endorsements tab for the
// ratings and endorsement lists, in a dialog whose head has Search and Pick beside ‹ › ✕. ‹ and ›
// step through the race's other candidates, staying on the tab that's shown.

import { $, closeOnBackdrop, dialogHead, h, slug } from "./dom.js";
import { icon } from "./icons.js";
import { candidatePills } from "./labels.js";
import { avatar, candidateQuery, choose, searchLink } from "./race-cards.js";
import { searchWord } from "./search.js";
import { cardPanel, endorsementsPanel, isLikely, renderTabs } from "./source-cards.js";
import { stancesPanel } from "./stances.js";

let page = null; // { picks }
const details = $("#details");
const GROUPED = new Set(["scorecard", "endorsement"]); // the kinds on the Endorsements tab
let shown = "issues"; // the tab shown, which ‹ and › keep

export function initDetails(context) {
  page = context;
  closeOnBackdrop(details);
  details.addEventListener("scroll", syncCompact, { passive: true });
}

// One of a race's candidates, by ``index``. ‹ and › step through the others without closing
// the dialog; ``focus`` ("previous" or "next") keeps the focus on the one that was pressed.
// ``at`` is the tab to show: "issues", "endorsements" or a source's (a Funding chip's money
// source); a tab the candidate hasn't got shows Issues.
export function showDetails(race, index, focus = null, at = "issues") {
  const { picks } = page;
  const candidate = race.candidates[index];
  const pickOrUndo = () => {
    choose(race, candidate.key, !picks.isPicked(race.key, candidate.key));
    syncPickButton();
  };
  const pickButton = h("button", { type: "button", class: "btn small primary with-icon", on: { click: pickOrUndo } });
  const syncPickButton = () => {
    const on = picks.isPicked(race.key, candidate.key);
    const name = on ? `Unpick ${candidate.name}` : `Pick ${candidate.name}`;
    pickButton.replaceChildren(icon(on ? "reset" : "check"), word(on ? "Unpick" : "Pick"));
    pickButton.setAttribute("aria-label", name);
    pickButton.title = name;
    pickButton.classList.toggle("ghost", on);
  };
  syncPickButton();
  const multiFull = race.seats > 1 && !picks.isPicked(race.key, candidate.key) && picks.picked(race.key).length >= race.seats;
  pickButton.disabled = multiFull;

  const grouped = candidate.cards.filter((card) => GROUPED.has(card.kind));
  const issues = { key: "issues", label: "Issues", likely: false };
  const endorsements = grouped.length
    ? { key: "endorsements", label: `Endorsements · ${grouped.length}`, likely: grouped.some(isLikely) }
    : null;
  const tabs = [
    issues,
    ...candidate.cards.filter((card) => !GROUPED.has(card.kind)).map((card) => ({ key: card.source, label: card.label, likely: isLikely(card), card })),
    endorsements,
  ].filter(Boolean);
  const initial = Math.max(0, tabs.findIndex((tab) => tab.key === at));
  shown = tabs[initial].key;
  const panelFor = (tab) => {
    if (tab === issues) return stancesPanel(candidate, candidateQuery(race, candidate), !candidate.cards.length);
    if (tab === endorsements) return endorsementsPanel(grouped);
    return cardPanel(tab.card);
  };
  const tabBox = h("div", { class: "details-tabs" });
  renderTabs(tabBox, tabs, `d-${slug(candidate.key)}`, panelFor, { initial, onSelect: (i) => { shown = tabs[i].key; } });

  const count = race.candidates.length;
  const step = (offset, label, symbol) => {
    const other = race.candidates[index + offset];
    return h("button", {
      type: "button", class: "icon-btn step", disabled: !other,
      "aria-label": other ? `${label} candidate: ${other.name}` : `No ${label.toLowerCase()} candidate`,
      title: other ? other.name : null, on: { click: () => showDetails(race, index + offset, label.toLowerCase(), shown) },
    }, symbol);
  };
  const steps = count > 1 ? { previous: step(-1, "Previous", "‹"), next: step(1, "Next", "›") } : {};

  const search = searchLink(race, candidate, "btn small ghost with-icon", [icon("search"), word(`${searchWord()} ↗`)]);
  const { head, close } = dialogHead(details, [
    avatar(candidate, "large"),
    h("div", { class: "details-title" },
      h("h2", { id: "details-name", "data-party": candidate.party || null }, candidate.name),
      h("p", { class: "muted" }, race.name, count > 1 ? ` · ${index + 1} of ${count}` : ""),
      h("p", { class: "cand-sub" }, candidatePills(candidate, race))),
    h("div", { class: "details-actions" }, search, pickButton),
  ], steps.previous, steps.next);
  details.classList.remove("compact");
  details.replaceChildren(head, tabBox);
  headSize.disconnect();
  headSize.observe(head);
  if (!details.open) details.showModal();
  details.scrollTop = 0;
  const pressed = steps[focus];
  (pressed && !pressed.disabled ? pressed : close).focus();
}

// A head button's word, which hides once the head shrinks, leaving its icon; the button's
// accessible name and tooltip say the rest.
const word = (text) => h("span", { class: "btn-word" }, text);

// The head shrinks to the photo, the name and the buttons' icons once the voter scrolls down, and
// grows back at the top. It shrinks only with room to scroll after, and grows back nearer the top
// than it shrank, so it never flips back and forth. The tabs stick under it (--head-h).
const SHRINK_AT = 48;
const GROW_AT = 8;
const headSize = new ResizeObserver(([entry]) => {
  details.style.setProperty("--head-h", `${entry.target.offsetHeight}px`);
});

function syncCompact() {
  const top = details.scrollTop;
  if (details.classList.contains("compact")) {
    if (top < GROW_AT) details.classList.remove("compact");
  } else if (top > SHRINK_AT && details.scrollHeight - details.clientHeight > 160) {
    details.classList.add("compact");
  }
}
