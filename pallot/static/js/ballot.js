// The ballot page. The left pane (chrome.js) holds "Your ballot" with your address and this
// page's form under it, the list of sections, and links to the other pages at the bottom (on a
// phone, a top bar; see topbar.js); the main area has the progress strip and the races, each
// one collapsible.
//
// This module looks the ballot up, draws it and starts the page. Its parts are their own
// modules, each handed ``page``: the districts card (districts-card.js), the race cards
// (race-cards.js), Details (details.js), and the strip, sections and the view controls (ballot-nav.js).

import { rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import {
  applyHidePicked, hidingNote, initNav, markCurrentSection, renderSections, setCardsLoading, updateProgress,
} from "./ballot-nav.js";
import { electionLine } from "./ballot-shared.js";
import { onBanListChanged } from "./ban-list.js";
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
import { initRaceCards, redrawCards, refillCards, renderCards } from "./race-cards.js";
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
  loadingCards: false, // the ballot's cards haven't arrived (or failed to)
  lookup, showDetails, openPrecincts, updateProgress, renderRaces, openRules,
};
let pendingLookup = null; // the AbortController of the latest lookup, cancelled by the next one

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

// The server sends the ballot as soon as its races are known, then again with every card. When
// the cards follow this quickly (a saved lookup), the ballot is drawn once, with them.
const QUICK_CARDS_MS = 250;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// keepForm: leave the address form open afterwards ("Change" on another page opened it).
// keepBallot: leave the ballot showing meanwhile (new precincts), rather than "Finding your ballot".
// A new lookup cancels one still running, its cards included, so an older answer can't replace a
// newer ballot. Resolves once the ballot is drawn; its cards may still be coming.
async function lookup(request, { keepForm = false, keepBallot = false } = {}) {
  pendingLookup?.abort();
  const controller = new AbortController();
  pendingLookup = controller;
  setStatus("Looking up your ballot…", "busy");
  submitButton.disabled = true;
  // Only a lookup that isn't cached takes long enough to see this.
  const loadingShown = keepBallot ? null : setTimeout(() => showLoading(true), 300);
  try {
    const answers = api.lines("/api/ballot", request, { signal: controller.signal });
    const first = (await answers.next()).value;
    if (controller.signal.aborted) return; // cancelled as its answer arrived
    if (!first?.ballot) throw new Error(first?.error || "The lookup stopped before it finished. Try again.");
    let found = first.ballot;
    let rest = first.done ? null : answers.next(); // the line with the cards
    if (rest) {
      const quick = await Promise.race([rest, wait(QUICK_CARDS_MS)]);
      if (controller.signal.aborted) return;
      if (quick?.value?.done) {
        found = quick.value.ballot;
        rest = null;
      } else if (quick) {
        rest = Promise.resolve(quick);
      }
    }
    page.ballot = found;
    page.request = request;
    page.loadingCards = Boolean(rest);
    writeJson(LAST_LOOKUP, request);
    page.picks = new Picks(found.election_date);
    render();
    setStatus("");
    if (keepForm) cancelButton.hidden = false;
    else showForm(false);
    if (rest) addCards(rest, controller);
  } catch (error) {
    if (controller.signal.aborted) return;
    showLoading(false);
    setStatus(error.message, "error");
    if (!page.ballot) showForm(true);
  } finally {
    clearTimeout(loadingShown);
    if (pendingLookup === controller) submitButton.disabled = false;
  }
}

// Puts the cards from the ballot's second line on the ballot drawn from its first, in place.
async function addCards(rest, controller) {
  let line = null;
  let failure = null;
  try {
    line = (await rest).value;
  } catch (error) {
    failure = error.message;
  }
  if (controller.signal.aborted) return;
  if (line?.done) {
    mergeCards(page.ballot, line.ballot);
    page.loadingCards = false;
  } else {
    page.ballot.warnings.push(`${line?.error || failure || "Couldn't load money, polls and endorsements."} `
      + "Look the address up again to try again.");
  }
  refillCards();
  renderMessages();
  setCardsLoading(page.loadingCards, { failed: page.loadingCards });
}

// Only the cards and what they decide change once the races are known (enrich.py), so they're
// copied onto the races already drawn, whose handlers keep the same objects.
function mergeCards(ballot, complete) {
  const allRaces = (b) => [...b.races, ...b.maybe.flatMap((section) => section.races)];
  const done = new Map(allRaces(complete).map((race) => [race.key, race]));
  for (const race of allRaces(ballot)) {
    const full = done.get(race.key);
    if (!full) continue;
    Object.assign(race, { cards: full.cards, holder: full.holder, open_seat: full.open_seat });
    const people = new Map(full.candidates.map((c) => [c.key, c]));
    for (const candidate of race.candidates) {
      const person = people.get(candidate.key);
      if (person) {
        Object.assign(candidate, { cards: person.cards, incumbent: person.incumbent, photo_url: person.photo_url,
          party_holds_seat: person.party_holds_seat });
      }
    }
  }
  Object.assign(ballot, { warnings: complete.warnings, notes: complete.notes, meta: complete.meta });
}

// "Finding your ballot", in place of the ballot or the welcome.
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
  setCardsLoading(page.loadingCards);
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
$("#print-btn").addEventListener("click", () => {
  if (!page.loadingCards) printDialog.showModal();
});
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

// A candidate banned or unbanned in another ballot tab gets or loses their Banned pill here too.
onBanListChanged(() => {
  if (page.ballot) refillCards();
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
