// The ballot page. The left pane (chrome.js) holds "Your ballot" with your address and this
// page's form under it, the list of sections, and links to the other pages at the bottom (on a
// phone, a top bar; see topbar.js); the main area has the progress strip and the races, each
// one collapsible.
//
// This module looks the ballot up, draws it and starts the page. Its parts are their own
// modules, each handed ``page``: the districts card (districts-card.js), the race cards
// (race-cards.js), Details (details.js), and the strip, sections and View (ballot-nav.js).

import { rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import { applyHidePicked, hidingNote, initNav, markCurrentSection, renderSections, updateProgress } from "./ballot-nav.js";
import { electionLine } from "./ballot-shared.js";
import { initChrome, setPaneCollapsed } from "./chrome.js";
import { initDetails, showDetails } from "./details.js";
import { syncMap } from "./district-map.js";
import { initDistrictsCard, openPrecincts, renderDistricts } from "./districts-card.js";
import { $, closeOnBackdrop, extLink, h, linkedText, onReturn, setStatus as showStatus } from "./dom.js";
import { showEndorsementLists } from "./endorsement-lists.js";
import { formatDate } from "./format.js";
import { hydrateIcons } from "./icons.js";
import { keyDatesCard } from "./key-dates.js";
import { STATES } from "./labels.js";
import { initRules, openRules } from "./pick-rule-dialog.js";
import { Picks, onPicksChanged } from "./picks.js";
import { buildPrintSheet } from "./print.js";
import { initRaceCards, redrawCards, renderCards } from "./race-cards.js";
import { ADDRESS_CARD, LAST_LOOKUP, readJson, settingsStamp, writeJson } from "./storage.js";
import { attachSuggestions } from "./suggest.js";
import { showToast } from "./toast.js";
import { openPanel } from "./topbar.js";

initChrome();
showEndorsementLists(); // in the welcome steps

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
const jump = $("#jump");
const printDialog = $("#print-dialog");

// What the page's parts share: the ballot on screen and its picks, the request behind it (not
// one that failed since).
const page = {
  ballot: null, picks: null, request: null,
  lookup, showDetails, openPrecincts, updateProgress, renderRaces, openRules,
};
let pendingLookup = null; // the AbortController of the lookup still running

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
  cancelButton.hidden = !page.ballot;
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
  if (page.request?.address === request.address) {
    if (page.request.precincts) request.precincts = page.request.precincts;
    if (page.request.districts) request.districts = page.request.districts;
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
    page.ballot = found;
    page.request = request;
    writeJson(LAST_LOOKUP, request);
    page.picks = new Picks(found.election_date);
    render();
    setStatus("");
    if (keepForm) cancelButton.hidden = false;
    else showForm(false);
  } catch (error) {
    if (controller.signal.aborted) return;
    showLoading(false);
    setStatus(error.message, "error");
    if (!page.ballot) showForm(true);
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
  jump.hidden = show || !page.ballot; // the sections are the old ballot's
  if (show) {
    welcome.hidden = true;
    result.hidden = true;
  } else if (page.ballot) {
    result.hidden = false;
  } else {
    welcome.hidden = false;
  }
}

// ---- rendering ----------------------------------------------------------------------

function render() {
  renderAddress();
  renderHeader();
  renderKeyDates();
  renderDistricts();
  syncMap(page.ballot);
  renderMessages();
  renderSections();
  loading.hidden = true;
  welcome.hidden = true;
  result.hidden = false;
  renderCards();
  renderRaces();
}

// Redraws the races and propositions in place, from the saved picks, with the
// progress and the filter: after the picks change as a whole (Clear picks, Pick by rule, their
// Undo, another tab). The rest of the page, an open edit of the districts and a note being typed
// included, stays as it is.
function renderRaces() {
  redrawCards();
  applyHidePicked();
  updateProgress();
  markCurrentSection();
}

function renderAddress() {
  const { location } = page.ballot;
  const card = {
    address: page.request.address,
    place: [location.city, location.county && `${location.county} County`].filter(Boolean).join(" · "),
    matched: location.matched_address || "",
    election: electionLine(page.ballot),
  };
  showAddress(card);
  writeJson(ADDRESS_CARD, card); // the other pages show it too
}

function renderHeader() {
  const state = STATES[page.ballot.location.state];
  const site = state?.registration ? null : state?.site;
  $("#ballot-sub").replaceChildren(
    electionLine(page.ballot),
    ...(site ? [" · Official info: ", extLink(site.url, site.label)] : []),
  );
}

function renderKeyDates() {
  const card = $("#key-dates");
  const contents = keyDatesCard(page.ballot);
  card.replaceChildren(...(contents || []).filter(Boolean));
  card.hidden = !contents;
}

function renderMessages() {
  const { warnings, notes } = page.ballot;
  $("#messages").replaceChildren(
    hidingNote,
    ...warnings.map((w) => h("p", { class: "notice notice-warn" }, w)),
    ...notes.map((n) => h("p", { class: "notice" }, linkedText(n))),
  );
}

// ---- print / clear ------------------------------------------------------------------

for (const dialog of [$("#compare"), printDialog]) closeOnBackdrop(dialog);

$("#rule-btn").addEventListener("click", () => openRules());

const walletChoice = $("#print-wallet");
for (const radio of printDialog.querySelectorAll('input[name="print-layout"]')) {
  radio.addEventListener("change", () => { $("#print-notes").disabled = walletChoice.checked; }); // notes don't fit
}
$("#print-btn").addEventListener("click", () => printDialog.showModal());
printDialog.addEventListener("close", () => {
  if (printDialog.returnValue === "print" && page.ballot) setTimeout(() => window.print(), 50);
});
// Every print, Print my picks or the browser's own (Ctrl+P), gets a sheet of the current
// picks, laid out by the print dialog's current choices.
window.addEventListener("beforeprint", () => {
  if (!page.ballot) {
    $("#print-sheet").replaceChildren();
    return;
  }
  const wallet = walletChoice.checked;
  buildPrintSheet(page.ballot, page.picks, { includeNotes: $("#print-notes").checked && !wallet, includeBlank: $("#print-blank").checked, wallet });
});

// Clears at once, and offers to put everything back.
$("#clear-picks").addEventListener("click", () => {
  if (!page.ballot) return;
  if (page.picks.isEmpty()) {
    showToast("No picks or notes to clear.");
    return;
  }
  const cleared = page.picks.clear();
  renderRaces();
  showToast("Cleared your picks and notes.", {
    label: "Undo",
    run: () => {
      page.picks.restore(cleared);
      renderRaces();
    },
  });
});

// ---- start --------------------------------------------------------------------------

initRaceCards(page);
initDetails(page);
initRules(page);
initDistrictsCard(page);
initNav(page);

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
  if (!page.ballot) return;
  page.picks.reload();
  renderRaces();
});

function start() {
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
  loadElections(initial?.election_date);
  if (initial?.address) {
    if (initial.party) partySelect.value = initial.party;
    lookup(initial, { keepForm: changing });
  }
}

start();
