// Details: a candidate's Profile (Texas SOS, then Wikidata), their Issues (stances.js), a tab per
// other source (a member of Congress's bills in In Congress), and one Endorsements tab for TrackAIPAC, Vote for Peace and the endorsement lists,
// each tab made of folding sections, in a dialog whose head has Search, Avoid and Pick beside ‹ › ✕. ‹ and ›
// step through the race's other candidates, staying on the tab that's shown. On a phone, ‹, Pick and ›
// sit in a bar at the bottom, in reach of a thumb, and a swipe sideways steps too.

import { isBanned } from "./ban-list.js";
import { $, closeOnBackdrop, dialogHead, h, slug } from "./dom.js";
import { ordinal } from "./format.js";
import { icon } from "./icons.js";
import { candidatePills } from "./labels.js";
import { avatar, avoidWords, candidateQuery, choose, searchLink, toggleBan } from "./race-cards.js";
import { searchWord } from "./search.js";
import { cardPanel, endorsementsPanel, isLikely, moneyPanel, pollsPanel, profilePanel, renderTabs } from "./source-cards.js";
import { stancesPanel } from "./stances.js";
import { onSwipe } from "./swipe.js";

let page = null; // { picks }
const details = $("#details");
const PROFILE = new Set(["filing", "profile"]); // the kinds on the Profile tab: Texas SOS, Wikidata
let shown = "profile"; // the tab shown, which ‹ and › keep
let current = null; // { race, index }: the candidate shown, for a swipe

export function initDetails(context) {
  page = context;
  closeOnBackdrop(details);
  details.addEventListener("scroll", syncCompact, { passive: true });
  onSwipe(details, (way) => {
    const { race, index } = current || {};
    if (race?.candidates[index + way]) showDetails(race, index + way, null, shown);
  });
}

// One of a race's candidates, by ``index``. ‹ and › step through the others without closing
// the dialog; ``focus`` ("previous" or "next") keeps the focus on the one that was pressed.
// ``at`` is the tab to show: "profile" (the candidate's Profile button), "issues", "endorsements" or
// a source's (a Funding chip's money source); a tab the candidate hasn't got shows Profile, which
// every candidate has, saying so when no source has a profile of them.
export function showDetails(race, index, focus = null, at = "profile") {
  const { picks } = page;
  const candidate = race.candidates[index];
  current = { race, index };
  const pickOrUndo = () => {
    choose(race, candidate.key, !picks.isPicked(race.key, candidate.key));
    syncPickButtons();
  };
  const multiFull = race.seats > 1 && !picks.isPicked(race.key, candidate.key) && picks.picked(race.key).length >= race.seats;
  // A retention question is answered Yes or No on its card, not by picking its judge.
  const pickButtons = [0, 1].map(() => h("button", { type: "button", class: "btn small primary with-icon", disabled: multiFull,
    hidden: race.retention, on: { click: pickOrUndo } }));
  // In a ranked-choice race, Rank (at the next rank: "Rank 2nd") and Unrank.
  const syncPickButtons = () => {
    const keys = picks.picked(race.key);
    const on = keys.includes(candidate.key);
    let text = on ? "Unpick" : "Pick";
    let name = `${text} ${candidate.name}`;
    if (race.ranked_choice) {
      text = on ? "Unrank" : `Rank ${ordinal(keys.length + 1)}`;
      name = on ? `Unrank ${candidate.name}, your ${ordinal(keys.indexOf(candidate.key) + 1)} choice`
        : `Rank ${candidate.name} your ${ordinal(keys.length + 1)} choice`;
    }
    for (const button of pickButtons) {
      button.replaceChildren(icon(on ? "reset" : "check"), word(text));
      button.setAttribute("aria-label", name);
      button.title = name;
      button.classList.toggle("ghost", on);
    }
  };
  syncPickButtons();

  const pills = h("p", { class: "cand-sub" }, candidatePills(candidate, race));
  const nameHead = h("h2", { id: "details-name", "data-party": candidate.party || null }, candidate.name);
  const banButton = h("button", { type: "button", class: "btn small ghost with-icon", on: { click: () => toggleBan(candidate, syncBan) } });
  const syncBan = () => {
    const on = isBanned(candidate);
    const { word: text, label } = avoidWords(candidate, on);
    banButton.replaceChildren(icon("ban"), word(text));
    banButton.setAttribute("aria-label", label);
    banButton.title = label;
    banButton.classList.toggle("is-banned", on);
    pills.replaceChildren(...candidatePills(candidate, race).filter(Boolean));
    nameHead.classList.toggle("is-banned", on);
  };
  syncBan();

  const grouped = candidate.cards.filter((card) => card.kind === "endorsement");
  const profiled = candidate.cards.filter((card) => PROFILE.has(card.kind));
  const profile = { key: "profile", label: "Profile", likely: profiled.some(isLikely) };
  const issues = { key: "issues", label: "Issues", likely: false };
  const endorsements = grouped.length
    ? { key: "endorsements", label: `Endorsements · ${grouped.length}`, likely: grouped.some(isLikely) }
    : null;
  const tabs = [
    profile,
    issues,
    ...candidate.cards.filter((card) => card.kind !== "endorsement" && !PROFILE.has(card.kind))
      .map((card) => ({ key: card.source, label: card.label, likely: isLikely(card), card })),
    endorsements,
  ].filter(Boolean);
  const initial = Math.max(0, tabs.findIndex((tab) => tab.key === at));
  shown = tabs[initial].key;
  const panelFor = (tab) => {
    if (tab === issues) return stancesPanel(candidate, candidateQuery(race, candidate), !candidate.cards.length);
    if (tab === profile) return profilePanel(profiled, candidate.name);
    if (tab === endorsements) return endorsementsPanel(grouped);
    if (tab.card.kind === "polls") return pollsPanel(tab.card, candidate.party);
    return tab.card.kind === "money" ? moneyPanel(tab.card) : cardPanel(tab.card);
  };
  const tabBox = h("div", { class: "details-tabs" });
  renderTabs(tabBox, tabs, `d-${slug(candidate.key)}`, panelFor, { initial, onSelect: (i) => { shown = tabs[i].key; } });

  const count = race.candidates.length;
  const step = (offset, label, className, ...content) => {
    const other = race.candidates[index + offset];
    return h("button", {
      type: "button", class: className, disabled: !other,
      "aria-label": other ? `${label} candidate: ${other.name}` : `No ${label.toLowerCase()} candidate`,
      title: other ? other.name : null, on: { click: () => showDetails(race, index + offset, label.toLowerCase(), shown) },
    }, content);
  };
  const steps = count > 1 ? {
    previous: [step(-1, "Previous", "icon-btn step", "‹"), step(-1, "Previous", "btn small ghost", "‹ ", word("Previous"))],
    next: [step(1, "Next", "icon-btn step", "›"), step(1, "Next", "btn small ghost", word("Next"), " ›")],
  } : { previous: [], next: [] };
  const bar = h("div", { class: "details-bar" }, steps.previous[1], pickButtons[1], steps.next[1]);

  const search = searchLink(race, candidate, "btn small ghost with-icon", [icon("search"), word(`${searchWord()} ↗`)]);
  const { head, close } = dialogHead(details, [
    avatar(candidate, "large"),
    h("div", { class: "details-title" },
      nameHead,
      h("p", { class: "muted details-race" }, race.name, count > 1 ? ` · ${index + 1} of ${count}` : ""),
      pills),
    h("div", { class: "details-actions" }, search, banButton, pickButtons[0]),
  ], steps.previous[0], steps.next[0]);
  details.classList.remove("compact");
  details.replaceChildren(head, tabBox, bar);
  if (!details.open) details.showModal();
  details.scrollTop = 0;
  const pressed = (steps[focus] || []).find((button) => button.offsetParent && !button.disabled);
  (pressed || close).focus();
}

// A button's word; on a phone, Search's and Avoid's hide, leaving their icons, and the button's
// accessible name and tooltip say the rest.
const word = (text) => h("span", { class: "btn-word" }, text);

// The head shrinks to the photo, the name and the buttons' icons once the voter scrolls down, and
// grows back at the top. It shrinks only with room to scroll after, and grows back nearer the top
// than it shrank, so it never flips back and forth. The tabs stick under it (--head-h, dialogHead).
const SHRINK_AT = 48;
const GROW_AT = 8;

function syncCompact() {
  const top = details.scrollTop;
  if (details.classList.contains("compact")) {
    if (top < GROW_AT) details.classList.remove("compact");
  } else if (top > SHRINK_AT && details.scrollHeight - details.clientHeight > 160) {
    details.classList.add("compact");
  }
}
