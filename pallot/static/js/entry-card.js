// The entry card on the ballot page: "See your ballot, race by race", with equal tabs, Address, Voter
// card and Pallot file (a saved session, or picks someone sent, read as soon as it's chosen and opened
// on Show my ballot), the election and party under them, and Show my ballot. It's in the main area
// while there's no ballot, and when "Change" is chosen; on a phone with a ballot showing, it opens in
// the top bar's address panel instead. ballot.js sends the form; this module draws the tabs and says
// which one is chosen.
//
// The voter card tab shows only once the server says it takes a voter card (GET /api/config's
// ``voter_card``); its ``default_entry`` ("address" or "voter_card") chooses the tab a first visit
// starts on. Its ``states`` give the State box, each state's counties for the County box's
// suggestions, and the district boxes its coverage shows: Texas's precinct, which finds the rest,
// and its commissioner and JP precincts too. The voter's last state is remembered.

import { api } from "./api.js";
import { $, h, setStatus } from "./dom.js";
import { DISTRICTS, STATES, districtName } from "./labels.js";
import { chooseFile, fileLines, readFile } from "./pallot-file.js";
import { setUiPref, uiPref } from "./storage.js";

const ENTRIES = {
  address: { tab: $("#entry-tab-address"), panel: $("#entry-address"), focus: () => $("#address") },
  voter_card: { tab: $("#entry-tab-card"), panel: $("#entry-voter-card"), focus: () => $("#vc-state") },
  file: { tab: $("#entry-tab-file"), panel: $("#entry-file"), focus: () => $("#choose-file-btn") },
};
const TEXAS = { code: "TX", name: "Texas", counties: [], districts: ["cd", "sd", "hd", "sboe"], precincts: true };
let cardStates = { TX: TEXAS };
let wantedState = "TX";
const card = $("#entry");
const home = card.parentElement;
const above = card.previousElementSibling; // the welcome's heading, which stays above the card
let chosen = "address";
let chosenByVoter = false;

export function entryMode() {
  return chosen;
}

// Shows one tab's fields; the other's are disabled, so the browser doesn't ask for them.
export function selectEntry(mode, { focus = false } = {}) {
  if (!ENTRIES[mode] || ENTRIES[mode].tab.hidden) mode = "address";
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

// The voter card's boxes: { state, county, precinct, districts: { cd, sd, hd, sboe }, precincts:
// { commissioner, jp } }, the precinct, each district and each precinct only when filled in.
export function readVoterCard() {
  const number = (input) => (input.value.trim() ? Number(input.value) : null);
  const request = { state: $("#vc-state").value, county: $("#vc-county").value.trim(), districts: {}, precincts: {} };
  const precinct = $("#vc-precinct")?.value.trim();
  if (precinct) request.precinct = precinct;
  for (const input of $("#vc-districts").querySelectorAll("input[type=number]")) {
    const value = number(input);
    if (value != null) request[DISTRICTS[input.name].unit === "precinct" ? "precincts" : "districts"][input.name] = value;
  }
  return request;
}

// Fills the voter card's boxes from a remembered lookup ({ state, county, precinct, districts,
// precincts }); a lookup from before the card had a state is Texas's.
export function fillVoterCard({ state = "TX", county = "", precinct = "", districts = {}, precincts = {} } = {}) {
  chooseState(state);
  $("#vc-county").value = county;
  const numbers = { ...districts, ...precincts, precinct: precinct ?? "" };
  for (const input of $("#vc-districts").querySelectorAll("input")) input.value = numbers[input.name] ?? "";
}

// The card in the main area, or in the top bar's address panel (``panel``, the pane's .side-address).
export function placeEntry(panel = null) {
  const target = panel || home;
  if (card.parentElement === target) return;
  if (!panel && above) above.after(card);
  else target.prepend(card);
}

// The state's optional boxes, each the size of State and County's, on the same grid: Texas's
// precinct first, then the districts its coverage shows, and its commissioner and JP precincts.
// ``keep``: the values to put back, by name. Texas's wording, sketch and links show only for Texas.
function drawVoterCardBoxes(state, keep = {}) {
  const highest = STATES[state.code]?.districtCounts || {};
  const kinds = [...state.districts, ...(state.precincts ? Object.keys(DISTRICTS).filter((kind) => DISTRICTS[kind].unit === "precinct") : [])];
  const precinct = state.precincts && h("div", { class: "field" },
    h("label", { for: "vc-precinct" }, "Precinct"),
    h("input", { id: "vc-precinct", name: "precinct", type: "text", autocomplete: "off", autocapitalize: "characters",
      spellcheck: "false", maxlength: "8", pattern: "[0-9A-Za-z]{1,8}", placeholder: "e.g. 300",
      title: "The precinct number on your card, such as 300 or 101A", value: keep.precinct || "" }));
  $("#vc-districts").replaceChildren(...[precinct, ...kinds.filter((kind) => DISTRICTS[kind]).map((kind) =>
    h("div", { class: "field" },
      h("label", { for: `vc-${kind}` }, districtName(kind, state.labels)),
      h("input", { type: "number", inputmode: "numeric", min: "1", id: `vc-${kind}`, name: kind,
        max: highest[kind] ? String(highest[kind]) : null, value: keep[kind] ?? "" })))].filter(Boolean));
  const texas = state.code === "TX";
  $("#vc-districts-hint").textContent = state.precincts
    ? "Optional: fill in any your card lists. With your precinct, Pallot finds the rest."
    : "Optional: fill in any your card lists.";
  $("#vc-where").hidden = !texas;
  if (!texas) $("#vc-where-panel").hidden = true;
  $("#vc-where").setAttribute("aria-expanded", String(!$("#vc-where-panel").hidden));
  const sample = texas ? "Travis" : state.counties[0]?.replace(/ (County|Parish|Borough|Census Area|Municipality)$/, "");
  $("#vc-county").placeholder = sample ? `e.g. ${sample}` : "";
  $("#vc-counties").replaceChildren(...state.counties.map((name) => h("option", { value: name })));
}

function boxValues() {
  return Object.fromEntries([...$("#vc-districts").querySelectorAll("input")].map((input) => [input.name, input.value]));
}

// Shows a state's boxes, empty. Before the states have loaded, it's remembered and Texas's show.
function chooseState(code) {
  wantedState = code;
  const state = cardStates[code] || cardStates.TX;
  $("#vc-state").value = state.code;
  drawVoterCardBoxes(state);
}

// Fills the State box once the states have loaded, keeping what the voter or a remembered lookup put in the boxes.
function initStates(states) {
  if (!states.length) return;
  cardStates = Object.fromEntries(states.map((state) => [state.code, state]));
  if (!cardStates.TX) cardStates.TX = TEXAS;
  $("#vc-state").replaceChildren(...states.map((state) => h("option", { value: state.code }, state.name)));
  const state = cardStates[wantedState] || cardStates.TX;
  $("#vc-state").value = state.code;
  drawVoterCardBoxes(state, boxValues());
  $("#vc-state").addEventListener("change", () => {
    const code = $("#vc-state").value;
    setUiPref("cardState", code);
    $("#vc-county").value = "";
    chooseState(code);
  });
}

// "Where do I find these?", a small link by the districts' heading: shows or hides the card's sketch under them.
function initWhere() {
  const button = $("#vc-where");
  const panel = $("#vc-where-panel");
  button.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
  });
}

// The Pallot file tab: the file is read as soon as it's chosen, asking for its phrase if it's locked, and
// what it holds shows under it; ballot.js opens it on Show my ballot.
let chosenSlate = null;
export const pickedSlate = () => chosenSlate;

function initFileTab() {
  const status = $("#file-status");
  const holds = $("#file-holds");
  $("#choose-file-btn").addEventListener("click", async () => {
    const file = await chooseFile();
    if (!file) return;
    setStatus(status, "");
    let opened = null;
    try {
      opened = await readFile(file);
    } catch (error) {
      setStatus(status, error.message, "error");
    }
    chosenSlate = opened;
    $("#chosen-file").textContent = opened ? file.name : "No file chosen";
    holds.hidden = !opened;
    holds.replaceChildren(...(opened ? fileLines(opened).map((line) => h("p", { class: "fine" }, line)) : []));
  });
}

function initTabs() {
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
      const order = Object.keys(ENTRIES).filter((key) => !ENTRIES[key].tab.hidden);
      const next = order[(order.indexOf(name) + step + order.length) % order.length];
      chosenByVoter = true;
      selectEntry(next);
      ENTRIES[next].tab.focus();
    });
  }
}

// Asks the server whether it takes a voter card, and which tab to start on. Without an answer, the
// card has only the address. ``startOn()``: the tab of the voter's last lookup, if any;
// ``typed()``: whether the voter has already started on the address.
export async function loadEntryConfig({ startOn = () => null, typed = () => false } = {}) {
  let config = null;
  try {
    config = await api.get("/api/config");
  } catch {
    return;
  }
  if (!config?.voter_card) return;
  initStates(config.states || []);
  ENTRIES.voter_card.tab.hidden = false;
  if (chosenByVoter) return;
  const mode = startOn() || (typed() ? "address" : config.default_entry);
  selectEntry(mode === "voter_card" ? "voter_card" : "address");
}

initWhere();
initTabs();
initFileTab();
chooseState(uiPref("cardState") || "TX");
selectEntry("address");
