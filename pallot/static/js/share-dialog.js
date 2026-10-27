// Share picks (share.js): a dialog from the toolbar, or More on a phone, that copies or shares a link
// carrying the ballot's picks, saves them as a file, and opens a picks file. Picks from a link or a
// file are offered once a ballot is shown: the voter sees what they bring and what's left out
// before they're used, and Undo puts the voter's own back.

import { electionLine } from "./ballot-shared.js";
import { $, closeOnBackdrop, confirmDialog, h, setStatus } from "./dom.js";
import { plural } from "./format.js";
import { LINK_KEY, buildSlate, planImport, readSlate, slateCounts, slateFromLink, slateLink } from "./share.js";
import { showToast } from "./toast.js";

const dialog = $("#share-dialog");
const summary = $("#share-summary");
const choices = $("#share-choices");
const notesChoice = $("#share-notes");
const addressChoice = $("#share-address");
const linkButton = $("#share-link");
const saveButton = $("#share-save");
const urlBox = $("#share-url");
const status = $("#share-status");
const fileInput = $("#share-file");
const MAX_FILE = 1_000_000;
const SHOWN_MISSING = 3;

let page = null; // { ballot, picks, request, lookup, renderRaces }
let held = null; // picks from a link or file waiting for a ballot: { slate, from, retried }

const nativeShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;

const slate = () => buildSlate(page.ballot, page.picks, {
  request: page.request, title: electionLine(page.ballot), notes: notesChoice.checked, address: addressChoice.checked,
});

function openShare() {
  if (!page.ballot) return;
  const counts = slateCounts(buildSlate(page.ballot, page.picks, { request: page.request }));
  const any = counts.races > 0 || counts.notes > 0;
  summary.textContent = any
    ? `Your picks in ${plural(counts.races, "race")}${counts.notes ? ` and ${plural(counts.notes, "note")}` : ""}, for ${electionLine(page.ballot)}.`
    : "You haven't picked anyone yet. Once you do, you can share your picks here.";
  choices.hidden = !any;
  $("#share-notes-choice").hidden = !counts.notes;
  $("#share-link-label").textContent = nativeShare() ? "Share link" : "Copy link";
  urlBox.hidden = true;
  setStatus(status, "");
  dialog.showModal();
  (any ? linkButton : $("#share-open")).focus();
}

async function shareLink() {
  const url = await slateLink(slate(), location.origin + location.pathname);
  if (nativeShare()) {
    try {
      await navigator.share({ title: "My picks on Pallot", url });
      setStatus(status, "Link shared.", "ok");
    } catch (error) {
      if (error.name !== "AbortError") showUrl(url);
    }
    return;
  }
  try {
    await navigator.clipboard.writeText(url);
    urlBox.hidden = true;
    setStatus(status, "Link copied. Paste it into a message or an email.", "ok");
  } catch {
    showUrl(url);
  }
}

// Where the link couldn't be copied or shared, it's shown selected, to copy by hand.
function showUrl(url) {
  urlBox.value = url;
  urlBox.hidden = false;
  urlBox.focus();
  urlBox.select();
  setStatus(status, "Copy this link, then paste it into a message or an email.", "info");
}

function saveFile() {
  const name = `pallot-picks-${page.ballot.election_date || "undated"}.json`;
  const href = URL.createObjectURL(new Blob([JSON.stringify(slate(), null, 2)], { type: "application/json" }));
  const link = h("a", { href, download: name, hidden: true });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  setStatus(status, `Saved ${name} to your downloads.`, "ok");
}

async function openFile() {
  const file = fileInput.files[0];
  fileInput.value = "";
  if (!file) return;
  let opened;
  try {
    if (file.size > MAX_FILE) throw new Error("This isn't a Pallot picks file.");
    opened = readSlate(await file.text());
  } catch (error) {
    setStatus(status, error.message, "error");
    return;
  }
  dialog.close();
  offerSlate(opened, "file");
}

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

// The picks a "#picks=" link carries, read as the page starts, and the link taken out of the
// address bar, so a reload or a bookmark doesn't offer them again. Null without one; an unreadable
// link is said in a toast.
export async function takeLinkedPicks() {
  const value = new URLSearchParams(location.hash.slice(1)).get(LINK_KEY);
  if (value === null) return null;
  history.replaceState(null, "", location.pathname + location.search);
  try {
    held = { slate: await slateFromLink(value), from: "link", retried: false };
    return held.slate;
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
  $("#share-btn").addEventListener("click", openShare);
  linkButton.addEventListener("click", shareLink);
  saveButton.addEventListener("click", saveFile);
  $("#share-open").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", openFile);
  addressChoice.addEventListener("change", () => { urlBox.hidden = true; });
  notesChoice.addEventListener("change", () => { urlBox.hidden = true; });
  window.addEventListener("hashchange", async () => {
    if (await takeLinkedPicks()) offerHeldPicks();
  });
}
