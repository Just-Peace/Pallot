// The ballot page. The left pane holds "Your ballot" with your address under it, the list of
// sections, and links to the other pages at the bottom (on a phone, a top bar; see topbar.js);
// the main area has the progress strip and the races, each one collapsible.

import { rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import { openCompare } from "./compare.js";
import { extLink, formatDate, h, initials, safeUrl, slug } from "./dom.js";
import { hydrateIcons } from "./icons.js";
import { GROUP_LABELS, GROUP_ORDER, STATES, districtLine, partyPill } from "./labels.js";
import {
  Picks, WRITE_IN, loadLastLookup, loadUi, saveAddressCard, saveLastLookup, saveUi, settingsStamp,
} from "./picks.js";
import { buildPrintSheet } from "./print.js";
import { currentEngine, searchHref } from "./search.js";
import { badgeList, likelyFlag, likelyUnflagged, raceMoney, renderTabs } from "./source-cards.js";
import { attachSuggestions } from "./suggest.js";
import { hideToast, showToast } from "./toast.js";
import { openPanel } from "./topbar.js";

const $ = (selector) => document.querySelector(selector);
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

// ---- status line (only while working, or when something went wrong) -------------------

function setStatus(message, kind = "info") {
  statusBox.className = `status status-${kind}`;
  statusBox.textContent = message || "";
  if (message && kind === "error") openPanel("address"); // on a phone, the line is in that panel
}

// ---- the address: a saved card, or the form ------------------------------------------

function showForm(show) {
  form.hidden = !show;
  addressCard.hidden = show;
  cancelButton.hidden = !ballot;
  openPanel(show ? "address" : null);
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
  if (shownRequest?.precincts && shownRequest.address === request.address) request.precincts = shownRequest.precincts;
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
    saveLastLookup(request);
    picks = new Picks(ballot.election_date);
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
  const { location, districts: d } = ballot;
  const school = location.school_district?.replace(/\bIndependent School District\b/, "ISD");
  const card = {
    address: shownRequest.address,
    place: [location.city, location.county && `${location.county} County`].filter(Boolean).join(" · "),
    districts: [districtLine(d), school].filter(Boolean).join(" · "),
    matched: location.matched_address || "",
  };
  showAddress(card);
  saveAddressCard(card); // the other pages show it too
  renderPrecinctNote();
}

const PRECINCTS_FROM = { ballotpedia: "Precincts from Ballotpedia", you: "Precincts you entered" };

// Under the districts: where the precinct numbers came from, and a form to change them (with
// every precinct known there's no "Depends on your precinct" section, and so no other form).
function renderPrecinctNote() {
  const note = $("#address-precincts");
  const editor = $("#precinct-edit");
  const from = PRECINCTS_FROM[ballot.districts.precinct_source];
  note.hidden = !from;
  editor.hidden = true;
  editor.replaceChildren();
  if (!from) return;
  const edit = h("button", { type: "button", class: "link-btn", "aria-expanded": "false", "aria-controls": editor.id }, "Edit");
  edit.addEventListener("click", () => {
    const opening = editor.hidden;
    editor.replaceChildren(opening ? precinctForm() : "");
    editor.hidden = !opening;
    edit.setAttribute("aria-expanded", String(opening));
    if (opening) editor.querySelector("input").focus();
  });
  note.replaceChildren(from, " · ", edit);
}

function renderHeader() {
  const site = STATES[ballot.location.state]?.site;
  $("#ballot-sub").replaceChildren(
    [formatDate(ballot.election_date), ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · "),
    ...(site ? [" · Official info: ", extLink(site.url, site.label)] : []),
  );
}

const showPickedButton = h("button", { type: "button", class: "link-btn" }, "Show them");
const hidingNote = h("p", { class: "notice", hidden: true }, "Races you've picked are hidden. ", showPickedButton);

function renderMessages() {
  const precinct = ballot.maybe.find((section) => section.id === "precinct");
  $("#messages").replaceChildren(
    ...(precinct ? [precinctPrompt(precinct)] : []),
    hidingNote,
    ...ballot.warnings.map((w) => h("p", { class: "notice notice-warn" }, w)),
    ...ballot.notes.map((n) => h("p", { class: "notice" }, n)),
  );
}

// At the top of the ballot while races wait on the voter's precincts: a link to their form.
function precinctPrompt(section) {
  const count = section.races.length;
  const link = h("a", { href: "#maybe-precinct" }, "Enter your precinct numbers");
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const field = $("#maybe-precinct input");
    field.scrollIntoView({ block: "center" });
    field.focus({ preventScroll: true });
  });
  return h("p", { class: "notice" },
    `${count} ${count === 1 ? "race depends" : "races depend"} on your precinct. `, link, " to see which are on your ballot.");
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

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

// "5 of 12 races · 1 of 2 propositions", one bar for both, and the section counts. The races
// that may not be on the ballot aren't counted.
function updateProgress() {
  const countPicked = (keys) => keys.filter((k) => picks.picked(k).length).length;
  const raceKeys = ballot.races.map((r) => r.key);
  const measureKeys = measureKeysOf(ballot);
  const done = countPicked(raceKeys);
  const decided = countPicked(measureKeys);
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
    const picked = keys.filter((k) => picks.picked(k).length).length;
    element.textContent = maybe ? (picked ? `${picked} picked` : String(keys.length)) : `${picked}/${keys.length}`;
    element.classList.toggle("complete", !maybe && picked === keys.length);
  }
}

// ---- collapsible cards --------------------------------------------------------------

// A card whose heading is a button that shows or hides its body. Collapsed, the heading
// is one line: the race on the left, the pick ("✓ James Talarico") on the right.
function collapsibleCard(key, { title, meta, body, headExtras = [] }) {
  const bodyId = `body-${slug(key)}`;
  const status = h("span", { class: "race-status" });
  const toggle = h("button", { type: "button", class: "race-toggle", "aria-controls": bodyId },
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "race-name" }, title),
    status,
    meta ? h("span", { class: "race-meta" }, meta) : null);
  const bodyElement = h("div", { class: "race-body", id: bodyId }, body);
  const article = h("article", { class: "race", "data-race": key },
    h("header", { class: "race-head" }, h("h3", {}, toggle), ...headExtras),
    bodyElement);
  toggle.addEventListener("click", () => {
    picks.setCollapsed(key, !picks.isCollapsed(key));
    redraw.get(key)?.();
  });
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
      return collapsed;
    },
  };
}

function pickedText(race, picked) {
  if (!picked.length) return "Not picked yet";
  return picked
    .map((key) => (key === WRITE_IN
      ? picks.writeInLabel(race.key, "Write-in (no name yet)")
      : race.candidates.find((c) => c.key === key)?.name))
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
  const clearButton = h("button", { class: "link-btn clear-pick", type: "button", hidden: true }, "Clear pick");
  clearButton.addEventListener("click", () => {
    picks.set(race.key, []);
    refresh(race.key);
  });
  const body = h("fieldset", { class: "race-options" },
    h("legend", { class: "sr-only" }, `${race.name}: vote for ${multi ? `up to ${race.seats}` : "1"}`),
    race.candidates.length ? null : h("p", { class: "muted" }, "No candidates listed yet."),
    h("ul", { class: "cands" }, race.candidates.map((c) => candidateRow(race, c)), writeInRow(race)));
  const money = raceMoney(race, () => openCompare(compareDialog, race));
  const card = collapsibleCard(race.key, { title: race.name, meta: meta.join(" · "), body: [money, body], headExtras: [clearButton] });

  redraw.set(race.key, () => {
    const picked = picks.picked(race.key);
    // Colour the race by its pick's party (neutral when the picks are from different parties).
    const parties = new Set(picked.map((key) => race.candidates.find((c) => c.key === key)?.party || "none"));
    if (parties.size === 1) card.article.dataset.pickParty = [...parties][0];
    else delete card.article.dataset.pickParty;
    const collapsed = card.show(pickedText(race, picked), picked.length > 0);
    clearButton.hidden = collapsed || !picked.length;
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

function avatar(candidate, extraClass = "") {
  const src = safeUrl(candidate.photo_url);
  return src
    ? h("img", { class: `avatar ${extraClass}`, src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
    : h("span", { class: `avatar ${extraClass}`, "aria-hidden": "true" }, initials(candidate.name));
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
  const query = searchQuery(race, candidate);
  return h("a", {
    class: className,
    href: searchHref(query),
    target: "_blank",
    rel: "noopener noreferrer",
    title: `Search ${currentEngine().label} for ${candidate.name}`,
    "aria-label": `Search the web for ${candidate.name} (opens in a new tab)`,
  }, label);
}

function candidateRow(race, candidate) {
  const multi = race.seats > 1;
  const id = slug(candidate.key);
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id: `pick-${id}`, class: "pick-input" });
  input.addEventListener("change", () => choose(race, candidate.key, input.checked));

  const noteText = picks.note(candidate.key);
  const textarea = h("textarea", { id: `note-${id}-text`, rows: "2", placeholder: "Your thoughts on this candidate…" });
  textarea.value = noteText;
  const saved = h("span", { class: "saved", "aria-live": "polite" });
  const noteBox = h("div", { class: "note", id: `note-${id}`, hidden: !noteText },
    h("label", { for: `note-${id}-text` }, `Your note on ${candidate.name}`), textarea, saved);
  const noteButton = h("button", {
    type: "button", class: `icon-btn note-btn${noteText ? " has-note" : ""}`,
    "aria-expanded": String(Boolean(noteText)), "aria-controls": `note-${id}`,
  }, "✎ Note");
  noteButton.addEventListener("click", () => {
    const opening = noteBox.hidden;
    noteBox.hidden = !opening;
    noteButton.setAttribute("aria-expanded", String(opening));
    if (opening) textarea.focus();
  });
  let timer;
  const save = () => {
    clearTimeout(timer);
    picks.setNote(candidate.key, textarea.value);
    hideToast(); // an Undo of "Clear picks" would now lose this
    noteButton.classList.toggle("has-note", Boolean(textarea.value.trim()));
    saved.textContent = "Saved";
    setTimeout(() => { saved.textContent = ""; }, 1500);
  };
  textarea.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(save, 400);
  });
  textarea.addEventListener("change", save); // on leaving the box, e.g. for another page

  const sources = candidate.cards.length;
  const unflagged = likelyUnflagged(candidate); // likely matches with no badge to show the "?"
  const detailsButton = h("button", { type: "button", class: "icon-btn", disabled: !sources },
    sources ? `Details · ${plural(sources, "source")}` : "No details",
    unflagged.length ? likelyFlag(`Likely match: ${unflagged.join(", ")}`) : null);
  detailsButton.addEventListener("click", () => showDetails(race, race.candidates.indexOf(candidate)));

  return h(
    "li",
    { class: "cand", "data-cand": candidate.key, "data-party": candidate.party || null },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: `pick-${id}`, class: "cand-label" },
        avatar(candidate),
        h("span", { class: "cand-text" },
          h("span", { class: "cand-name" }, candidate.name),
          h("span", { class: "cand-sub" },
            partyPill(candidate),
            candidate.incumbent ? h("span", { class: "pill" }, "Incumbent") : null,
            candidate.write_in ? h("span", { class: "pill" }, "Write-in") : null))),
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
  let timer;
  const save = () => {
    clearTimeout(timer);
    picks.setWriteIn(race.key, name.value);
    const typed = Boolean(name.value.trim());
    const picked = picks.picked(race.key).includes(WRITE_IN);
    const full = multi && !picked && picks.picked(race.key).length >= race.seats;
    if (typed !== picked && !full) choose(race, WRITE_IN, typed);
    else refresh(race.key); // the collapsed line shows the new name
  };
  name.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(save, 300);
  });
  name.addEventListener("change", save); // on leaving the box, e.g. for another page
  const hint = STATES[ballot.location.state]?.writeInNote;
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
  const fold = filled && loadUi().collapseOnPick;
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

function precinctForm() {
  const d = ballot.districts;
  const field = (name, label) =>
    h("label", { class: "field small" }, label,
      h("input", { type: "number", min: "1", max: "99", inputmode: "numeric", name, value: d[name] ?? null }));
  const precinctForm = h("form", { class: "precinct-form" },
    field("commissioner", "Commissioner precinct"),
    field("jp", "Justice of the Peace precinct"),
    field("constable", "Constable precinct"),
    h("button", { class: "btn", type: "submit" }, "Update my ballot"));
  precinctForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(precinctForm);
    const precincts = {};
    for (const key of ["commissioner", "jp", "constable"]) {
      const value = parseInt(data.get(key), 10);
      if (value > 0) precincts[key] = value;
    }
    lookup({ ...shownRequest, precincts }, { keepBallot: true });
  });
  return precinctForm;
}

function renderMaybe() {
  $("#maybe").replaceChildren(
    ...ballot.maybe.map((section) =>
      h("section", { class: "group maybe", id: `maybe-${section.id}`, "aria-labelledby": `maybe-${section.id}-title` },
        h("h2", { class: "group-title", id: `maybe-${section.id}-title` }, section.title),
        h("p", { class: "muted explain" }, section.explanation),
        section.id === "precinct" ? precinctForm() : null,
        section.races.map(raceCard))),
  );
}

function measureCard(measure) {
  const key = `measure:${measure.key}`;
  const name = `measure-${slug(measure.key)}`;
  const options = [["for", "For"], ["against", "Against"]].map(([value, label]) => {
    const input = h("input", { type: "radio", name, id: `${name}-${value}`, value });
    input.addEventListener("change", () => {
      picks.set(key, [value]);
      settle(key, true);
    });
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
  const pickButton = h("button", { type: "button", class: "btn primary" });
  const syncPickButton = () => {
    const on = picks.isPicked(race.key, candidate.key);
    pickButton.textContent = on ? "✓ Picked (undo)" : `Pick ${candidate.name}`;
    pickButton.classList.toggle("ghost", on);
  };
  pickButton.addEventListener("click", () => {
    choose(race, candidate.key, !picks.isPicked(race.key, candidate.key));
    syncPickButton();
  });
  syncPickButton();
  const multiFull = race.seats > 1 && !picks.isPicked(race.key, candidate.key) && picks.picked(race.key).length >= race.seats;
  pickButton.disabled = multiFull;

  const tabs = h("div", { class: "details-tabs" });
  if (candidate.cards.length) renderTabs(tabs, candidate.cards, `d-${slug(candidate.key)}`);
  else tabs.append(h("p", { class: "muted details-empty" }, "No source has details on this candidate yet."));
  const closeButton = h("button", { type: "button", class: "icon-btn close", "aria-label": "Close" }, "✕");
  closeButton.addEventListener("click", () => details.close());

  const count = race.candidates.length;
  const step = (offset, label, symbol) => {
    const other = race.candidates[index + offset];
    const button = h("button", {
      type: "button", class: "icon-btn step", disabled: !other,
      "aria-label": other ? `${label} candidate: ${other.name}` : `No ${label.toLowerCase()} candidate`,
      title: other ? other.name : null,
    }, symbol);
    button.addEventListener("click", () => showDetails(race, index + offset, label.toLowerCase()));
    return button;
  };
  const steps = count > 1 ? { previous: step(-1, "Previous", "‹"), next: step(1, "Next", "›") } : {};

  details.replaceChildren(
    h("div", { class: "details-head" },
      avatar(candidate, "large"),
      h("div", { class: "details-title" },
        h("h2", { id: "details-name" }, candidate.name),
        h("p", { class: "muted" }, race.name, count > 1 ? ` · ${index + 1} of ${count}` : ""),
        h("p", { class: "cand-sub" }, partyPill(candidate), candidate.incumbent ? h("span", { class: "pill" }, "Incumbent") : null)),
      h("div", { class: "details-nav" }, steps.previous, steps.next, closeButton)),
    tabs,
    h("div", { class: "details-foot" }, searchLink(race, candidate, "btn ghost", `Search the web for ${candidate.name} ↗`), pickButton),
  );
  if (!details.open) details.showModal();
  details.scrollTop = 0;
  const pressed = steps[focus];
  (pressed && !pressed.disabled ? pressed : closeButton).focus();
}

for (const dialog of [details, compareDialog]) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close(); // click on the backdrop
  });
}

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

const setView = (pref, value) => saveUi({ ...loadUi(), [pref]: value });

// "Only races I haven't picked": hides the races picked so far. One picked meanwhile stays
// until this runs again (switching it on, a new ballot), so it doesn't vanish mid-pick.
function applyHidePicked() {
  const on = Boolean(loadUi().hidePicked);
  for (const card of result.querySelectorAll(".race")) {
    card.classList.toggle("hidden-picked", on && picks.picked(card.dataset.race).length > 0);
  }
  $("#hide-picked").checked = on;
  hidingNote.hidden = !on;
  viewMenu.classList.toggle("filtered", on);
}

function setHidePicked(on) {
  setView("hidePicked", on);
  if (!ballot) return;
  applyHidePicked();
  markCurrentSection(); // the marked section may have gone
}

$("#hide-picked").addEventListener("change", (event) => setHidePicked(event.target.checked));
showPickedButton.addEventListener("click", () => setHidePicked(false));
$("#collapse-on-pick").checked = Boolean(loadUi().collapseOnPick);
$("#collapse-on-pick").addEventListener("change", (event) => setView("collapseOnPick", event.target.checked));
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
    if (!picks.picked(key).length) {
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
// the progress, Next and the sections.
const narrow = matchMedia("(max-width: 960px)");
function placeForWidth() {
  if (narrow.matches) {
    strip.append(jump);
    $(".ballot-head").after(tools);
  } else {
    $(".side-bottom").before(jump);
    strip.append(tools);
  }
}
narrow.addEventListener("change", placeForWidth);
placeForWidth();

// Links to a section, Next and j/k scroll to just below the strip, however tall it is.
new ResizeObserver(() => {
  document.documentElement.style.scrollPaddingTop = `${strip.offsetHeight + 12}px`;
}).observe(strip);

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

// At most once a frame while scrolling.
let marking = false;
function markSoon() {
  if (marking) return;
  marking = true;
  requestAnimationFrame(() => {
    marking = false;
    markCurrentSection();
  });
}
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
function reloadIfSettingsChanged() {
  if (settingsStamp() !== settingsSeen) location.reload();
}
window.addEventListener("pageshow", (event) => {
  if (event.persisted) reloadIfSettingsChanged();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) reloadIfSettingsChanged();
});

async function start() {
  const fromHash = new URLSearchParams(location.hash.slice(1));
  const changing = fromHash.has("change"); // "Change" on another page's address card
  if (changing) history.replaceState(null, "", location.pathname + location.search);
  const initial = fromHash.get("address")
    ? { address: fromHash.get("address"), ...(fromHash.get("date") ? { election_date: fromHash.get("date") } : {}) }
    : loadLastLookup();
  if (initial?.address) {
    // Show the remembered address right away; the lookup fills in the rest.
    addressInput.value = initial.address;
    showAddress(rememberedCard(initial.address));
    form.hidden = true;
    addressCard.hidden = false;
  } else {
    openPanel("address"); // on a phone, the form is the first thing to fill in
  }
  if (changing) showForm(true);
  await loadElections(initial?.election_date);
  if (initial?.address) {
    if (initial.party) partySelect.value = initial.party;
    lookup(initial, { keepForm: changing });
  }
}

start();
