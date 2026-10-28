// Share picks (share.js): a dialog from the toolbar, or More on a phone, that copies or shares a link
// carrying the ballot's picks, saves them as a file, and opens a picks file, either locked with a
// phrase if the voter chooses. Picks from a link or a file are offered once a ballot is shown: the
// voter sees what they bring and what's left out before they're used, and Undo puts the voter's own
// back. A locked link or file asks for its phrase first (askPhrase).
//
// The phrase is the voter's secret: it's only ever in its box, which is masked, kept out of
// spellcheck (which may send text away), autocorrect and password managers, never stored, and
// emptied when its dialog closes. It never leaves the browser.

import { electionLine } from "./ballot-shared.js";
import { $, closeOnBackdrop, confirmDialog, h, setStatus } from "./dom.js";
import { plural } from "./format.js";
import { icon } from "./icons.js";
import {
  LINK_KEY, buildSlate, canLock, phraseReady, phraseRules, picksFile, planImport, readPicksFile, slateCounts, slateFromLink,
  slateLink,
} from "./share.js";
import { showToast } from "./toast.js";

const dialog = $("#share-dialog");
const summary = $("#share-summary");
const choices = $("#share-choices");
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
const fileInput = $("#share-file");
const phraseDialog = $("#phrase-dialog");
const phraseEntry = $("#phrase-input");
const phraseStatus = $("#phrase-status");
const openButton = $("#phrase-open");
const MAX_FILE = 1_000_000;
const SHOWN_MISSING = 3;

let page = null; // { ballot, picks, request, lookup, renderRaces }
let held = null; // picks from a link or file waiting for a ballot: { slate, from, retried }
let asking = null; // the phrase question open: { open, resolve, reject } (askPhrase)

const nativeShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;

// The link leaves the notes out unless the voter ticks them in; the file, a copy for themselves,
// keeps them unless they tick them out. Only the link offers the address.
const slate = (notes, address = false) => buildSlate(page.ballot, page.picks, {
  request: page.request, title: electionLine(page.ballot), notes, address,
});

const locked = () => lockChoice.checked && !$("#share-lock-choice").hidden;

// The link's warning names everything the link would show, and to whom.
function syncWarning() {
  urlBox.hidden = true;
  const also = [linkNotes.checked && !linkNotes.closest("label").hidden && "your notes", addressChoice.checked && "your address"].filter(Boolean);
  const who = locked() ? "anyone who has it and the phrase" : "anyone who has it";
  warning.textContent = `${locked() ? "A locked link" : "A link"} shows who you picked${also.length ? `, ${also.join(" and ")}` : ""} to ${who}, `
    + "and to anyone they pass it on to. Send it only to people you trust.";
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

function hidePhrase(input) {
  input.type = "password";
  const button = document.querySelector(`[data-phrase-show][aria-controls="${input.id}"]`);
  button.textContent = "Show";
  button.setAttribute("aria-pressed", "false");
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
  const counts = slateCounts(buildSlate(page.ballot, page.picks, { request: page.request }));
  const any = counts.races > 0 || counts.notes > 0;
  summary.textContent = any
    ? `Your picks in ${plural(counts.races, "race")}${counts.notes ? ` and ${plural(counts.notes, "note")}` : ""}, for ${electionLine(page.ballot)}.`
    : "You haven't picked anyone yet. Once you do, you can share your picks here.";
  choices.hidden = !any;
  $("#share-lock-choice").hidden = !canLock();
  for (const choice of document.querySelectorAll("#share-dialog .notes-choice")) choice.hidden = !counts.notes;
  $("#share-link-label").textContent = nativeShare() ? "Share link" : "Copy link";
  syncLock();
  setStatus(status, "");
  dialog.showModal();
  (any ? linkButton : $("#share-open")).focus();
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

async function saveFile() {
  const phrase = chosenPhrase();
  if (phrase === false) return;
  await busy(phrase, async () => {
    const name = `pallot-picks-${page.ballot.election_date || "undated"}.json`;
    const href = URL.createObjectURL(new Blob([await picksFile(slate(fileNotes.checked), phrase)], { type: "application/json" }));
    const link = h("a", { href, download: name, hidden: true });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
    setStatus(status, `Saved ${name} to your downloads.${phrase ? " Keep the phrase somewhere safe: it can't be recovered." : ""}`, "ok");
  });
}

async function openFile() {
  const file = fileInput.files[0];
  fileInput.value = "";
  if (!file) return;
  let opened;
  try {
    if (file.size > MAX_FILE) throw new Error("This isn't a Pallot picks file.");
    opened = await readPicksFile(await file.text(), askPhrase);
  } catch (error) {
    setStatus(status, error.message, "error");
    return;
  }
  if (!opened) return;
  dialog.close();
  offerSlate(opened, "file");
}

// ---- the phrase of a locked link or file ------------------------------------------------

// Asks for the phrase of a locked link or file until ``open(phrase)`` finds the picks with it
// (share.js), and resolves to them, or to null if the voter cancels.
function askPhrase(open) {
  return new Promise((resolve, reject) => {
    asking = { open, resolve, reject };
    setStatus(phraseStatus, "");
    phraseDialog.showModal();
    phraseEntry.focus();
  });
}

async function tryPhrase() {
  if (!asking || openButton.disabled) return;
  const phrase = phraseEntry.value;
  if (!phrase) {
    setStatus(phraseStatus, "Type the phrase first.", "error");
    phraseEntry.focus();
    return;
  }
  const question = asking;
  openButton.disabled = true;
  setStatus(phraseStatus, "Unlocking…", "busy");
  try {
    const found = await question.open(phrase);
    if (found) {
      asking = null;
      phraseDialog.close();
      question.resolve(found);
      return;
    }
    setStatus(phraseStatus, "That phrase doesn't open these picks. Check it and try again.", "error");
    phraseEntry.select();
  } catch (error) {
    asking = null;
    phraseDialog.close();
    question.reject(error);
  } finally {
    openButton.disabled = false;
  }
}

// ---- opening picks on the ballot ----------------------------------------------------------

const listed = (names) => (names.length > SHOWN_MISSING
  ? `${names.slice(0, SHOWN_MISSING).join(", ")} and ${names.length - SHOWN_MISSING} more`
  : names.join(", "));

// Asks before using picks from a link or a file on the ballot shown. Picks for another election
// first offer that election's ballot, once.
async function offerSlate(opened, from, retried = false) {
  const wanted = opened.election.date;
  if (wanted && wanted !== page.ballot.election_date && !retried) {
    const sure = await confirmDialog({
      title: "These picks are for another election",
      body: `They're for ${opened.election.title || wanted}. Your ballot shows ${electionLine(page.ballot)}.`,
      confirm: "Show that ballot",
    });
    if (!sure) return;
    held = { slate: opened, from, retried: true };
    const request = { ...page.request, election_date: wanted };
    if (opened.election.party) request.party = opened.election.party;
    page.lookup(request);
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
    held = { slate: found, from: "link", retried: false };
    return found;
  } catch (error) {
    showToast(error.message);
    return null;
  }
}

// Once a ballot is drawn: offers the picks a link or file brought, if any wait.
export function offerHeldPicks() {
  if (!held || !page.ballot) return;
  const { slate: waiting, from, retried } = held;
  held = null;
  offerSlate(waiting, from, retried);
}

export function initShare(shared) {
  page = shared;
  closeOnBackdrop(dialog);
  closeOnBackdrop(phraseDialog);
  // Nothing in these dialogs is ever submitted, so a browser never takes a phrase for a password to save.
  dialog.querySelector("form").addEventListener("submit", (event) => event.preventDefault());
  dialog.addEventListener("close", forgetPhrase);
  phraseDialog.addEventListener("close", () => {
    phraseEntry.value = "";
    hidePhrase(phraseEntry);
    const question = asking;
    asking = null;
    question?.resolve(null);
  });
  for (const button of document.querySelectorAll("[data-phrase-show]")) {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.getAttribute("aria-controls"));
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-pressed", String(show));
      input.focus();
    });
  }
  $("#share-btn").addEventListener("click", openShare);
  $("#share-done").addEventListener("click", () => dialog.close());
  lockChoice.addEventListener("change", syncLock);
  phraseInput.addEventListener("input", () => {
    showRules();
    urlBox.hidden = true;
  });
  linkButton.addEventListener("click", shareLink);
  saveButton.addEventListener("click", saveFile);
  $("#share-open").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", openFile);
  addressChoice.addEventListener("change", syncWarning);
  linkNotes.addEventListener("change", syncWarning);
  $("#phrase-cancel").addEventListener("click", () => phraseDialog.close());
  openButton.addEventListener("click", tryPhrase);
  phraseEntry.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    tryPhrase();
  });
  window.addEventListener("hashchange", async () => {
    if (await takeLinkedPicks()) offerHeldPicks();
  });
}
