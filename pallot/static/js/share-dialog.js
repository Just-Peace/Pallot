// Share picks (share.js): a dialog from the toolbar, or More on a phone, that copies or shares a link
// carrying the ballot's picks, locked with a phrase unless the voter unticks it, and points to
// Settings for a copy of everything (a Pallot file, pallot-file.js). Picks from a link or a file are offered
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
import { askPhrase, fileLines, offerSession, phraseLock } from "./pallot-file.js";
import { LINK_KEY, buildSlate, canLock, planImport, sameDistricts, samePlace, slateCounts, slateFromLink, slateLink } from "./share.js";
import { LAST_DISTRICTS, readJson } from "./storage.js";
import { showToast } from "./toast.js";

const dialog = $("#share-dialog");
const summary = $("#share-summary");
const lockBlock = $("#share-lock-choice");
const notesChoice = $("#share-notes");
const addressChoice = $("#share-address");
const warning = $("#share-warn");
const linkButton = $("#share-link");
const urlBox = $("#share-url");
const status = $("#share-status");
const SHOWN_MISSING = 3;

let page = null; // { ballot, picks, request, lookup, renderRaces }
let held = null; // picks from a link or file waiting for a ballot: { slate, from, retried, placed }

const nativeShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;

// What's sent: this election's picks, with the notes and the address (and the districts it's in)
// only if the voter ticks them in.
const slate = (notes, address = false) => buildSlate(page.ballot, page.picks, {
  request: page.request, title: electionLine(page.ballot), notes, address, districts: readJson(LAST_DISTRICTS, null),
});
const sentSlate = () => slate(notesChoice.checked && !notesChoice.closest("label").hidden, addressChoice.checked);

// The warning under Copy link names everything the link would show, and to whom.
function syncWarning() {
  urlBox.hidden = true;
  const also = [notesChoice.checked && !notesChoice.closest("label").hidden && "your notes", addressChoice.checked && "your address"].filter(Boolean);
  const who = lock.locked() ? "Anyone with it and the phrase" : "Anyone with it";
  warning.textContent = `${who} sees who you picked${also.length ? `, ${also.join(" and ")}` : ""}, and so does anyone they pass it on to. `
    + "Send it only to people you trust.";
}

const lock = phraseLock({
  check: $("#share-lock"), box: $("#share-phrase-box"), input: $("#share-phrase"), rules: $("#share-phrase-rules"), status,
  onChange: syncWarning,
});

// Runs ``work`` with the button off, saying "Locking…" while a phrase is stretched into a key.
async function busy(phrase, work) {
  linkButton.disabled = true;
  if (phrase) setStatus(status, "Locking…", "busy");
  try {
    await work();
  } catch (error) {
    setStatus(status, error.message || "Something went wrong. Try again.", "error");
  } finally {
    linkButton.disabled = false;
  }
}

function openShare() {
  if (!page.ballot) return;
  const counts = slateCounts(slate(true));
  const any = counts.races > 0 || counts.notes > 0;
  summary.textContent = any
    ? `Your picks in ${plural(counts.races, "race")}${counts.notes ? ` and ${plural(counts.notes, "note")}` : ""}, for ${electionLine(page.ballot)}.`
    : "You haven't picked anyone yet. Once you do, you can share your picks here.";
  $("#share-choices").hidden = !any;
  lockBlock.hidden = !canLock();
  notesChoice.closest("label").hidden = !counts.notes;
  $("#share-link-label").textContent = nativeShare() ? "Share link" : "Copy link";
  urlBox.hidden = true;
  setStatus(status, "");
  lock.sync();
  dialog.showModal();
  (any ? linkButton : $("#share-done")).focus();
}

async function shareLink() {
  const phrase = lock.chosen();
  if (phrase === false) return;
  await busy(phrase, async () => {
    const url = await slateLink(sentSlate(), location.origin + location.pathname, phrase);
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

// What the Pallot file tab read (``opened``), on Show my ballot: a session is put back; picks wait for a
// ballot, the one they're for if the voter wants it, else their own once they look it up.
export async function openFromStart(opened, lookup, ask) {
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
  dialog.addEventListener("close", () => lock.forget());
  $("#share-btn").addEventListener("click", openShare);
  $("#share-done").addEventListener("click", () => dialog.close());
  linkButton.addEventListener("click", shareLink);
  addressChoice.addEventListener("change", syncWarning);
  notesChoice.addEventListener("change", syncWarning);
  window.addEventListener("hashchange", async () => {
    if (await takeLinkedPicks()) offerHeldPicks();
  });
}
