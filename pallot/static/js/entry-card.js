// The entry card on the ballot page: "See your ballot, race by race", with two equal tabs, My address
// and My voter card, the election and party under both, and Show my ballot. It's in the main area
// while there's no ballot, and when "Change" is chosen; on a phone with a ballot showing, it opens in
// the top bar's address panel instead. ballot.js sends the form; this module draws the tabs and says
// which one is chosen.
//
// The voter card tab shows only once the server says it takes a voter card (GET /api/config's
// ``voter_card``); its ``default_entry`` ("address" or "voter_card") chooses the tab a first visit
// starts on.

import { api } from "./api.js";
import { $, pairBox } from "./dom.js";
import { DISTRICTS, STATES } from "./labels.js";

const ENTRIES = {
  address: { tab: $("#entry-tab-address"), panel: $("#entry-address"), focus: () => $("#address") },
  voter_card: { tab: $("#entry-tab-card"), panel: $("#entry-voter-card"), focus: () => $("#vc-county") },
};
const tabs = $("#entry-tabs");
const card = $("#entry");
const home = card.parentElement;
let chosen = "address";
let chosenByVoter = false;

export function entryMode() {
  return chosen;
}

// Shows one tab's fields; the other's are disabled, so the browser doesn't ask for them.
export function selectEntry(mode, { focus = false } = {}) {
  if (!ENTRIES[mode] || (mode === "voter_card" && tabs.hidden)) mode = "address";
  chosen = mode;
  for (const [name, { tab, panel }] of Object.entries(ENTRIES)) {
    const on = name === mode;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    panel.hidden = !on;
    panel.querySelector("fieldset").disabled = !on;
  }
  if (focus) focusEntry();
}

export function focusEntry() {
  ENTRIES[chosen].focus().focus();
}

// The voter card's boxes: { county, precinct, districts: { cd, sd, hd, sboe }, precincts:
// { commissioner, jp } }, each district or precinct only when filled in.
export function readVoterCard() {
  const number = (input) => (input.value.trim() ? Number(input.value) : null);
  const request = { county: $("#vc-county").value.trim(), precinct: number($("#vc-precinct")), districts: {}, precincts: {} };
  for (const input of $("#vc-districts").querySelectorAll("input")) {
    const value = number(input);
    if (value != null) request[DISTRICTS[input.name].unit === "precinct" ? "precincts" : "districts"][input.name] = value;
  }
  return request;
}

// The card in the main area, or in the top bar's address panel (``panel``, the pane's .side-address).
export function placeEntry(panel = null) {
  const target = panel || home;
  if (card.parentElement !== target) target.prepend(card);
}

function drawVoterCardBoxes() {
  const highest = STATES.TX?.districtCounts || {};
  $("#vc-districts").replaceChildren(...Object.entries(DISTRICTS).map(([kind, { short }]) =>
    pairBox(short, { id: `vc-${kind}`, name: kind, max: highest[kind] ? String(highest[kind]) : null })));
}

function initTabs() {
  const order = Object.keys(ENTRIES);
  for (const [name, { tab, panel }] of Object.entries(ENTRIES)) {
    panel.setAttribute("role", "tabpanel");
    tab.addEventListener("click", () => {
      chosenByVoter = true;
      selectEntry(name, { focus: true });
    });
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const next = order[(order.indexOf(name) + step + order.length) % order.length];
      chosenByVoter = true;
      selectEntry(next);
      ENTRIES[next].tab.focus();
    });
  }
}

// Asks the server whether it takes a voter card, and which tab to start on. Without an answer, the
// card has only the address. ``typed()``: whether the voter has already started on the address.
export async function loadEntryConfig({ typed = () => false } = {}) {
  let config = null;
  try {
    config = await api.get("/api/config");
  } catch {
    return;
  }
  if (!config?.voter_card) return;
  drawVoterCardBoxes();
  initTabs();
  tabs.hidden = false;
  if (!chosenByVoter && !typed()) selectEntry(config.default_entry === "voter_card" ? "voter_card" : "address");
}

selectEntry("address");
