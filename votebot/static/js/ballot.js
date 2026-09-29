// The ballot page. The left pane holds "Your ballot" with your address under it, the list of
// sections, and links to the other pages at the bottom; the main area has the progress strip
// and the races, each one collapsible.

import { rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import { extLink, formatDate, h, initials, safeUrl, slug } from "./dom.js";
import { hydrateIcons } from "./icons.js";
import { GROUP_LABELS, GROUP_ORDER, STATES, districtLine, partyPill } from "./labels.js";
import { Picks, WRITE_IN, loadLastLookup, saveAddressCard, saveLastLookup, settingsStamp } from "./picks.js";
import { buildPrintSheet } from "./print.js";
import { currentEngine, searchHref } from "./search.js";
import { badgeList, raceMoney, renderTabs } from "./source-cards.js";

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
const result = $("#result");
const jump = $("#jump");
const details = $("#details");
const printDialog = $("#print-dialog");

let ballot = null;
let picks = null;
let lastRequest = null;
const redraw = new Map(); // race or proposition key -> redraws its card from the saved picks
let sectionCounts = []; // the left pane's section list: [{ element, keys, maybe }]

// ---- status line (only while working, or when something went wrong) -------------------

function setStatus(message, kind = "info") {
  statusBox.className = `status status-${kind}`;
  statusBox.textContent = message || "";
}

// ---- the address: a saved card, or the form ------------------------------------------

function showForm(show) {
  form.hidden = !show;
  addressCard.hidden = show;
  cancelButton.hidden = !ballot;
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
  if (lastRequest?.precincts && lastRequest.address === request.address) request.precincts = lastRequest.precincts;
  return request;
}

// keepForm: leave the address form open afterwards ("Change" on another page opened it).
async function lookup(request, { keepForm = false } = {}) {
  lastRequest = request;
  setStatus("Looking up your ballot…", "busy");
  submitButton.disabled = true;
  try {
    ballot = await api.post("/api/ballot", request);
    saveLastLookup(request);
    picks = new Picks(ballot.election_date);
    render();
    setStatus("");
    if (keepForm) cancelButton.hidden = false;
    else showForm(false);
  } catch (error) {
    setStatus(error.message, "error");
    if (!ballot) showForm(true);
  } finally {
    submitButton.disabled = false;
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
  updateProgress();
  welcome.hidden = true;
  result.hidden = false;
}

function renderAddress() {
  const { location, districts: d } = ballot;
  const card = {
    address: lastRequest.address,
    place: [location.city, location.county && `${location.county} County`].filter(Boolean).join(" · "),
    districts: districtLine(d),
    matched: location.matched_address || "",
  };
  showAddress(card);
  saveAddressCard(card); // the other pages show it too
}

function renderHeader() {
  const site = STATES[ballot.location.state]?.site;
  $("#ballot-sub").replaceChildren(
    [formatDate(ballot.election_date), ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · "),
    ...(site ? [" · Official info: ", extLink(site.url, site.label)] : []),
  );
}

function renderMessages() {
  $("#messages").replaceChildren(
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
  const items = [];
  const add = (id, label, keys, maybe = false) => {
    const count = h("span", { class: "count" });
    sectionCounts.push({ element: count, keys, maybe });
    items.push(h("li", {}, h("a", { href: `#${id}`, class: maybe ? "maybe-link" : null }, h("span", {}, label), count)));
  };
  for (const group of GROUP_ORDER) {
    const keys = ballot.races.filter((r) => r.group === group).map((r) => r.key);
    if (keys.length) add(`group-${group}`, GROUP_LABELS[group], keys);
  }
  for (const section of ballot.maybe) add(`maybe-${section.id}`, section.title, section.races.map((r) => r.key), true);
  if (ballot.measures.length) add("measures-section", "Propositions", ballot.measures.map((m) => `measure:${m.key}`));
  $("#jump-list").replaceChildren(...items);
  jump.hidden = !items.length;
}

function updateProgress() {
  const done = ballot.races.filter((r) => picks.picked(r.key).length).length;
  const total = ballot.races.length;
  $("#progress").textContent = `${done} of ${total} races picked`;
  $("#progress-bar").style.width = `${total ? Math.round((done / total) * 100) : 0}%`;
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
  const card = collapsibleCard(race.key, { title: race.name, meta: meta.join(" · "), body: [raceMoney(race), body], headExtras: [clearButton] });

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
  const detailsButton = h("button", { type: "button", class: "icon-btn", disabled: !sources },
    sources ? `Details · ${sources} source${sources === 1 ? "" : "s"}` : "No details");
  detailsButton.addEventListener("click", () => openDetails(race, candidate));

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
  refresh(race.key);
}

function refresh(key) {
  redraw.get(key)?.();
  updateProgress();
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
    lookup({ ...lastRequest, precincts });
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
      refresh(key);
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

function renderMeasures() {
  $("#measures").replaceChildren(
    ballot.measures.length
      ? h("section", { class: "group", id: "measures-section" },
          h("h2", { class: "group-title" }, "Propositions"), ballot.measures.map(measureCard))
      : "",
  );
}

// ---- details dialog -----------------------------------------------------------------

function openDetails(race, candidate) {
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
  renderTabs(tabs, candidate.cards, `d-${slug(candidate.key)}`);
  const closeButton = h("button", { type: "button", class: "icon-btn close", "aria-label": "Close" }, "✕");
  closeButton.addEventListener("click", () => details.close());

  details.replaceChildren(
    h("div", { class: "details-head" },
      avatar(candidate, "large"),
      h("div", { class: "details-title" },
        h("h2", { id: "details-name" }, candidate.name),
        h("p", { class: "muted" }, race.name),
        h("p", { class: "cand-sub" }, partyPill(candidate), candidate.incumbent ? h("span", { class: "pill" }, "Incumbent") : null)),
      closeButton),
    tabs,
    h("div", { class: "details-foot" }, searchLink(race, candidate, "btn ghost", `Search the web for ${candidate.name} ↗`), pickButton),
  );
  details.showModal();
  closeButton.focus();
}

details.addEventListener("click", (event) => {
  if (event.target === details) details.close(); // click on the backdrop
});

// ---- print / clear / expand ---------------------------------------------------------

$("#print-btn").addEventListener("click", () => printDialog.showModal());
printDialog.addEventListener("close", () => {
  if (printDialog.returnValue !== "print" || !ballot) return;
  buildPrintSheet(ballot, picks, { includeNotes: $("#print-notes").checked, includeBlank: $("#print-blank").checked });
  setTimeout(() => window.print(), 50);
});
$("#clear-picks").addEventListener("click", () => {
  if (ballot && confirm("Clear all your picks and notes for this election?")) {
    picks.clear();
    render();
  }
});
$("#expand-all").addEventListener("click", () => setAllCollapsed(false));
$("#collapse-all").addEventListener("click", () => setAllCollapsed(true));

// ---- start --------------------------------------------------------------------------

form.addEventListener("submit", (event) => {
  event.preventDefault();
  lookup(readForm());
});
electionSelect.addEventListener("change", syncPartyField);

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
  }
  if (changing) showForm(true);
  await loadElections(initial?.election_date);
  if (initial?.address) {
    if (initial.party) partySelect.value = initial.party;
    lookup(initial, { keepForm: changing });
  }
}

start();
