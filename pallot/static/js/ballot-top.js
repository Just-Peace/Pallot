// On a phone, When to vote and Your districts fold into a line each above the map, so the first race
// shows on the first screen: "Early voting Oct 19–30 · Election Day Nov 3" and "Your districts: US
// House 10 · Senate 14 · House 49 · Pct 300". A line opens its full card under it. Wider, the lines
// are hidden and the cards always show (the CSS).

import { $, h } from "./dom.js";
import { keyDatesSummary } from "./key-dates.js";

// Opens or folds a card the lines stand for (``id``: "key-dates", "districts-card").
export function openTopCard(id, open) {
  $(`#${id}`).classList.toggle("open", open);
  $(`.top-line[aria-controls="${id}"]`).setAttribute("aria-expanded", String(open));
}

export function initBallotTop() {
  for (const line of document.querySelectorAll(".top-line")) {
    line.addEventListener("click", () => openTopCard(line.getAttribute("aria-controls"), line.getAttribute("aria-expanded") !== "true"));
  }
}

function fill(id, label, text) {
  $(`.top-line[aria-controls="${id}"]`).replaceChildren(
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "top-line-text" }, label, text),
  );
}

// "US House 10 · Senate 14 · House 49 · Pct 300", as many as are known.
function districtsText(ballot, request) {
  const d = ballot.districts;
  const precinct = d.election_precinct?.name ?? (ballot.location.source === "voter_card" ? request?.precinct : null);
  return [
    d.cd != null && `US House ${d.cd}`, d.sd != null && `Senate ${d.sd}`, d.hd != null && `House ${d.hd}`, precinct && `Pct ${precinct}`,
  ].filter(Boolean).join(" · ") || "not known yet";
}

// After the cards are drawn for a ballot. A card stays as the voter left it, and Your districts opens
// when it holds a warning: races left off, or an approximate address.
export function renderBallotTop(ballot, request) {
  const dates = $("#key-dates");
  $("#top-summary").hidden = dates.hidden && $("#districts-card").hidden;
  $('.top-line[aria-controls="key-dates"]').hidden = dates.hidden;
  fill("key-dates", h("span", { class: "sr-only" }, "When to vote: "), keyDatesSummary(ballot));
  fill("districts-card", h("strong", {}, "Your districts: "), districtsText(ballot, request));
  if (ballot.left_out || ballot.location.approximate) openTopCard("districts-card", true);
}
