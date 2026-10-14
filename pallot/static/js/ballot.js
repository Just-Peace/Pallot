// The ballot page. The left pane (chrome.js) holds "Your ballot" with your address under it, the
// list of sections, and links to the other pages at the bottom (on a phone, a top bar; see
// topbar.js); the main area has the entry card (entry-card.js) and a short welcome until there's a
// ballot, then the progress strip and the races, each one collapsible.
//
// This module looks the ballot up, draws it and starts the page. Its parts are their own
// modules, each handed ``page``: the districts card (districts-card.js), the race cards
// (race-cards.js), Details (details.js), and the strip, sections and the view controls (ballot-nav.js).

import { lookupLabel, rememberedCard, showAddress } from "./address.js";
import { api } from "./api.js";
import {
  applyHidePicked, askFocus, hidingNote, initNav, markCurrentSection, renderSections, setCardsLoading, syncPollMarks, updateProgress,
} from "./ballot-nav.js";
import { electionLine } from "./ballot-shared.js";
import { onBanListChanged } from "./ban-list.js";
import { initChrome, narrow } from "./chrome.js";
import { initDetails, showDetails } from "./details.js";
import { syncMap } from "./district-map.js";
import { initDistrictsCard, openDistricts, renderDistricts } from "./districts-card.js";
import { syncEndorserBar } from "./endorser-bar.js";
import { $, closeOnBackdrop, confirmDialog, extLink, h, linkedText, onReturn, setStatus as showStatus, stepText } from "./dom.js";
import { entryMode, fillVoterCard, focusEntry, loadEntryConfig, placeEntry, readVoterCard } from "./entry-card.js";
import { formatDate } from "./format.js";
import { hydrateIcons } from "./icons.js";
import { keyDatesCard } from "./key-dates.js";
import { STATES } from "./labels.js";
import { hideBanner, initRules, openRules, syncRuleBanner } from "./pick-rule-dialog.js";
import { Picks, onPicksChanged } from "./picks.js";
import { buildPrintSheet } from "./print.js";
import { initRaceCards, redrawCards, refillBans, refillCards, renderCards } from "./race-cards.js";
import { ADDRESS_CARD, LAST_LOOKUP, readJson, settingsStamp, writeJson } from "./storage.js";
import { attachSuggestions } from "./suggest.js";
import { hideToast, showToast } from "./toast.js";
import { openPanel } from "./topbar.js";

initChrome();

const form = $("#lookup-form");
const addressInput = $("#address");
const electionSelect = $("#election");
const partyField = $("#party-field");
const partySelect = $("#party");
const submitButton = $("#lookup-btn");
const cancelButton = $("#cancel-change");
const addressCard = $("#address-card");
const entryHint = $("#entry-hint");
const statusBox = $("#status");
const entry = $("#entry");
const entryTitle = $("#entry-title");
const welcome = document.querySelectorAll("[data-welcome]"); // the heading above the entry card and the points under it
const showWelcome = (show) => welcome.forEach((el) => { el.hidden = !show; });
const loading = $("#loading");
const result = $("#result");
const jump = $("#jump");
const printDialog = $("#print-dialog");

// What the page's parts share: the ballot on screen and its picks, the request behind it (not
// one that failed since).
const page = {
  ballot: null, picks: null, request: null,
  loadingCards: false, // the ballot's cards haven't arrived (or failed to)
  lookup, showDetails, openDistricts, updateProgress, renderRaces, openRules,
  markEndorsers: syncEndorserBar, // Help me pick's marks, after the cards are built again
};
let pendingLookup = null; // the AbortController of the latest lookup, cancelled by the next one

// ---- status line (only while working, or when something went wrong) -------------------

function setStatus(message, kind = "info") {
  showStatus(statusBox, message, kind);
  if (message && kind === "error") showEntry(true, { focus: false }); // the line is in the entry card
}

// ---- the address: a saved card in the pane, or the entry card ------------------------

let hasAddress = false; // the pane's address card has one to show
const typingDevice = matchMedia("(hover: hover) and (pointer: fine)");

function showAddressCard(card) {
  showAddress(card);
  hasAddress = true;
  addressCard.hidden = false;
  entryHint.hidden = true;
}

// The entry card: in the main area, above the ballot when there is one; on a phone with a ballot
// showing, in the top bar's address panel, which stays open until it's sent or cancelled.
// ``focus``: put the cursor in its first box.
function showEntry(show, { focus = show } = {}) {
  const inPanel = show && narrow.matches && Boolean(page.ballot);
  placeEntry(inPanel ? $(".side-address") : null);
  entry.hidden = !show;
  entryTitle.textContent = page.ballot ? "Look up another ballot" : "See your ballot, race by race";
  cancelButton.hidden = !page.ballot;
  addressCard.hidden = inPanel || !hasAddress;
  showWelcome(show && !page.ballot && loading.hidden);
  openPanel(inPanel ? "address" : null);
  if (show && !inPanel && page.ballot) scrollTo({ top: 0 });
  if (focus) focusEntry();
}

$("#change-address").addEventListener("click", () => showEntry(true));
cancelButton.addEventListener("click", () => showEntry(false));
narrow.addEventListener("change", () => {
  if (!entry.hidden) showEntry(true, { focus: false });
});

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

// The entry card's request: the address, or the voter card's county and precinct with the districts
// filled in under it. The same address keeps the districts entered on the ballot, and a voter card
// sends its own boxes.
function readForm() {
  let request;
  if (entryMode() === "voter_card") {
    const { county, precinct, districts, precincts } = readVoterCard();
    request = { county, precinct };
    if (Object.keys(districts).length) request.districts = districts;
    if (Object.keys(precincts).length) request.precincts = precincts;
  } else {
    request = { address: addressInput.value.trim() };
    if (page.request?.address === request.address) {
      if (page.request.precincts) request.precincts = page.request.precincts;
      if (page.request.districts) request.districts = page.request.districts;
    }
  }
  if (electionSelect.value) request.election_date = electionSelect.value;
  if (!partyField.hidden && partySelect.value) request.party = partySelect.value;
  if (page.request?.all_races && ballotOf(page.request) === ballotOf(request)) request.all_races = true;
  return request;
}

// Which ballot a request is for: two requests for the same address, or the same county and
// precinct, are one ballot, whatever else they ask.
const plain = (text) => String(text ?? "").trim().replace(/\s+/g, " ").toLowerCase();
function ballotOf(request) {
  if (request.address) return `address:${plain(request.address)}`;
  return `card:${plain(request.county).replace(/\s+county$/, "")}:${plain(request.precinct).replace(/^0+(?=.)/, "")}`;
}

// The server sends the ballot as soon as its races are known, then again with every card. When
// the cards follow this quickly (a saved lookup), the ballot is drawn once, with them.
const QUICK_CARDS_MS = 250;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// keepForm: leave the entry card open, meanwhile and afterwards ("Change" on another page opened it).
// keepBallot: leave the ballot showing meanwhile (new precincts), rather than "Finding your ballot".
// clearPicks: the old address's Picks, cleared once the new ballot arrives, with Undo.
// A new lookup cancels one still running, its cards included, so an older answer can't replace a
// newer ballot. Resolves once the ballot is drawn; its cards may still be coming.
async function lookup(request, { keepForm = false, keepBallot = false, clearPicks = null } = {}) {
  pendingLookup?.abort();
  const controller = new AbortController();
  pendingLookup = controller;
  setStatus("Looking up your ballot…", "busy");
  if (keepBallot) showToast("Updating your ballot…");
  submitButton.disabled = true;
  // Only a lookup that isn't cached takes long enough to see this.
  const loadingShown = keepBallot ? null : setTimeout(() => showLoading(true, { keepEntry: keepForm }), 300);
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
    if (!request.address) { // as Texas and the precinct map write them: "Travis", "300"
      request.county = found.location.county || request.county;
      request.precinct = found.districts.election_precinct?.name || request.precinct;
    }
    page.ballot = found;
    page.request = request;
    page.loadingCards = Boolean(rest);
    writeJson(LAST_LOOKUP, request);
    clearPicks?.reload();
    const cleared = clearPicks?.clear();
    page.picks = new Picks(found.election_date);
    render();
    setStatus("");
    if (cleared) offerUndoClear(clearPicks, cleared);
    else if (keepBallot) hideToast();
    showEntry(keepForm, { focus: false });
    if (rest) addCards(rest, controller);
  } catch (error) {
    if (controller.signal.aborted) return;
    showLoading(false);
    if (keepBallot) {
      setStatus("");
      showToast(error.message);
    } else {
      setStatus(error.message, "error");
    }
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
  syncPollMarks();
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

// "Finding your ballot", in place of the ballot, or of the entry card and the welcome (``keepEntry``:
// the card stays). Its second line changes as the wait goes on, so a long first lookup never looks stuck.
const LOADING_STEPS = [
  [0, "Finding your districts…"],
  [3000, "Reading your county's ballot…"],
  [10000, "A first lookup takes up to a minute; later ones are instant."],
];
let stopLoadingSteps = null;

function showLoading(show, { keepEntry = false } = {}) {
  stopLoadingSteps?.();
  stopLoadingSteps = show ? stepText($("#loading-step"), LOADING_STEPS) : null;
  loading.hidden = !show;
  jump.hidden = show || !page.ballot; // the sections are the old ballot's
  if (show) {
    showWelcome(false);
    result.hidden = true;
    if (!keepEntry && entry.parentElement === loading.parentElement) entry.hidden = true;
  } else if (page.ballot) {
    result.hidden = false;
  }
}

// ---- rendering ----------------------------------------------------------------------

function render() {
  showLoading(false);
  renderAddress();
  renderHeader();
  renderKeyDates();
  renderDistricts();
  syncMap(page.ballot);
  renderMessages();
  renderSections();
  showWelcome(false);
  askFocus();
  hideBanner();
  renderCards();
  renderRaces();
  setCardsLoading(page.loadingCards);
}

// Redraws the races and propositions in place, from the saved picks, with the
// progress, the filters, Help me pick's marks and the rule's banner: after the picks change as a
// whole (Clear picks, Pick by rule, their Undo, another tab). The rest of the page, an open edit of
// the districts and a note being typed included, stays as it is.
function renderRaces() {
  redrawCards();
  applyHidePicked();
  syncEndorserBar();
  syncRuleBanner();
  updateProgress();
  markCurrentSection();
}

function renderAddress() {
  const { location } = page.ballot;
  const fromCard = location.source === "voter_card";
  const card = {
    address: lookupLabel(page.request),
    place: fromCard ? "From your voter card"
      : [location.city, location.county && `${location.county} County`].filter(Boolean).join(" · "),
    matched: location.matched_address || "",
    election: electionLine(page.ballot),
  };
  showAddressCard(card);
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
  hideBanner();
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

// A new address or precinct starts a new ballot, and so does switching between the address and the
// voter card: when this election has picks, notes or write-ins, the voter is asked first, and
// they're cleared once the new ballot arrives. A new election or party alone keeps them, and
// nothing else the voter chose is cleared.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const request = readForm();
  const old = page.ballot && page.picks;
  if (!old || ballotOf(request) === ballotOf(page.request)) {
    lookup(request);
    return;
  }
  old.reload();
  if (old.isEmpty()) {
    lookup(request);
    return;
  }
  const card = !request.address;
  const switching = card !== !page.request.address;
  const sure = await confirmDialog({
    title: switching ? (card ? "Look up by voter card instead?" : "Look up by address instead?")
      : card ? "Look up a new precinct?" : "Look up a new address?",
    body: `A new ${card ? "precinct" : "address"} starts a new ballot. Your picks, notes and write-ins for this election will be cleared. Your settings stay.`,
    confirm: "Continue",
  });
  if (sure) lookup(request, { clearPicks: old });
});

function offerUndoClear(picks, cleared) {
  showToast("Cleared your picks for the old address.", {
    label: "Undo",
    run: () => {
      picks.reload();
      picks.restore(cleared);
      page.picks.reload();
      renderRaces();
    },
  });
}

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
  if (page.ballot) refillBans();
});

// Picks made in another tab show here too, and a pick made here doesn't undo them.
onPicksChanged(() => {
  if (!page.ballot) return;
  page.picks.reload();
  if (page.picks.isEmpty()) hideBanner();
  renderRaces();
});

function start() {
  const fromHash = new URLSearchParams(location.hash.slice(1));
  const changing = fromHash.has("change"); // "Change" on another page's address card
  if (changing) history.replaceState(null, "", location.pathname + location.search);
  const initial = fromHash.get("address")
    ? { address: fromHash.get("address"), ...(fromHash.get("date") ? { election_date: fromHash.get("date") } : {}) }
    : readJson(LAST_LOOKUP, null);
  const label = lookupLabel(initial);
  if (label) {
    // Show the remembered address or voter card right away; the lookup fills in the rest.
    if (initial.address) addressInput.value = initial.address;
    else fillVoterCard(initial);
    showAddressCard(rememberedCard(label));
  }
  // A first visit starts with the cursor in the address box, except on a touch screen, where the
  // keyboard would cover the card.
  if (changing || !label) showEntry(true, { focus: changing || typingDevice.matches });
  loadElections(initial?.election_date);
  loadEntryConfig({
    startOn: () => (label ? (initial.address ? "address" : "voter_card") : null),
    typed: () => Boolean(addressInput.value.trim()),
  });
  if (label) {
    if (initial.party) partySelect.value = initial.party;
    lookup(initial, { keepForm: changing });
  }
}

start();
