// Share picks (share.js): a dialog from the toolbar, or More on a phone, that copies or shares a link
// carrying the ballot's picks, saves a Pallot file (the whole session, or these picks to send), and
// opens one, either locked with a phrase if the voter chooses. Picks from a link or a file are offered
// once a ballot is shown: the voter sees what they bring and what's left out before they're used, and
// Undo puts the voter's own back. Picks for another address ask first which ballot to show, unless
// the address or its districts are the same as the voter's. A session is put back (pallot-file.js).
//
// The phrase is the voter's secret: it's only ever in its box, which is masked, kept out of
// spellcheck (which may send text away), autocorrect and password managers, never stored, and
// emptied when its dialog closes. It never leaves the browser.

import { electionLine } from "./ballot-shared.js";
import { $, choiceDialog, closeOnBackdrop, confirmDialog, h, setStatus } from "./dom.js";
import { plural } from "./format.js";
import { icon } from "./icons.js";
import {
  askPhrase, bindPhraseShow, fileLines, hidePhrase, offerSession, openPallotFile, saveBytes, saveSession,
} from "./pallot-file.js";
import {
  EXTENSION, LINK_KEY, buildSlate, canLock, pallotFile, phraseReady, phraseRules, planImport, sameDistricts, samePlace, slateCounts,
  slateFromLink, slateLink,
} from "./share.js";
import { LAST_DISTRICTS, readJson } from "./storage.js";
import { showToast } from "./toast.js";

const dialog = $("#share-dialog");
const summary = $("#share-summary");
const lockChoice = $("#share-lock");
const phraseBox = $("#share-phrase-box");
const phraseInput = $("#share-phrase");
const rulesList = $("#share-phrase-rules");
const linkNotes = $("#share-link-notes");
const fileNotes = $("#share-file-notes");
const addressChoice = $("#share-address");
const warning = $("#share-warn");
const linkButton = $("#share-link");
const saveButton = $("#share-save");
const urlBox = $("#share-url");
const status = $("#share-status");
const SHOWN_MISSING = 3;

let page = null; // { ballot, picks, request, lookup, renderRaces }
let held = null; // picks from a link or file waiting for a ballot: { slate, from, retried, placed }

const nativeShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;

// The link leaves the notes out unless the voter ticks them in; a file of these picks, keeps them
// unless they tick them out. Only the link offers the address, with the districts it's in.
const slate = (notes, address = false) => buildSlate(page.ballot, page.picks, {
  request: page.request, title: electionLine(page.ballot), notes, address, districts: readJson(LAST_DISTRICTS, null),
});

const locked = () => lockChoice.checked && !$("#share-lock-choice").hidden;
const savingSession = () => $('input[name="share-file-what"]:checked').value === "session";

// The link's warning names everything the link would show, and to whom.
function syncWarning() {
  urlBox.hidden = true;
  const also = [linkNotes.checked && !linkNotes.closest("label").hidden && "your notes", addressChoice.checked && "your address"].filter(Boolean);
  const who = locked() ? "anyone who has it and the phrase" : "anyone who has it";
  warning.textContent = `${locked() ? "A locked link" : "A link"} shows who you picked${also.length ? `, ${also.join(" and ")}` : ""} to ${who}, `
    + "and to anyone they pass it on to. Send it only to people you trust.";
}

// The file's notes choice is for a file of these picks only: a session keeps everything.
function syncFileWhat() {
  fileNotes.closest("label").hidden = savingSession() || !slateCounts(slate(true)).notes;
}

// The phrase's rules, each ticked once it's met.
function showRules() {
  rulesList.replaceChildren(...phraseRules(phraseInput.value).map((rule) => h("li", { class: rule.met ? "met" : null },
    rule.met ? icon("check") : h("span", { "aria-hidden": "true" }, "•"),
    rule.text,
    h("span", { class: "sr-only" }, rule.met ? " (done)" : " (not yet)"))));
}

function syncLock() {
  phraseBox.hidden = !lockChoice.checked;
  showRules();
  syncWarning();
  if (lockChoice.checked) phraseInput.focus();
}

// Forgets the phrase and unticks the lock, as the dialog closes.
function forgetPhrase() {
  phraseInput.value = "";
  hidePhrase(phraseInput);
  lockChoice.checked = false;
  phraseBox.hidden = true;
}

// The phrase to lock with: null when unlocked, false (said in the status line) when it doesn't
// meet the rules yet.
function chosenPhrase() {
  if (!locked()) return null;
  const phrase = phraseInput.value;
  if (phraseReady(phrase)) return phrase;
  const missing = phraseRules(phrase).filter((rule) => rule.required && !rule.met).map((rule) => rule.text.toLowerCase());
  setStatus(status, `Your phrase needs ${missing.join(", ")}.`, "error");
  phraseInput.focus();
  return false;
}

// Runs ``work`` with the buttons off, saying "Locking…" while a phrase is stretched into a key.
async function busy(phrase, work) {
  linkButton.disabled = saveButton.disabled = true;
  if (phrase) setStatus(status, "Locking…", "busy");
  try {
    await work();
  } catch (error) {
    setStatus(status, error.message || "Something went wrong. Try again.", "error");
  } finally {
    linkButton.disabled = saveButton.disabled = false;
  }
}

function openShare() {
  if (!page.ballot) return;
  const counts = slateCounts(slate(true));
  const any = counts.races > 0 || counts.notes > 0;
  summary.textContent = any
    ? `Your picks in ${plural(counts.races, "race")}${counts.notes ? ` and ${plural(counts.notes, "note")}` : ""}, for ${electionLine(page.ballot)}.`
    : "You haven't picked anyone yet. Once you do, you can send your picks from here.";
  $("#share-link-part").hidden = !any;
  $("#share-file-picks").hidden = !any;
  if (!any) $('input[name="share-file-what"][value="session"]').checked = true;
  $("#share-lock-choice").hidden = !canLock();
  linkNotes.closest("label").hidden = !counts.notes;
  syncFileWhat();
  $("#share-link-label").textContent = nativeShare() ? "Share link" : "Copy link";
  syncLock();
  setStatus(status, "");
  dialog.showModal();
  (any ? linkButton : saveButton).focus();
}

async function shareLink() {
  const phrase = chosenPhrase();
  if (phrase === false) return;
  await busy(phrase, async () => {
    const url = await slateLink(slate(linkNotes.checked, addressChoice.checked), location.origin + location.pathname, phrase);
    const sendPhrase = phrase ? " Send the phrase another way, such as in person." : "";
    if (nativeShare()) {
      try {
        await navigator.share({ title: "My picks on Pallot", url });
        setStatus(status, `Link shared.${sendPhrase}`, "ok");
      } catch (error) {
        if (error.name !== "AbortError") showUrl(url);
        else setStatus(status, "");
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      urlBox.hidden = true;
      setStatus(status, `Link copied. Paste it into a message or an email.${sendPhrase}`, "ok");
    } catch {
      showUrl(url);
    }
  });
}

// Where the link couldn't be copied or shared, it's shown selected, to copy by hand.
function showUrl(url) {
  urlBox.value = url;
  urlBox.hidden = false;
  urlBox.focus();
  urlBox.select();
  setStatus(status, "Copy this link, then paste it into a message or an email.", "info");
}

// The race on screen behind the dialog, under the strip, for a session to go back to.
function raceOnScreen() {
  const line = $("#progress-strip").getBoundingClientRect().bottom;
  const card = [...document.querySelectorAll("#result .race")].find((race) => race.offsetParent && race.getBoundingClientRect().bottom > line + 40);
  return card?.dataset.race || "";
}

async function saveFile() {
  const phrase = chosenPhrase();
  if (phrase === false) return;
  await busy(phrase, async () => {
    let name;
    if (savingSession()) {
      name = await saveSession({ phrase, race: raceOnScreen() });
    } else {
      name = `pallot-picks-${page.ballot.election_date || "undated"}${EXTENSION}`;
      saveBytes(await pallotFile(slate(fileNotes.checked), phrase), name);
    }
    setStatus(status, `Saved ${name} to your downloads.${phrase ? " Keep the phrase somewhere safe: it can't be recovered." : ""}`, "ok");
  });
}

async function openFile() {
  let opened;
  try {
    opened = await openPallotFile();
  } catch (error) {
    setStatus(status, error.message, "error");
    return;
  }
  if (!opened) return;
  dialog.close();
  if (opened.session) offerSession(opened);
  else offerSlate(opened, "file");
}

// ---- opening picks on the ballot ----------------------------------------------------------

const listed = (names) => (names.length > SHOWN_MISSING
  ? `${names.slice(0, SHOWN_MISSING).join(", ")} and ${names.length - SHOWN_MISSING} more`
  : names.join(", "));

// The lookup for the ballot a file's or link's picks are for: its address, election and party.
export function requestFor(opened, base = opened.ballot) {
  const request = { ...base };
  if (opened.election.date) request.election_date = opened.election.date;
  if (opened.election.party) request.party = opened.election.party;
  return request;
}

// Whether picks for ``opened``'s address belong on the voter's own ballot without asking: the same
// address, or one in the same districts.
const sameBallot = (opened) => samePlace(opened.ballot, page.request) || sameDistricts(opened.districts, readJson(LAST_DISTRICTS, null));

// Asks before using picks from a link or a file on the ballot shown. Picks for another address
// first offer that address's ballot, once, and picks for another election that election's.
async function offerSlate(opened, from, retried = false, placed = false) {
  if (opened.ballot && !placed && !sameBallot(opened)) {
    const where = fileLines(opened)[0];
    const choice = await choiceDialog({
      title: "These picks are for another address",
      body: `They're for ${where}. Show that ballot, or keep yours?`,
      cancel: "Not now",
      choices: [{ value: "mine", label: "Keep mine" }, { value: "theirs", label: "Show that ballot" }],
    });
    if (!choice) return;
    if (choice === "theirs") {
      held = { slate: opened, from, retried: true, placed: true };
      page.lookup(requestFor(opened));
      return;
    }
  }
  const wanted = opened.election.date;
  if (wanted && wanted !== page.ballot.election_date && !retried) {
    const sure = await confirmDialog({
      title: "These picks are for another election",
      body: `They're for ${opened.election.title || wanted}. Your ballot shows ${electionLine(page.ballot)}.`,
      confirm: "Show that ballot",
    });
    if (!sure) return;
    held = { slate: opened, from, retried: true, placed: true };
    page.lookup(requestFor(opened, page.request));
    return;
  }
  const plan = planImport(opened, page.ballot, page.picks);
  if (!plan.changed) {
    showToast(plan.picks || plan.notes ? "These picks are already on your ballot." : "None of these races are on your ballot.");
    return;
  }
  const what = [plan.picks && `picks in ${plural(plan.picks, "race")}`, plan.notes && plural(plan.notes, "note")].filter(Boolean).join(" and ");
  const sure = await confirmDialog({
    title: from === "link" ? "Use the picks you were sent?" : "Use the picks in this file?",
    body: [
      h("p", {}, `They have ${what}${opened.election.title ? `, for ${opened.election.title}` : ""}.`),
      h("p", {}, plan.replaced ? `They replace your picks in ${plural(plan.replaced, "race")}. Your other picks stay.` : "Your own picks stay."),
      plan.missing.length ? h("p", {}, `Not on your ballot, so left out: ${listed(plan.missing)}.`) : null,
    ],
    confirm: "Use these picks",
  });
  if (!sure) return;
  const before = page.picks.merge(plan.changes);
  page.renderRaces();
  showToast(from === "link" ? "Added the picks you were sent." : "Added the picks from the file.", {
    label: "Undo",
    run: () => {
      page.picks.restore(before);
      page.renderRaces();
    },
  });
}

// The picks a "#picks=" link carries, read as the page starts (asking for its phrase if it's
// locked), and the link taken out of the address bar, so a reload or a bookmark doesn't offer them
// again. Null without one, or when the voter cancels the phrase; an unreadable link is said in a toast.
export async function takeLinkedPicks() {
  const value = new URLSearchParams(location.hash.slice(1)).get(LINK_KEY);
  if (value === null) return null;
  history.replaceState(null, "", location.pathname + location.search);
  try {
    const found = await slateFromLink(value, askPhrase);
    if (!found) return null;
    held = { slate: found, from: "link", retried: false, placed: false };
    return found;
  } catch (error) {
    showToast(error.message);
    return null;
  }
}

// Once a ballot is drawn: offers the picks a link or file brought, if any wait.
export function offerHeldPicks() {
  if (!held || !page.ballot) return;
  const { slate: waiting, from, retried, placed } = held;
  held = null;
  offerSlate(waiting, from, retried, placed);
}

// "Load a Pallot file" on the first visit, before any ballot: a session is put back; picks wait for a ballot,
// the one they're for if the voter wants it, else their own once they look it up.
export async function openFromStart(lookup, ask) {
  let opened;
  try {
    opened = await openPallotFile();
  } catch (error) {
    ask(error.message, "error");
    return;
  }
  if (!opened) return;
  if (opened.session) {
    offerSession(opened);
    return;
  }
  held = { slate: opened, from: "file", retried: true, placed: true };
  if (opened.ballot) {
    const choice = await choiceDialog({
      title: "Show the ballot these picks are for?",
      body: fileLines(opened).map((line) => h("p", {}, line)),
      cancel: "Not now",
      choices: [{ value: "mine", label: "Enter my own address" }, { value: "theirs", label: "Show that ballot" }],
    });
    if (choice === "theirs") {
      lookup(requestFor(opened));
      return;
    }
  }
  held.retried = false;
  ask("Look up your address to see the picks from the file on your ballot.", "info");
}

export function initShare(shared) {
  page = shared;
  closeOnBackdrop(dialog);
  // Nothing in this dialog is ever submitted, so a browser never takes a phrase for a password to save.
  dialog.querySelector("form").addEventListener("submit", (event) => event.preventDefault());
  dialog.addEventListener("close", forgetPhrase);
  bindPhraseShow($('[data-phrase-show][aria-controls="share-phrase"]'));
  $("#share-btn").addEventListener("click", openShare);
  $("#share-done").addEventListener("click", () => dialog.close());
  lockChoice.addEventListener("change", syncLock);
  phraseInput.addEventListener("input", () => {
    showRules();
    urlBox.hidden = true;
  });
  linkButton.addEventListener("click", shareLink);
  saveButton.addEventListener("click", saveFile);
  for (const input of document.querySelectorAll('input[name="share-file-what"]')) input.addEventListener("change", syncFileWhat);
  $("#share-open").addEventListener("click", openFile);
  addressChoice.addEventListener("change", syncWarning);
  linkNotes.addEventListener("change", syncWarning);
  window.addEventListener("hashchange", async () => {
    if (await takeLinkedPicks()) offerHeldPicks();
  });
}
