// Details: a candidate's cards from every source, one tab each, in a dialog, with Pick and a web
// search. ‹ and › step through the race's other candidates.

import { $, closeOnBackdrop, dialogHead, h, slug } from "./dom.js";
import { candidatePills } from "./labels.js";
import { avatar, choose, searchLink } from "./race-cards.js";
import { searchTitle } from "./search.js";
import { renderTabs } from "./source-cards.js";

let page = null; // { picks }
const details = $("#details");

export function initDetails(context) {
  page = context;
  closeOnBackdrop(details);
}

// One of a race's candidates, by ``index``. ‹ and › step through the others without closing
// the dialog; ``focus`` ("previous" or "next") keeps the focus on the one that was pressed.
export function showDetails(race, index, focus = null) {
  const { picks } = page;
  const candidate = race.candidates[index];
  const pickOrUndo = () => {
    choose(race, candidate.key, !picks.isPicked(race.key, candidate.key));
    syncPickButton();
  };
  const pickButton = h("button", { type: "button", class: "btn primary", on: { click: pickOrUndo } });
  const syncPickButton = () => {
    const on = picks.isPicked(race.key, candidate.key);
    pickButton.textContent = on ? "✓ Picked (undo)" : `Pick ${candidate.name}`;
    pickButton.classList.toggle("ghost", on);
  };
  syncPickButton();
  const multiFull = race.seats > 1 && !picks.isPicked(race.key, candidate.key) && picks.picked(race.key).length >= race.seats;
  pickButton.disabled = multiFull;

  const tabs = h("div", { class: "details-tabs" });
  if (candidate.cards.length) renderTabs(tabs, candidate.cards, `d-${slug(candidate.key)}`);
  else tabs.append(h("p", { class: "muted details-empty" }, "No source has details on this candidate yet."));

  const count = race.candidates.length;
  const step = (offset, label, symbol) => {
    const other = race.candidates[index + offset];
    return h("button", {
      type: "button", class: "icon-btn step", disabled: !other,
      "aria-label": other ? `${label} candidate: ${other.name}` : `No ${label.toLowerCase()} candidate`,
      title: other ? other.name : null, on: { click: () => showDetails(race, index + offset, label.toLowerCase()) },
    }, symbol);
  };
  const steps = count > 1 ? { previous: step(-1, "Previous", "‹"), next: step(1, "Next", "›") } : {};

  const { head, close } = dialogHead(details, [
    avatar(candidate, "large"),
    h("div", { class: "details-title" },
      h("h2", { id: "details-name" }, candidate.name),
      h("p", { class: "muted" }, race.name, count > 1 ? ` · ${index + 1} of ${count}` : ""),
      h("p", { class: "cand-sub" }, candidatePills(candidate, race))),
  ], steps.previous, steps.next);
  details.replaceChildren(
    head,
    tabs,
    h("div", { class: "details-foot" }, searchLink(race, candidate, "btn ghost", `${searchTitle(candidate.name)} ↗`), pickButton),
  );
  if (!details.open) details.showModal();
  details.scrollTop = 0;
  const pressed = steps[focus];
  (pressed && !pressed.disabled ? pressed : close).focus();
}
