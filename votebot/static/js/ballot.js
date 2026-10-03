// The ballot page. The left pane (chrome.js) holds "Your ballot" with your address and this
// page's form under it, the list of sections, and links to the other pages at the bottom (on a
// phone, a top bar; see topbar.js); the main area has the progress strip and the races, each
// one collapsible.

import { isPaneCollapsed, narrow, onPaneToggle, setPaneCollapsed } from "./chrome.js";
import { rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import { openCompare } from "./compare.js";
import { syncMap } from "./district-map.js";
import {
  $, autosave, closeOnBackdrop, dialogHead, extLink, h, initials, onFrame, onReturn, safeUrl, setStatus as showStatus, slug, trackHeight,
} from "./dom.js";
import { formatDate, listed, plural } from "./format.js";
import { hydrateIcons, icon } from "./icons.js";
import { keyDatesCard } from "./key-dates.js";
import { GROUP_LABELS, GROUP_ORDER, STATES, candidatePills } from "./labels.js";
import { Picks, WRITE_IN, onPicksChanged } from "./picks.js";
import { buildPrintSheet } from "./print.js";
import { currentEngine, searchHref } from "./search.js";
import { badgeList, likelyFlag, likelyUnflagged, raceMoney, renderTabs } from "./source-cards.js";
import { ADDRESS_CARD, LAST_LOOKUP, readJson, setUiPref, settingsStamp, uiPref, writeJson } from "./storage.js";
import { attachSuggestions } from "./suggest.js";
import { hideToast, showToast } from "./toast.js";
import { openPanel } from "./topbar.js";

const form = $("#lookup-form");
const addressInput = $("#address");
const electionSelect = $("#election");
const partyField = $("#party-field");
const partySelect = $("#party");
const submitButton = $("#lookup-btn");
const cancelButton = $("#cancel-change");
const addressCard = $("#address-card");
const statusBox = $("#status");
const welcome = $("#welcome");
const loading = $("#loading");
const result = $("#result");
const strip = $("#progress-strip");
const tools = $("#ballot-tools");
const viewMenu = $("#view-menu");
const nextButton = $("#next-race");
const jump = $("#jump");
const details = $("#details");
const compareDialog = $("#compare");
const printDialog = $("#print-dialog");

let ballot = null;
let picks = null;
let shownRequest = null; // the request behind the ballot on screen, not one that failed since
let pendingLookup = null; // the AbortController of the lookup still running
const redraw = new Map(); // race or proposition key -> redraws its card from the saved picks
let sectionCounts = []; // the left pane's section list: [{ element, keys, maybe }]
let sectionLinks = []; // and its links: [{ id, link }], the section's id and the link to it
let currentSection = null; // the id of the section marked as the one on screen
let lastJumped = null; // the race "Next race to pick" went to last
let editingDistricts = false;

// ---- status line (only while working, or when something went wrong) -------------------

function setStatus(message, kind = "info") {
  showStatus(statusBox, message, kind);
  if (message && kind === "error") showAddressPanel(); // the line is under the address
}

// ---- the address: a saved card, or the form ------------------------------------------

// The address and the form: on a phone, the top bar's panel; wider, the pane, unfolded.
function showAddressPanel() {
  openPanel("address");
  setPaneCollapsed(false);
}

function showForm(show) {
  form.hidden = !show;
  addressCard.hidden = show;
  cancelButton.hidden = !ballot;
  if (show) showAddressPanel();
  else openPanel(null);
  if (show) addressInput.focus();
}

$("#change-address").addEventListener("click", () => showForm(true));
cancelButton.addEventListener("click", () => showForm(false));

// ---- elections dropdown -------------------------------------------------------------

function describeElections(elections) {
  const general = elections.find((e) => e.type === "GE");
  const others = elections.length - (general ? 1 : 0);
  if (general) return others ? `${general.name} + ${others} special` : general.name;
  return elections.map((e) => e.name).join(", ");
}

async function loadElections(selected) {
  try {
    const dates = await api.get("/api/elections");
    electionSelect.replaceChildren(
      h("option", { value: "" }, "Next election"),
      ...dates.map((d) =>
        h("option", { value: d.date, "data-primaries": d.has_primaries ? "1" : null, selected: d.date === selected },
          `${formatDate(d.date)} · ${describeElections(d.elections)}`),
      ),
    );
  } catch {
    // keep "Next election"; the ballot lookup reports real problems
  }
  syncPartyField();
}

function syncPartyField() {
  const option = electionSelect.selectedOptions[0];
  partyField.hidden = !option?.dataset.primaries;
}

// ---- lookup -------------------------------------------------------------------------

function readForm() {
  const request = { address: addressInput.value.trim() };
  if (electionSelect.value) request.election_date = electionSelect.value;
  if (!partyField.hidden && partySelect.value) request.party = partySelect.value;
  if (shownRequest?.address === request.address) {
    if (shownRequest.precincts) request.precincts = shownRequest.precincts;
    if (shownRequest.districts) request.districts = shownRequest.districts;
  }
  return request;
}

// keepForm: leave the address form open afterwards ("Change" on another page opened it).
// keepBallot: leave the ballot showing meanwhile (new precincts), rather than a skeleton.
// A new lookup cancels one still running, so an older answer can't replace a newer ballot.
async function lookup(request, { keepForm = false, keepBallot = false } = {}) {
  pendingLookup?.abort();
  const controller = new AbortController();
  pendingLookup = controller;
  setStatus("Looking up your ballot…", "busy");
  submitButton.disabled = true;
  // Only a lookup that isn't cached takes long enough to see this.
  const skeleton = keepBallot ? null : setTimeout(() => showLoading(true), 300);
  try {
    const found = await api.post("/api/ballot", request, { signal: controller.signal });
    if (controller.signal.aborted) return; // cancelled as its answer arrived
    ballot = found;
    shownRequest = request;
    writeJson(LAST_LOOKUP, request);
    picks = new Picks(ballot.election_date);
    editingDistricts = false;
    render();
    setStatus("");
    if (keepForm) cancelButton.hidden = false;
    else showForm(false);
  } catch (error) {
    if (controller.signal.aborted) return;
    showLoading(false);
    setStatus(error.message, "error");
    if (!ballot) showForm(true);
  } finally {
    clearTimeout(skeleton);
    if (pendingLookup === controller) {
      pendingLookup = null;
      submitButton.disabled = false;
    }
  }
}

// A skeleton ballot, saying a first lookup takes a while, in place of the ballot or the welcome.
function showLoading(show) {
  loading.hidden = !show;
  jump.hidden = show || !ballot; // the sections are the old ballot's
  if (show) {
    welcome.hidden = true;
    result.hidden = true;
  } else if (ballot) {
    result.hidden = false;
  } else {
    welcome.hidden = false;
  }
}

// ---- rendering ----------------------------------------------------------------------

function render() {
  redraw.clear();
  renderAddress();
  renderHeader();
  renderKeyDates();
  renderDistricts();
  syncMap(ballot);
  renderMessages();
  renderGroups();
  renderMaybe();
  renderMeasures();
  renderSections();
  applyHidePicked();
  updateProgress();
  loading.hidden = true;
  welcome.hidden = true;
  result.hidden = false;
  markCurrentSection();
}

function renderAddress() {
  const { location } = ballot;
  const card = {
    address: shownRequest.address,
    place: [location.city, location.county && `${location.county} County`].filter(Boolean).join(" · "),
    matched: location.matched_address || "",
    election: electionLine(),
  };
  showAddress(card);
  writeJson(ADDRESS_CARD, card); // the other pages show it too
}

// The numbers the voter can change: what each is called, and the highest there is.
const EDITABLE = {
  cd: ["U.S. House district", 38], sd: ["State Senate district", 31], hd: ["State House district", 150],
  sboe: ["State Board of Education district", 15], commissioner: ["Commissioner precinct", 4],
  jp: ["Justice of the peace and constable precinct", 99],
};
const DISTRICT_NAMES = { cd: "U.S. House", sd: "State Senate", hd: "State House", sboe: "SBOE" };

function shownNumbers(d) {
  return { cd: d.cd ?? null, sd: d.sd ?? null, hd: d.hd ?? null, sboe: d.sboe ?? null,
    commissioner: d.commissioner ?? null, jp: d.jp ?? d.constable ?? null };
}

// A district's number, or a box in its place after the pencil (``edit``: its kind). A seat that
// isn't up is grey, and a number races wait on, missing, is amber.
function district(label, value, { notUp = false, missing = false, title = null, edit = null } = {}) {
  if (edit) {
    const [name, max] = EDITABLE[edit];
    return h("label", { class: "district editing", title: name }, label ? [label, " "] : null,
      h("input", { type: "number", class: "district-input", name: edit, min: "1", max: String(max), inputmode: "numeric",
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
const PRECINCT_NAMES = { commissioner: "Commissioner", jp: "JP" };
const PRECINCT_KINDS = Object.keys(PRECINCT_NAMES);
function precinctSources(d) {
  const groups = new Map();
  for (const kind of PRECINCT_KINDS) {
    const source = d.precinct_sources?.[kind];
    const value = kind === "jp" ? d.jp ?? d.constable : d[kind];
    if (source && (source === "you" || value != null)) groups.set(source, [...(groups.get(source) || []), PRECINCT_NAMES[kind]]);
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

const NOT_UP_LABELS = { sd: "State Senate", sboe: "SBOE" };
function notUpNote(d) {
  const names = (d.not_up || []).filter((kind) => d[kind] != null).map((kind) => `${NOT_UP_LABELS[kind]} ${d[kind]}`);
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
  const names = (d.entered || []).map((kind) => DISTRICT_NAMES[kind]);
  return names.length ? ` ${listed(names)} ${names.length > 1 ? "districts" : "district"} you entered.` : "";
}

function renderDistricts() {
  const { location, districts: d } = ballot;
  const shown = shownNumbers(d);
  const waiting = ballot.maybe.find((section) => section.id === "precinct");
  const missing = PRECINCT_KINDS.filter((kind) => shown[kind] == null);
  const prompted = Boolean(waiting) && missing.length > 0;
  const edit = (kind) => (editingDistricts ? kind : null); // boxes in place of the numbers, after the pencil
  const needed = (kind) => prompted && missing.includes(kind);
  const school = location.school_district?.replace(/\bIndependent School District\b/, "ISD");
  const precinct = d.election_precinct;
  const notUp = new Set(d.not_up || []);

  const rows = [
    districtRow(
      district("U.S. House", d.cd, { edit: edit("cd") }),
      district("State Senate", d.sd, { notUp: notUp.has("sd"), edit: edit("sd") }),
      district("State House", d.hd, { edit: edit("hd") }),
      district(h("abbr", { title: "State Board of Education" }, "SBOE"), d.sboe, { notUp: notUp.has("sboe"), edit: edit("sboe") }),
    ),
    districtRow(
      location.county && district("County", location.county),
      precinct && district("Precinct", precinct.name, { title: `Election precinct, from the map “${precinct.map_label}”` }),
      district("Commissioner", d.commissioner, { edit: edit("commissioner"), missing: needed("commissioner") }),
      district([h("abbr", { title: "Justice of the Peace" }, "JP"), " & Constable"], shown.jp,
        { edit: edit("jp"), missing: needed("jp") }),
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
    editingDistricts ? null : notUpNote(d),
  ].filter(Boolean);
  $("#districts-card").replaceChildren(
    h("div", { class: "districts-head" }, h("h2", { id: "districts-card-title" }, "Your districts"), districtActions(d)),
    ...(editingDistricts ? [districtsForm(rows, shown)] : rows),
    h("p", { class: "fine" }, "Districts from the US Census and the Texas Legislative Council.",
      enteredDistricts(d), precinct ? electionPrecinctSource(precinct) : "", precinctSources(d)),
  );
  $("#districts-card").hidden = false;
}

// The pencil, which opens every number for editing, and Reset, which works once any number is the voter's.
function districtActions(d) {
  const label = "Edit your districts";
  const pencil = h("button", { type: "button", class: "icon-only", id: "districts-edit", "aria-label": label, title: label,
    "aria-pressed": String(editingDistricts), on: { click: () => setEditingDistricts(!editingDistricts) } }, icon("edit"));
  const yours = Boolean(d.entered?.length) || Object.values(d.precinct_sources || {}).includes("you");
  const back = yours ? "Reset to the districts VoteBot looked up"
    : "Reset: nothing to reset, these are the districts VoteBot looked up";
  const reset = h("button", { type: "button", class: "icon-only", "aria-label": back, title: back, disabled: !yours,
    on: { click: () => updateDistricts(null) } }, icon("reset"));
  return h("div", { class: "district-actions" }, pencil, reset);
}

// The card's lines with their open boxes. It sends only the numbers the voter changed, on top of
// the ones they entered before; the rest keep following the address, the county and Ballotpedia.
function districtsForm(rows, shown) {
  const cancel = h("button", { class: "btn small ghost", type: "button", on: { click: () => setEditingDistricts(false) } }, "Cancel");
  const buttons = [h("button", { class: "btn small primary", type: "submit" }, "Update my ballot"), cancel];
  const form = h("form", { class: "districts-form", id: "districts-form", "aria-label": "Your districts" },
    rows, h("div", { class: "button-row" }, buttons));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const districts = { ...shownRequest.districts };
    const precincts = { ...shownRequest.precincts };
    let changed = false;
    for (const input of form.querySelectorAll(".district-input")) {
      const kind = input.name;
      const typed = parseInt(input.value, 10);
      const value = typed > 0 ? typed : null;
      if (value === shown[kind]) continue;
      changed = true;
      if (kind in DISTRICT_NAMES) districts[kind] = value;
      else precincts[kind] = value;
      if (kind === "jp") precincts.constable = value;
    }
    if (changed) updateDistricts({ districts, precincts });
    else setEditingDistricts(false);
  });
  return form;
}

const PRECINCT_WORDS = { commissioner: "commissioner", jp: "justice of the peace" };

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
  const asked = one ? `your ${PRECINCT_WORDS[missing[0]]} precinct` : "your commissioner and justice of the peace precincts";
  const precinct = ballot.districts.election_precinct;
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

function setEditingDistricts(on) {
  editingDistricts = on;
  renderDistricts();
  (on ? firstEmptyBox() : $("#districts-edit"))?.focus();
}

function openPrecincts() {
  if (!editingDistricts) {
    editingDistricts = true;
    renderDistricts();
  }
  const field = firstEmptyBox(PRECINCT_KINDS);
  field.scrollIntoView({ block: "center" });
  field.focus({ preventScroll: true });
}

// ``entered``: { districts, precincts } the voter gave, or null to go back to the looked-up ones.
async function updateDistricts(entered) {
  const { precincts: _precincts, districts: _districts, ...request } = shownRequest;
  for (const [key, numbers] of Object.entries(entered || {})) {
    if (Object.keys(numbers).length) request[key] = numbers;
  }
  const before = ballot;
  await lookup(request, { keepBallot: true });
  if (ballot === before) return;
  $("#districts-edit")?.focus();
  const waiting = ballot.maybe.some((section) => section.id === "precinct");
  const target = waiting ? "#maybe-precinct .race" : "#group-precinct .race";
  const show = { label: "Show", run: () => { const first = $(target); if (first) goTo(first); } };
  showToast(waiting ? "Your ballot is updated. Some races still depend on your commissioner or JP precinct."
    : "Your ballot is updated for your districts.",
    $(target) ? show : null);
}

// "November 3, 2026 · 2026 November General Election": under the ballot's heading, and the
// address card's last line.
function electionLine() {
  return [formatDate(ballot.election_date), ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · ");
}

function renderHeader() {
  const state = STATES[ballot.location.state];
  const site = state?.registration ? null : state?.site;
  $("#ballot-sub").replaceChildren(
    electionLine(),
    ...(site ? [" · Official info: ", extLink(site.url, site.label)] : []),
  );
}

function renderKeyDates() {
  const card = $("#key-dates");
  const contents = keyDatesCard(ballot);
  card.replaceChildren(...(contents || []).filter(Boolean));
  card.hidden = !contents;
}

const showPickedButton = h("button", { type: "button", class: "link-btn", on: { click: () => setHidePicked(false) } }, "Show them");
const hidingNote = h("p", { class: "notice", hidden: true }, "Races you've picked are hidden. ", showPickedButton);

function renderMessages() {
  $("#messages").replaceChildren(
    hidingNote,
    ...ballot.warnings.map((w) => h("p", { class: "notice notice-warn" }, w)),
    ...ballot.notes.map((n) => h("p", { class: "notice" }, n)),
  );
}

function renderGroups() {
  const sections = [];
  for (const group of GROUP_ORDER) {
    const groupRaces = ballot.races.filter((r) => r.group === group);
    if (!groupRaces.length) continue;
    const id = `group-${group}`;
    sections.push(
      h("section", { class: "group", id, "aria-labelledby": `${id}-title` },
        h("h2", { class: "group-title", id: `${id}-title` }, GROUP_LABELS[group]),
        groupRaces.map(raceCard)),
    );
  }
  $("#groups").replaceChildren(...sections);
}

// The left pane's list of sections, each with how many of its races are picked.
function renderSections() {
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
  for (const group of GROUP_ORDER) {
    const keys = ballot.races.filter((r) => r.group === group).map((r) => r.key);
    if (keys.length) add(`group-${group}`, GROUP_LABELS[group], keys);
  }
  for (const section of ballot.maybe) add(`maybe-${section.id}`, section.title, section.races.map((r) => r.key), true);
  if (ballot.measures.length) add("measures-section", "Propositions", measureKeysOf(ballot));
  $("#jump-list").replaceChildren(...items);
  jump.hidden = !items.length;
}

// "5 of 12 races · 1 of 2 propositions", one bar for both, and the section counts. The races
// that may not be on the ballot aren't counted.
function updateProgress() {
  const raceKeys = ballot.races.map((r) => r.key);
  const measureKeys = measureKeysOf(ballot);
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

// ---- collapsible cards --------------------------------------------------------------

// A card whose heading is a button that shows or hides its body. The heading stays under the
// strip while its card scrolls by. Collapsed, it's one line: the race on the left, the pick
// ("✓ James Talarico") on the right; the pick shows expanded too, once there is one. ✕ Clear,
// next to it, takes the pick back, with Undo.
function collapsibleCard(key, { title, meta, body }) {
  const bodyId = `body-${slug(key)}`;
  const status = h("span", { class: "race-status" });
  const fold = () => {
    picks.setCollapsed(key, !picks.isCollapsed(key));
    redraw.get(key)?.();
  };
  const toggle = h("button", { type: "button", class: "race-toggle", "aria-controls": bodyId, on: { click: fold } },
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "race-name" }, title),
    status,
    meta ? h("span", { class: "race-meta" }, meta) : null);
  const clearPick = () => {
    const before = picks.picked(key);
    picks.set(key, []);
    refresh(key);
    toggle.focus();
    showToast(`Cleared your pick for ${title}.`, {
      label: "Undo",
      run: () => {
        picks.set(key, before);
        refresh(key);
      },
    });
  };
  const clear = h("button", { type: "button", class: "icon-btn with-icon clear-pick", hidden: true,
    "aria-label": `Clear your pick for ${title}`, title: "Clear pick", on: { click: clearPick } }, icon("x"), "Clear");
  const bodyElement = h("div", { class: "race-body", id: bodyId }, body);
  const article = h("article", { class: "race", "data-race": key },
    h("header", { class: "race-head" }, h("h3", {}, toggle), clear),
    bodyElement);
  return {
    article,
    show(statusText, done) {
      const collapsed = picks.isCollapsed(key);
      article.classList.toggle("collapsed", collapsed);
      article.classList.toggle("has-pick", done);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      bodyElement.hidden = collapsed;
      status.textContent = statusText;
      status.title = statusText;
      status.classList.toggle("done", done);
      clear.hidden = !done;
    },
  };
}

// A declared write-in's name says so, as a typed write-in's does: the voter writes it in.
function writeInName(candidate) {
  return candidate && (candidate.write_in ? `${candidate.name} (write-in)` : candidate.name);
}

function pickedText(race, picked) {
  if (!picked.length) return "Not picked yet";
  return picked
    .map((key) => (key === WRITE_IN
      ? picks.writeInLabel(race.key, "Write-in (no name yet)")
      : writeInName(race.candidates.find((c) => c.key === key))))
    .filter(Boolean)
    .join(", ");
}

function raceCard(race) {
  const multi = race.seats > 1;
  const meta = [
    multi ? `Vote for up to ${race.seats}` : null,
    race.unexpired ? "Unexpired term" : null,
    race.election_name && !/general election/i.test(race.election_name) ? race.election_name : null,
    race.source === "ballotpedia" ? "Listed by Ballotpedia" : null,
  ].filter(Boolean);
  const body = h("fieldset", { class: "race-options" },
    h("legend", { class: "sr-only" }, `${race.name}: vote for ${multi ? `up to ${race.seats}` : "1"}`),
    race.candidates.length ? null : h("p", { class: "muted" }, "No candidates listed yet."),
    h("ul", { class: "cands" }, race.candidates.map((c) => candidateRow(race, c)), writeInRow(race)));
  const money = raceMoney(race, () => openCompare(compareDialog, race));
  const notes = (race.notes || []).map((note) => h("p", { class: "fine race-note" },
    `${note.source}: ${note.text}`, note.url ? [" ", extLink(note.url, `More on ${note.source}`)] : null));
  const card = collapsibleCard(race.key, {
    title: race.name, meta: meta.join(" · "), body: [...notes, money, body],
  });

  redraw.set(race.key, () => {
    const picked = picks.picked(race.key);
    // Colour the race by its pick's party (neutral when the picks are from different parties).
    const parties = new Set(picked.map((key) => race.candidates.find((c) => c.key === key)?.party || "none"));
    if (parties.size === 1) card.article.dataset.pickParty = [...parties][0];
    else delete card.article.dataset.pickParty;
    card.show(pickedText(race, picked), picked.length > 0);
    for (const row of card.article.querySelectorAll(".cand")) {
      const on = picked.includes(row.dataset.cand);
      row.classList.toggle("picked", on);
      const input = row.querySelector(".pick-input");
      input.checked = on;
      if (multi) input.disabled = !on && picked.length >= race.seats;
      const note = row.querySelector(".write-in-note");
      if (note) note.hidden = !on;
    }
  });
  redraw.get(race.key)();
  return card.article;
}

function avatar(candidate, extraClass = null) {
  const src = safeUrl(candidate.photo_url);
  return src
    ? h("img", { class: ["avatar", extraClass], src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
    : h("span", { class: ["avatar", extraClass], "aria-hidden": "true" }, initials(candidate.name));
}

// What to search the web for: the candidate plus the office and place, so common names find the right person.
function searchQuery(race, candidate) {
  const { county, state_name: stateName } = ballot.location;
  const terms = [candidate.name, race.name];
  if ((race.group === "county" || race.group === "precinct") && county && !race.name.includes(county)) {
    terms.push(`${county} County`);
  }
  if (stateName && !race.name.includes(stateName)) terms.push(stateName);
  if (ballot.election_date) terms.push(ballot.election_date.slice(0, 4));
  return terms.join(" ");
}

function searchLink(race, candidate, className, label) {
  return extLink(searchHref(searchQuery(race, candidate)), label, {
    class: className,
    title: `Search ${currentEngine().label} for ${candidate.name}`,
    "aria-label": `Search the web for ${candidate.name} (opens in a new tab)`,
  });
}

function candidateRow(race, candidate) {
  const multi = race.seats > 1;
  const id = slug(candidate.key);
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id: `pick-${id}`, class: "pick-input",
    on: { change: (event) => choose(race, candidate.key, event.target.checked) } });

  const noteText = picks.note(candidate.key);
  const textarea = h("textarea", { id: `note-${id}-text`, rows: "2", placeholder: "Your thoughts on this candidate…" });
  textarea.value = noteText;
  const saved = h("span", { class: "saved", "aria-live": "polite" });
  const noteBox = h("div", { class: "note", id: `note-${id}`, hidden: !noteText },
    h("label", { for: `note-${id}-text` }, `Your note on ${candidate.name}`), textarea, saved);
  const openNote = () => {
    const opening = noteBox.hidden;
    noteBox.hidden = !opening;
    noteButton.setAttribute("aria-expanded", String(opening));
    if (opening) textarea.focus();
  };
  const noteButton = h("button", {
    type: "button", class: ["icon-btn note-btn", noteText && "has-note"],
    "aria-expanded": String(Boolean(noteText)), "aria-controls": `note-${id}`, on: { click: openNote },
  }, "✎ Note");
  autosave(textarea, () => {
    picks.setNote(candidate.key, textarea.value);
    hideToast(); // an Undo of "Clear picks" would now lose this
    noteButton.classList.toggle("has-note", Boolean(textarea.value.trim()));
    saved.textContent = "Saved";
    setTimeout(() => { saved.textContent = ""; }, 1500);
  }, 400);

  const sources = candidate.cards.length;
  const unflagged = likelyUnflagged(candidate); // likely matches with no badge to show the "?"
  const detailsButton = h("button", { type: "button", class: "icon-btn", disabled: !sources,
    on: { click: () => showDetails(race, race.candidates.indexOf(candidate)) } },
    sources ? `Details · ${plural(sources, "source")}` : "No details",
    unflagged.length ? likelyFlag(`Likely match: ${unflagged.join(", ")}`) : null);

  return h(
    "li",
    { class: "cand", "data-cand": candidate.key, "data-party": candidate.party || null },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: `pick-${id}`, class: "cand-label" },
        avatar(candidate),
        h("span", { class: "cand-text" },
          h("span", { class: "cand-name" }, candidate.name),
          h("span", { class: "cand-sub" }, candidatePills(candidate)))),
      h("div", { class: "cand-actions" }, noteButton, detailsButton, searchLink(race, candidate, "icon-btn", "Web search ↗"))),
    badgeList(candidate),
    noteBox,
  );
}

// The last row of every race: a blank for someone who isn't listed. Typing a name picks
// it; emptying the box takes the pick back.
function writeInRow(race) {
  const multi = race.seats > 1;
  const id = `writein-${slug(race.key)}`;
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id, class: "pick-input" });
  const name = h("input", {
    type: "text", id: `${id}-name`, class: "write-in-name", maxlength: "80", autocomplete: "off",
    placeholder: "Someone else's name", "aria-label": `Write-in name for ${race.name}`,
  });
  name.value = picks.writeIn(race.key);
  input.addEventListener("change", () => {
    choose(race, WRITE_IN, input.checked);
    if (input.checked) name.focus();
  });
  autosave(name, () => {
    picks.setWriteIn(race.key, name.value);
    const typed = Boolean(name.value.trim());
    const picked = picks.picked(race.key).includes(WRITE_IN);
    const full = multi && !picked && picks.picked(race.key).length >= race.seats;
    if (typed !== picked && !full) choose(race, WRITE_IN, typed);
    else refresh(race.key); // the collapsed line shows the new name
  }, 300);
  const note = STATES[ballot.location.state]?.writeInNote;
  const hint = note && race.candidates.some((c) => c.write_in) ? `${note} The ones who filed for this race are listed above.` : note;
  return h(
    "li",
    { class: "cand write-in", "data-cand": WRITE_IN },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: id, class: "write-in-label" }, "Write-in"),
      name),
    hint ? h("p", { class: "fine write-in-note", hidden: true }, hint) : null,
  );
}

// ---- picking ------------------------------------------------------------------------

function choose(race, key, checked) {
  let keys = picks.picked(race.key).filter((k) => k !== key);
  if (checked) keys = race.seats > 1 ? [...keys, key] : [key];
  picks.set(race.key, keys);
  // A write-in doesn't fold the race: its name box would go while the voter types.
  settle(race.key, checked && key !== WRITE_IN && keys.length >= race.seats);
}

function refresh(key) {
  hideToast(); // an Undo of "Clear picks" would now lose this change
  redraw.get(key)?.();
  updateProgress();
}

// After a pick that fills the race: with "Collapse a race when I pick" (View), fold the race to
// one line, and bring its heading back into view if that left it above the strip.
function settle(key, filled) {
  const fold = filled && uiPref("collapseOnPick");
  if (fold) picks.setCollapsed(key, true);
  refresh(key);
  const card = fold ? cardFor(key) : null;
  if (card && card.getBoundingClientRect().top < strip.getBoundingClientRect().bottom) card.scrollIntoView({ block: "start" });
}

function setAllCollapsed(collapsed) {
  picks.setCollapsed([...redraw.keys()], collapsed);
  for (const draw of redraw.values()) draw();
}

// ---- maybe sections, precincts, propositions ----------------------------------------

function precinctLink() {
  return h("p", { class: "precinct-link" },
    h("button", { type: "button", class: "link-btn", on: { click: openPrecincts } }, "Enter your commissioner and JP precincts"));
}

function renderMaybe() {
  $("#maybe").replaceChildren(
    ...ballot.maybe.map((section) =>
      h("section", { class: "group maybe", id: `maybe-${section.id}`, "aria-labelledby": `maybe-${section.id}-title` },
        h("h2", { class: "group-title", id: `maybe-${section.id}-title` }, section.title),
        h("p", { class: "muted explain" }, section.explanation),
        section.id === "precinct" ? precinctLink() : null,
        section.races.map(raceCard))),
  );
}

function measureCard(measure) {
  const key = `measure:${measure.key}`;
  const name = `measure-${slug(measure.key)}`;
  const options = [["for", "For"], ["against", "Against"]].map(([value, label]) => {
    const vote = () => {
      picks.set(key, [value]);
      settle(key, true);
    };
    const input = h("input", { type: "radio", name, id: `${name}-${value}`, value, on: { change: vote } });
    return { value, input, label: h("label", { class: "measure-option", for: `${name}-${value}` }, input, label) };
  });
  const body = [
    measure.summary ? h("p", {}, measure.summary) : null,
    h("fieldset", { class: "measure-options" }, h("legend", { class: "sr-only" }, measure.title), options.map((o) => o.label)),
    measure.url ? h("p", { class: "fine" }, extLink(measure.url, "Read more on Ballotpedia")) : null,
  ];
  const card = collapsibleCard(key, { title: measure.title, meta: measure.district, body });
  card.article.classList.add("measure");
  redraw.set(key, () => {
    const vote = picks.picked(key)[0];
    for (const option of options) option.input.checked = option.value === vote;
    card.show(vote ? `Voting ${vote}` : "Not decided yet", Boolean(vote));
  });
  redraw.get(key)();
  return card.article;
}

const measureKeysOf = (b) => b.measures.map((m) => `measure:${m.key}`);

function renderMeasures() {
  $("#measures").replaceChildren(
    ballot.measures.length
      ? h("section", { class: "group", id: "measures-section" },
          h("h2", { class: "group-title" }, "Propositions"), ballot.measures.map(measureCard))
      : "",
  );
}

// ---- details dialog -----------------------------------------------------------------

// One of a race's candidates, by ``index``. ‹ and › step through the others without closing
// the dialog; ``focus`` ("previous" or "next") keeps the focus on the one that was pressed.
function showDetails(race, index, focus = null) {
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
      h("p", { class: "cand-sub" }, candidatePills(candidate))),
  ], steps.previous, steps.next);
  details.replaceChildren(
    head,
    tabs,
    h("div", { class: "details-foot" }, searchLink(race, candidate, "btn ghost", `Search the web for ${candidate.name} ↗`), pickButton),
  );
  if (!details.open) details.showModal();
  details.scrollTop = 0;
  const pressed = steps[focus];
  (pressed && !pressed.disabled ? pressed : close).focus();
}

for (const dialog of [details, compareDialog, printDialog]) closeOnBackdrop(dialog);

// ---- print / clear ------------------------------------------------------------------

const walletChoice = $("#print-wallet");
for (const radio of printDialog.querySelectorAll('input[name="print-layout"]')) {
  radio.addEventListener("change", () => { $("#print-notes").disabled = walletChoice.checked; }); // notes don't fit
}
$("#print-btn").addEventListener("click", () => printDialog.showModal());
printDialog.addEventListener("close", () => {
  if (printDialog.returnValue !== "print" || !ballot) return;
  const wallet = walletChoice.checked;
  buildPrintSheet(ballot, picks, { includeNotes: $("#print-notes").checked && !wallet, includeBlank: $("#print-blank").checked, wallet });
  setTimeout(() => window.print(), 50);
});

// Clears at once, and offers to put everything back.
$("#clear-picks").addEventListener("click", () => {
  if (!ballot) return;
  if (picks.isEmpty()) {
    showToast("No picks or notes to clear.");
    return;
  }
  const cleared = picks.clear();
  render();
  showToast("Cleared your picks and notes.", {
    label: "Undo",
    run: () => {
      picks.restore(cleared);
      render();
    },
  });
});

// ---- view: collapse, only unpicked races, next race, j/k -----------------------------

// "Only races I haven't picked": hides the races picked so far. One picked meanwhile stays
// until this runs again (switching it on, a new ballot), so it doesn't vanish mid-pick.
function applyHidePicked() {
  const on = Boolean(uiPref("hidePicked"));
  for (const card of result.querySelectorAll(".race")) {
    card.classList.toggle("hidden-picked", on && picks.has(card.dataset.race));
  }
  $("#hide-picked").checked = on;
  hidingNote.hidden = !on;
  viewMenu.classList.toggle("filtered", on);
}

function setHidePicked(on) {
  setUiPref("hidePicked", on);
  if (!ballot) return;
  applyHidePicked();
  markCurrentSection(); // the marked section may have gone
}

$("#hide-picked").addEventListener("change", (event) => setHidePicked(event.target.checked));
$("#collapse-on-pick").checked = Boolean(uiPref("collapseOnPick"));
$("#collapse-on-pick").addEventListener("change", (event) => setUiPref("collapseOnPick", event.target.checked));
$("#expand-all").addEventListener("click", () => {
  setAllCollapsed(false);
  viewMenu.open = false;
});
$("#collapse-all").addEventListener("click", () => {
  setAllCollapsed(true);
  viewMenu.open = false;
});

// The View menu closes like a menu: a click elsewhere, or Esc.
document.addEventListener("click", (event) => {
  if (viewMenu.open && !viewMenu.contains(event.target)) viewMenu.open = false;
});
viewMenu.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !viewMenu.open) return;
  event.preventDefault();
  viewMenu.open = false;
  viewMenu.querySelector("summary").focus();
});

function cardFor(key) {
  return result.querySelector(`.race[data-race="${CSS.escape(key)}"]`);
}

// Scrolls a race's card to just below the strip and focuses its heading. ``open`` expands
// it first if it's collapsed.
function goTo(card, { open = false } = {}) {
  const key = card.dataset.race;
  if (open && picks.isCollapsed(key)) {
    picks.setCollapsed(key, false);
    redraw.get(key)?.();
  }
  card.scrollIntoView({ block: "start" });
  card.querySelector(".race-toggle").focus({ preventScroll: true });
}

// The first race or proposition without a pick, after the one in focus (or the one it went
// to last), round to the start. The races that may not be on the ballot are skipped, as the
// progress skips them.
nextButton.addEventListener("click", () => {
  if (!ballot) return;
  const keys = [...ballot.races.map((r) => r.key), ...measureKeysOf(ballot)];
  const from = keys.indexOf(document.activeElement?.closest(".race")?.dataset.race ?? lastJumped) + 1;
  for (let i = 0; i < keys.length; i += 1) {
    const key = keys[(from + i) % keys.length];
    if (!picks.has(key)) {
      lastJumped = key;
      goTo(cardFor(key), { open: true });
      return;
    }
  }
});

// j and k: the next and previous race on the page, from the one in focus, or else from the
// one at the top of the window. Typing in a box, or an open dialog, leaves them alone.
document.addEventListener("keydown", (event) => {
  if (!ballot || result.hidden || (event.key !== "j" && event.key !== "k")) return;
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
});

// ---- phones ---------------------------------------------------------------------------

// On a phone (or a narrow window) the section chips join the sticky strip, and View, Clear
// picks and Print move under the heading, where they scroll away. So what stays in view is
// the progress, Next and the sections. With the left pane folded, the chips join the strip too.
function placeForWidth() {
  if (narrow.matches) $(".ballot-head").after(tools);
  else strip.append(tools);
  if (narrow.matches || isPaneCollapsed()) strip.append(jump); // the chips' row last
  else $(".side-bottom").before(jump);
}
narrow.addEventListener("change", placeForWidth);
onPaneToggle(placeForWidth);
placeForWidth();

// Links to a section, Next and j/k scroll to just below the strip, however tall it is, and
// each race's heading sticks right under it (--strip-h).
trackHeight(strip, "--strip-h", (height) => {
  document.documentElement.style.scrollPaddingTop = `${height + 12}px`;
});

// ---- the section on screen ------------------------------------------------------------

// Marks the section on screen in the section list: the last one whose top has gone under the
// strip (the first until then, the last at the foot of the page). Where the list is a row of
// chips (a phone), the row scrolls sideways to show it.
function markCurrentSection() {
  if (!ballot || result.hidden) return;
  const shown = sectionLinks.filter(({ id }) => document.getElementById(id)?.offsetParent); // not hidden by the filter
  if (!shown.length) return;
  const line = strip.getBoundingClientRect().bottom + 8;
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

const markSoon = onFrame(markCurrentSection);
addEventListener("scroll", markSoon, { passive: true });
addEventListener("resize", markSoon);

// ---- start --------------------------------------------------------------------------

form.addEventListener("submit", (event) => {
  event.preventDefault();
  lookup(readForm());
});
electionSelect.addEventListener("change", syncPartyField);
attachSuggestions(addressInput);

hydrateIcons();

// Settings live on their own page. If they changed while this page was open (in another tab,
// or kept by the browser for the Back button), start over so the ballot reflects them.
const settingsSeen = settingsStamp();
onReturn(() => {
  if (settingsStamp() !== settingsSeen) location.reload();
});

// Picks made in another tab show here too, and a pick made here doesn't undo them.
onPicksChanged(() => {
  if (!ballot) return;
  picks = new Picks(ballot.election_date);
  render();
});

async function start() {
  const fromHash = new URLSearchParams(location.hash.slice(1));
  const changing = fromHash.has("change"); // "Change" on another page's address card
  if (changing) history.replaceState(null, "", location.pathname + location.search);
  const initial = fromHash.get("address")
    ? { address: fromHash.get("address"), ...(fromHash.get("date") ? { election_date: fromHash.get("date") } : {}) }
    : readJson(LAST_LOOKUP, null);
  if (initial?.address) {
    // Show the remembered address right away; the lookup fills in the rest.
    addressInput.value = initial.address;
    showAddress(rememberedCard(initial.address));
    form.hidden = true;
    addressCard.hidden = false;
  } else {
    showAddressPanel(); // the form is the first thing to fill in
  }
  if (changing) showForm(true);
  await loadElections(initial?.election_date);
  if (initial?.address) {
    if (initial.party) partySelect.value = initial.party;
    lookup(initial, { keepForm: changing });
  }
}

start();
