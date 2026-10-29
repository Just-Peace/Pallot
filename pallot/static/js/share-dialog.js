// Share picks (share.js): a dialog from the toolbar, or More on a phone, that copies or shares a link
// carrying the ballot's picks, the voter's notes and Avoid list if they tick them in, and the districts
// (never the address), locked with a phrase unless the voter unticks it. It points to Settings for a
// copy of everything (a Pallot file, pallot-file.js). What a link brings is offered once a ballot is
// shown: the voter sees each part, ticked, and what's left out before any is used, and Undo puts their
// own back. A session from a file is put back (pallot-file.js).
//
// The phrase is the voter's secret: it's only ever in its box, which is masked, kept out of
// spellcheck (which may send text away), autocorrect and password managers, never stored, and
// emptied when its dialog closes. It never leaves the browser.

import { electionLine, shortElectionLine } from "./ballot-shared.js";
import { banList, setBanList } from "./ban-list.js";
import { $, closeOnBackdrop, confirmDialog, h, setStatus } from "./dom.js";
import { plural } from "./format.js";
import { askPhrase, offerSession, phraseLock } from "./pallot-file.js";
import { refillBans } from "./race-cards.js";
import { LINK_KEY, buildSlate, canLock, planImport, sameDistricts, slateCounts, slateFromLink, slateLink } from "./share.js";
import { LAST_DISTRICTS, readJson } from "./storage.js";
import { showToast } from "./toast.js";

const dialog = $("#share-dialog");
const summary = $("#share-summary");
const lockBlock = $("#share-lock-choice");
const parts = {
  picks: { box: $("#share-picks"), count: $("#share-picks-count") },
  notes: { box: $("#share-notes"), count: $("#share-notes-count") },
  avoid: { box: $("#share-avoid"), count: $("#share-avoid-count") },
};
const warning = $("#share-warn");
const linkButton = $("#share-link");
const urlBox = $("#share-url");
const status = $("#share-status");
const SHOWN_MISSING = 3;

let page = null; // { ballot, picks, request, lookup, renderRaces }
let held = null; // what a link or file brought, waiting for a ballot: { slate, from, retried }

const nativeShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;
const ticked = (part) => parts[part].box.checked && !parts[part].box.closest("label").hidden;

// What's sent: the parts ticked in, and the districts, so whoever opens it knows which ballot it's for.
const slate = ({ withPicks = ticked("picks"), notes = ticked("notes"), avoid = ticked("avoid") } = {}) => buildSlate(page.ballot, page.picks, {
  request: page.request, title: electionLine(page.ballot), withPicks, notes, avoid: avoid ? banList() : null,
  districts: readJson(LAST_DISTRICTS, null),
});

// The warning under Copy link names what the link would show, and to whom; Copy link is off while
// nothing is ticked.
function syncWarning() {
  urlBox.hidden = true;
  const shown = [ticked("picks") && "who you picked", ticked("notes") && "your notes", ticked("avoid") && "who you avoid"].filter(Boolean);
  linkButton.disabled = !shown.length;
  if (!shown.length) {
    warning.textContent = "Tick what the link should carry.";
    return;
  }
  const who = lock.locked() ? "Anyone with the link and phrase" : "Anyone with the link";
  warning.textContent = `${who} sees ${shown.join(", ").replace(/, ([^,]*)$/, " and $1")}. Send it only to people you trust.`;
}

const lock = phraseLock({
  check: $("#share-lock"), box: $("#share-phrase-box"), input: $("#share-phrase"), hint: $("#share-phrase-hint"), status,
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
  const counts = slateCounts(slate({ withPicks: true, notes: true, avoid: true }));
  const has = { picks: counts.races, notes: counts.notes, avoid: counts.avoid };
  const any = Object.values(has).some(Boolean);
  summary.textContent = any
    ? `For ${shortElectionLine(page.ballot)}, with your districts but never your address.`
    : "You haven't picked anyone yet. Once you do, you can share your picks here.";
  $("#share-choices").hidden = !any;
  for (const [part, { box, count }] of Object.entries(parts)) {
    box.closest("label").hidden = !has[part];
    count.textContent = part === "picks" ? `in ${plural(has.picks, "race")}` : part === "notes" ? plural(has.notes, "note") : plural(has.avoid, "name");
  }
  parts.picks.box.checked = true;
  parts.notes.box.checked = false;
  parts.avoid.box.checked = !has.picks;
  lockBlock.hidden = !canLock();
  $("#share-link-label").textContent = nativeShare() ? "Share link" : "Copy link";
  setStatus(status, "");
  lock.sync();
  dialog.showModal();
  (any ? (lock.locked() ? $("#share-phrase") : linkButton) : $("#share-close")).focus();
}

async function shareLink() {
  const phrase = lock.chosen();
  if (phrase === false) return;
  await busy(phrase, async () => {
    const url = await slateLink(slate(), location.origin + location.pathname, phrase);
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

// ---- opening what a link brought, on the ballot -------------------------------------------

const listed = (names) => (names.length > SHOWN_MISSING
  ? `${names.slice(0, SHOWN_MISSING).join(", ")} and ${names.length - SHOWN_MISSING} more`
  : names.join(", "));

// The lookup for the election and party ``opened``'s picks are for, at ``base``'s address.
export function requestFor(opened, base) {
  const request = { ...base };
  if (opened.election.date) request.election_date = opened.election.date;
  if (opened.election.party) request.party = opened.election.party;
  return request;
}

// A box for one part of what was sent, ticked.
const partBox = (label) => {
  const box = h("input", { type: "checkbox", checked: true });
  return { box, row: h("label", { class: "check" }, box, h("span", {}, label)) };
};

// Asks before using what a link or file brought on the ballot shown, each part a box: the picks, the
// notes, and the names for the voter's Avoid list (added, never replacing theirs). Picks for another
// election first offer that election's ballot.
async function offerSlate(opened, from, retried = false) {
  const wanted = opened.election.date;
  const brought = opened.races.length || opened.notes.length;
  if (brought && wanted && wanted !== page.ballot.election_date && !retried) {
    const sure = await confirmDialog({
      title: "These picks are for another election",
      body: `They're for ${opened.election.title || wanted}. Your ballot shows ${electionLine(page.ballot)}.`,
      confirm: "Show that ballot",
    });
    if (!sure) return;
    held = { slate: opened, from, retried: true };
    page.lookup(requestFor(opened, page.request));
    return;
  }
  const plan = planImport(opened, page.ballot, page.picks);
  const pickChanges = Object.keys(plan.changes.races).length + Object.keys(plan.changes.writeIns).length;
  const own = banList().map((entry) => entry.text.toLowerCase());
  const avoid = (opened.avoid || []).filter((entry) => !own.includes(entry.text.toLowerCase()));
  const offered = {
    picks: pickChanges ? partBox(`Picks in ${plural(plan.picks, "race")}`) : null,
    notes: plan.notes ? partBox(plural(plan.notes, "note")) : null,
    avoid: avoid.length ? partBox(`${plural(avoid.length, "name")} for your Avoid list: ${listed(avoid.map((entry) => entry.text))}`) : null,
  };
  if (!Object.values(offered).some(Boolean)) {
    showToast(brought && !plan.picks && !plan.notes ? "None of these races are on your ballot." : "You already have everything in this link.");
    return;
  }
  const where = opened.districts && !sameDistricts(opened.districts, readJson(LAST_DISTRICTS, null)) && opened.districts.line;
  const sure = await confirmDialog({
    title: from === "link" ? "Use what you were sent?" : "Use what's in this file?",
    body: [
      opened.election.title || where
        ? h("p", {}, opened.election.title ? `For ${opened.election.title}.` : null, where ? ` They're for ${where}; only the races also on your ballot are used.` : null)
        : null,
      h("div", { class: "share-parts" }, Object.values(offered).filter(Boolean).map((part) => part.row)),
      offered.picks && plan.replaced ? h("p", { class: "fine" }, `They replace your picks in ${plural(plan.replaced, "race")}. Your other picks stay.`) : null,
      plan.missing.length ? h("p", { class: "fine" }, `Not on your ballot, so left out: ${listed(plan.missing)}.`) : null,
    ],
    confirm: "Use these",
  });
  if (!sure) return;
  const use = (part) => Boolean(offered[part]?.box.checked);
  if (!use("picks") && !use("notes") && !use("avoid")) return;
  const before = page.picks.merge({
    races: use("picks") ? plan.changes.races : {},
    writeIns: use("picks") ? plan.changes.writeIns : {},
    notes: use("notes") ? plan.changes.notes : {},
  });
  const bans = banList();
  if (use("avoid")) setBanList([...bans, ...avoid]);
  page.renderRaces();
  refillBans();
  showToast(from === "link" ? "Added what you were sent." : "Added what's in the file.", {
    label: "Undo",
    run: () => {
      page.picks.restore(before);
      setBanList(bans);
      page.renderRaces();
      refillBans();
    },
  });
}

// What a "#picks=" link carries, read as the page starts (asking for its phrase if it's locked), and
// the link taken out of the address bar, so a reload or a bookmark doesn't offer it again. Null
// without one, or when the voter cancels the phrase; an unreadable link is said in a toast.
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

// Once a ballot is drawn: offers what a link or file brought, if anything waits.
export function offerHeldPicks() {
  if (!held || !page.ballot) return;
  const { slate: waiting, from, retried } = held;
  held = null;
  offerSlate(waiting, from, retried);
}

// What the Pallot file tab read (``opened``), on Show my ballot: a session is put back; anything else
// waits for the voter's ballot, offered once it's shown (``ask`` says to look it up).
export function openFromStart(opened, ask) {
  if (opened.session) {
    offerSession(opened);
    return;
  }
  held = { slate: opened, from: "file", retried: false };
  if (page.ballot) offerHeldPicks();
  else ask("Look up your address to see what's in the file on your ballot.", "info");
}

export function initShare(shared) {
  page = shared;
  closeOnBackdrop(dialog);
  // Nothing in this dialog is ever submitted, so a browser never takes a phrase for a password to save.
  dialog.querySelector("form").addEventListener("submit", (event) => event.preventDefault());
  dialog.addEventListener("close", () => lock.forget());
  $("#share-btn").addEventListener("click", openShare);
  $("#share-close").addEventListener("click", () => dialog.close());
  linkButton.addEventListener("click", shareLink);
  for (const { box } of Object.values(parts)) box.addEventListener("change", syncWarning);
  window.addEventListener("hashchange", async () => {
    if (await takeLinkedPicks()) offerHeldPicks();
  });
}
