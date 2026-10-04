// Your districts: the voter's districts and precincts, where they came from, and a prompt for a
// precinct races wait on. The pencil turns each number into a box; the voter's numbers go back
// to the server with the address (``page.lookup``), and Reset goes back to the looked-up ones.

import { goTo } from "./ballot-nav.js";
import { $, h } from "./dom.js";
import { listed } from "./format.js";
import { icon } from "./icons.js";
import { DISTRICTS, PRECINCT_KINDS, STATES } from "./labels.js";
import { showToast } from "./toast.js";

let page = null; // { ballot, request, lookup }
let editing = false; // the numbers are boxes, after the pencil
let drawnFor = null; // the ballot the card was drawn for: a new one closes the boxes

export function initDistrictsCard(context) {
  page = context;
}

// The name on the card: "State Senate", "SBOE" with its long name as a tooltip, "JP & Constable".
function districtLabel(kind) {
  const { short, long } = DISTRICTS[kind];
  const name = short === long ? short : h("abbr", { title: long }, short);
  return kind === "jp" ? [name, " & Constable"] : name;
}

// "State Senate district", "Justice of the Peace and Constable precinct": a box's tooltip.
function spelledOut(kind) {
  return `${DISTRICTS[kind].long}${kind === "jp" ? " and Constable" : ""} ${DISTRICTS[kind].unit}`;
}

function shownNumbers(d) {
  return { cd: d.cd ?? null, sd: d.sd ?? null, hd: d.hd ?? null, sboe: d.sboe ?? null,
    commissioner: d.commissioner ?? null, jp: d.jp ?? d.constable ?? null };
}

// A district's number, or a box in its place after the pencil (``edit``: its kind). A seat that
// isn't up is grey, and a number races wait on, missing, is amber.
function district(label, value, { notUp = false, missing = false, title = null, edit = null } = {}) {
  if (edit) {
    const max = STATES[page.ballot.location.state]?.districtCounts?.[edit];
    return h("label", { class: "district editing", title: spelledOut(edit) }, label ? [label, " "] : null,
      h("input", { type: "number", class: "district-input", name: edit, min: "1", max: max ? String(max) : null, inputmode: "numeric",
        value: value ?? null }));
  }
  const shown = value == null
    ? h("strong", { class: "unknown" }, "—", h("span", { class: "sr-only" }, missing ? "missing: races depend on it" : "not known"))
    : h("strong", {}, value, notUp ? h("span", { class: "sr-only" }, " (not up this time)") : null);
  const kind = missing && value == null ? "district missing" : notUp ? "district not-up" : "district";
  title = missing && value == null ? "Missing: races on your ballot depend on it" : notUp ? "Not up for election this time" : title;
  return h("span", { class: kind, title }, label ? [label, " "] : null, shown);
}

// "Election precinct from the Texas Legislative Council's map “…”": the map's own name, quoted.
function electionPrecinctSource(precinct) {
  return ` Election precinct from the Texas Legislative Council's map “${precinct.map_label}”`
    + `${precinct.primary_map ? ", which normally carries over to the November general" : ""}; `
    + "your voter registration certificate wins if they differ.";
}

// Who gave the commissioner and JP precincts and the city council district, in a sentence each:
// " Commissioner and JP precincts from Harris County's list of its election precincts. City council district from Ballotpedia."
function precinctSources(d) {
  const groups = new Map();
  for (const kind of PRECINCT_KINDS) {
    const source = d.precinct_sources?.[kind];
    const value = kind === "jp" ? d.jp ?? d.constable : d[kind];
    if (source && (source === "you" || value != null)) groups.set(source, [...(groups.get(source) || []), DISTRICTS[kind].short]);
  }
  const named = (names) => `${listed(names)} ${names.length > 1 ? "precincts" : "precinct"}`;
  const county = d.county_source;
  const from = {
    you: () => "you entered",
    county: (names) => `from ${county?.county} County's ${county?.method === "table" ? "list of its election precincts"
      : names.length > 1 ? "maps, which hold your whole election precinct" : "map, which holds your whole election precinct"}`,
    ballotpedia: () => `${d.city_council ? "and city council district " : ""}from Ballotpedia`,
  };
  const parts = [...groups].map(([source, names]) => `${named(names)} ${from[source](names)}`);
  if (d.city_council && !groups.has("ballotpedia")) parts.push("City council district from Ballotpedia");
  return parts.map((part) => ` ${part}.`).join("");
}

function notUpNote(d) {
  const names = (d.not_up || []).filter((kind) => d[kind] != null).map((kind) => `${DISTRICTS[kind].short} ${d[kind]}`);
  if (!names.length) return null;
  return h("p", { class: "district-note" }, `${listed(names)} ${names.length > 1 ? "aren't" : "isn't"} up for election this time.`);
}

function districtRow(...items) {
  const shown = items.filter(Boolean);
  return shown.length
    ? h("p", { class: "district-line" }, shown.map((item, i) => [i ? h("span", { class: "sep" }, " · ") : null, item]))
    : null;
}

// " U.S. House and SBOE districts you entered."
function enteredDistricts(d) {
  const names = (d.entered || []).map((kind) => DISTRICTS[kind].short);
  return names.length ? ` ${listed(names)} ${names.length > 1 ? "districts" : "district"} you entered.` : "";
}

export function renderDistricts() {
  const { ballot } = page;
  if (drawnFor !== ballot) {
    drawnFor = ballot;
    editing = false;
  }
  const { location, districts: d } = ballot;
  const shown = shownNumbers(d);
  const waiting = ballot.maybe.find((section) => section.id === "precinct");
  const missing = PRECINCT_KINDS.filter((kind) => shown[kind] == null);
  const prompted = Boolean(waiting) && missing.length > 0;
  const needed = (kind) => prompted && missing.includes(kind);
  const school = location.school_district?.replace(/\bIndependent School District\b/, "ISD");
  const precinct = d.election_precinct;
  const notUp = new Set(d.not_up || []);
  const number = (kind, options = {}) => district(districtLabel(kind), shown[kind],
    { notUp: notUp.has(kind), missing: needed(kind), edit: editing ? kind : null, ...options });

  const rows = [
    districtRow(number("cd"), number("sd"), number("hd"), number("sboe")),
    districtRow(
      location.county && district("County", location.county),
      precinct && district("Precinct", precinct.name, { title: `Election precinct, from the map “${precinct.map_label}”` }),
      number("commissioner"),
      number("jp"),
    ),
    districtRow(
      location.city && district(null, location.city),
      d.city_council && district("City council", d.city_council),
      school && district(null, school),
    ),
    location.approximate
      ? h("p", { class: "district-warn" }, "Approximate address: check these against your voter registration certificate.")
      : null,
    prompted ? precinctPrompt(waiting, missing) : null,
    editing ? null : notUpNote(d),
  ].filter(Boolean);
  $("#districts-card").replaceChildren(
    h("div", { class: "districts-head" }, h("h2", { id: "districts-card-title" }, "Your districts"), districtActions(d)),
    ...(editing ? [districtsForm(rows, shown)] : rows),
    h("p", { class: "fine" }, "Districts from the US Census and the Texas Legislative Council.",
      enteredDistricts(d), precinct ? electionPrecinctSource(precinct) : "", precinctSources(d)),
  );
  $("#districts-card").hidden = false;
}

// The pencil, which opens every number for editing, and Reset, which works once any number is the voter's.
function districtActions(d) {
  const label = "Edit your districts";
  const pencil = h("button", { type: "button", class: "icon-only", id: "districts-edit", "aria-label": label, title: label,
    "aria-pressed": String(editing), on: { click: () => setEditing(!editing) } }, icon("edit"));
  const yours = Boolean(d.entered?.length) || Object.values(d.precinct_sources || {}).includes("you");
  const back = yours ? "Reset to the districts Pallot looked up"
    : "Reset: nothing to reset, these are the districts Pallot looked up";
  const reset = h("button", { type: "button", class: "icon-only", "aria-label": back, title: back, disabled: !yours,
    on: { click: () => updateDistricts(null) } }, icon("reset"));
  return h("div", { class: "district-actions" }, pencil, reset);
}

// The card's lines with their open boxes. It sends only the numbers the voter changed, on top of
// the ones they entered before; the rest keep following the address, the county and Ballotpedia.
function districtsForm(rows, shown) {
  const cancel = h("button", { class: "btn small ghost", type: "button", on: { click: () => setEditing(false) } }, "Cancel");
  const buttons = [h("button", { class: "btn small primary", type: "submit" }, "Update my ballot"), cancel];
  const form = h("form", { class: "districts-form", id: "districts-form", "aria-label": "Your districts" },
    rows, h("div", { class: "button-row" }, buttons));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const districts = { ...page.request.districts };
    const precincts = { ...page.request.precincts };
    let changed = false;
    for (const input of form.querySelectorAll(".district-input")) {
      const kind = input.name;
      const typed = parseInt(input.value, 10);
      const value = typed > 0 ? typed : null;
      if (value === shown[kind]) continue;
      changed = true;
      if (DISTRICTS[kind].unit === "district") districts[kind] = value;
      else precincts[kind] = value;
      if (kind === "jp") precincts.constable = value;
    }
    if (changed) updateDistricts({ districts, precincts });
    else setEditing(false);
  });
  return form;
}

function precinctPrompt(waiting, missing) {
  const count = waiting.races.length;
  const one = missing.length === 1;
  const enter = h("button", { type: "button", class: "link-btn", on: { click: openPrecincts } }, one ? "Enter it" : "Enter them");
  const seeRaces = () => {
    const first = $("#maybe-precinct .race");
    if (first) goTo(first);
  };
  const see = h("button", { type: "button", class: "link-btn", on: { click: seeRaces } }, one && count === 1 ? "See the race" : "See the races");
  // it names the precincts it asks for, since the card also shows the election precinct
  const asked = `your ${listed(missing.map((kind) => DISTRICTS[kind].long.toLowerCase()))} ${one ? "precinct" : "precincts"}`;
  const precinct = page.ballot.districts.election_precinct;
  return h("p", { class: "precinct-prompt" },
    precinct
      ? `Your election precinct is ${precinct.name}. Enter ${asked} from the same voter registration certificate. `
      : `Enter ${asked} from your voter registration certificate. `,
    `${count} ${count === 1 ? "race depends" : "races depend"} on ${one ? "it" : "them"}. `, enter, " · ", see);
}

// The first empty box (of ``kinds``, when given), else the first.
function firstEmptyBox(kinds = null) {
  const inputs = [...document.querySelectorAll("#districts-form .district-input")]
    .filter((input) => !kinds || kinds.includes(input.name));
  return inputs.find((input) => !input.value) ?? inputs[0];
}

function setEditing(on) {
  editing = on;
  renderDistricts();
  (on ? firstEmptyBox() : $("#districts-edit"))?.focus();
}

// Opens the boxes, at the first empty precinct: the prompt's Enter it, and the link above the
// races that wait on the precincts.
export function openPrecincts() {
  if (!editing) {
    editing = true;
    renderDistricts();
  }
  const field = firstEmptyBox(PRECINCT_KINDS);
  field.scrollIntoView({ block: "center" });
  field.focus({ preventScroll: true });
}

// ``entered``: { districts, precincts } the voter gave, or null to go back to the looked-up ones.
async function updateDistricts(entered) {
  const { precincts: _precincts, districts: _districts, ...request } = page.request;
  for (const [key, numbers] of Object.entries(entered || {})) {
    if (Object.keys(numbers).length) request[key] = numbers;
  }
  const before = page.ballot;
  await page.lookup(request, { keepBallot: true });
  if (page.ballot === before) return;
  $("#districts-edit")?.focus();
  const waiting = page.ballot.maybe.some((section) => section.id === "precinct");
  const target = waiting ? "#maybe-precinct .race" : "#group-precinct .race";
  const show = { label: "Show", run: () => { const first = $(target); if (first) goTo(first); } };
  showToast(waiting ? "Your ballot is updated. Some races still depend on your commissioner or JP precinct."
    : "Your ballot is updated for your districts.",
    $(target) ? show : null);
}
