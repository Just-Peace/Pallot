// A Pallot file (share.js) on any page: choosing one to open, the phrase of a locked file or link
// (askPhrase), saving one, what a file holds, and a whole session put back (session.js), after which
// the ballot opens on it, at the race it was saved on, with Undo.
//
// The phrase is the voter's secret: it's only ever in its box, which is masked, kept out of
// spellcheck (which may send text away), autocorrect and password managers, never stored, and
// emptied when its dialog closes. It never leaves the browser.

import { lookupLabel } from "./address.js";
import { choiceDialog, closeOnBackdrop, confirmDialog, h, setStatus } from "./dom.js";
import { plural } from "./format.js";
import { keepsAnything, restoreSession, sessionStore, undoRestore } from "./session.js";
import { EXTENSION, buildSession, pallotFile, readPallotFile, slateCounts } from "./share.js";
import { showToast } from "./toast.js";

const MAX_FILE = 1_000_000;
const RESTORED = "pallot.restored"; // sessionStorage: { race, before }, from a restore until the ballot opens on it

let phrase = null; // the phrase dialog's parts, made the first time it's needed
let asking = null; // the phrase question open: { open, resolve, reject }
let picker = null;

// ---- the phrase of a locked file or link ----------------------------------------------------

export function hidePhrase(input) {
  input.type = "password";
  const button = document.querySelector(`[data-phrase-show][aria-controls="${input.id}"]`);
  button.textContent = "Show";
  button.setAttribute("aria-pressed", "false");
}

// A phrase box's Show button shows or masks the phrase.
export function bindPhraseShow(button) {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Hide" : "Show";
    button.setAttribute("aria-pressed", String(show));
    input.focus();
  });
}

function phraseParts() {
  if (phrase) return phrase;
  const input = h("input", { type: "password", id: "phrase-input", autocomplete: "off", autocapitalize: "off", autocorrect: "off",
    spellcheck: "false", "data-1p-ignore": true, "data-lpignore": "true" });
  const show = h("button", { class: "btn ghost small", type: "button", "data-phrase-show": true, "aria-controls": "phrase-input", "aria-pressed": "false" }, "Show");
  const status = h("p", { class: "status", role: "status", "aria-live": "polite" });
  const open = h("button", { class: "btn primary", type: "button" }, "Open");
  const cancel = h("button", { class: "btn ghost", type: "button" }, "Cancel");
  const dialog = h("dialog", { id: "phrase-dialog", class: "small-dialog", "aria-labelledby": "phrase-title", "aria-describedby": "phrase-intro" },
    h("div", { class: "dialog-pad" },
      h("h2", { id: "phrase-title" }, "This is locked"),
      h("p", { id: "phrase-intro" }, "Type the phrase it was locked with."),
      h("label", { for: "phrase-input" }, "Phrase"),
      h("div", { class: "phrase-field" }, input, show),
      status,
      h("p", { class: "fine" }, "Your phrase stays on this device. Pallot's server never sees it."),
      h("div", { class: "button-row end" }, cancel, open)));
  document.body.append(dialog);
  phrase = { dialog, input, status, open };
  closeOnBackdrop(dialog);
  bindPhraseShow(show);
  dialog.addEventListener("close", () => {
    input.value = "";
    hidePhrase(input);
    const question = asking;
    asking = null;
    question?.resolve(null);
  });
  cancel.addEventListener("click", () => dialog.close());
  open.addEventListener("click", tryPhrase);
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    tryPhrase();
  });
  return phrase;
}

// Asks for the phrase of a locked file or link until ``open(phrase)`` finds what it holds (share.js),
// and resolves to that, or to null if the voter cancels.
export function askPhrase(open) {
  const { dialog, input, status } = phraseParts();
  return new Promise((resolve, reject) => {
    asking = { open, resolve, reject };
    setStatus(status, "");
    dialog.showModal();
    input.focus();
  });
}

async function tryPhrase() {
  const { dialog, input, status, open } = phrase;
  if (!asking || open.disabled) return;
  if (!input.value) {
    setStatus(status, "Type the phrase first.", "error");
    input.focus();
    return;
  }
  const question = asking;
  open.disabled = true;
  setStatus(status, "Unlocking…", "busy");
  try {
    const found = await question.open(input.value);
    if (found) {
      asking = null;
      dialog.close();
      question.resolve(found);
      return;
    }
    setStatus(status, "That phrase doesn't open it. Check it and try again.", "error");
    input.select();
  } catch (error) {
    asking = null;
    dialog.close();
    question.reject(error);
  } finally {
    open.disabled = false;
  }
}

// ---- choosing, reading and saving ------------------------------------------------------------

// The file the voter chooses, or null. Any file can be chosen, since a phone greys out the types it
// doesn't know; share.js tells a Pallot file by its first bytes.
export function chooseFile() {
  if (!picker) {
    picker = h("input", { type: "file", hidden: true });
    document.body.append(picker);
  }
  return new Promise((resolve) => {
    const done = () => {
      const file = picker.files[0] || null;
      picker.value = "";
      resolve(file);
    };
    picker.addEventListener("change", done, { once: true });
    picker.addEventListener("cancel", done, { once: true });
    picker.click();
  });
}

// What the file the voter chooses holds (share.js's slate), or null if they chose none or cancelled
// its phrase. Throws an Error that says what's wrong, for the voter.
export async function openPallotFile() {
  const file = await chooseFile();
  return file ? readFile(file) : null;
}

// What ``file`` holds, as openPallotFile().
export async function readFile(file) {
  if (file.size > MAX_FILE) throw new Error("This isn't a Pallot file.");
  return readPallotFile(new Uint8Array(await file.arrayBuffer()), askPhrase);
}

// Saves ``bytes`` to the voter's downloads as ``name``.
export function saveBytes(bytes, name) {
  const href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const link = h("a", { href, download: name, hidden: true });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

const today = () => {
  const now = new Date();
  return [now.getFullYear(), now.getMonth() + 1, now.getDate()].map((n) => String(n).padStart(2, "0")).join("-");
};

// Saves everything this browser keeps as a file, locked with ``phrase`` or the built-in key, with
// ``race``, the race on screen, to go back to. Returns the file's name.
export async function saveSession({ phrase: chosen = null, race = "" } = {}) {
  const name = `pallot-session-${today()}${EXTENSION}`;
  saveBytes(await pallotFile(buildSession(sessionStore(), { race }), chosen), name);
  return name;
}

// ---- what a file holds, and putting a session back -------------------------------------------

// What a file holds, a line each: where its ballot is ("1 Main St · U.S. House 10 · Pct 300"), and
// its picks and notes.
export function fileLines(slate) {
  const { races, notes } = slateCounts(slate);
  const where = [lookupLabel(slate.ballot), slate.districts?.line].filter(Boolean).join(" · ");
  const parts = [races && `picks in ${plural(races, "race")}`, notes && plural(notes, "note"), slate.session && "your settings"].filter(Boolean);
  const holds = parts.length ? `It has ${parts.join(", ").replace(/, ([^,]*)$/, " and $1")}` : "It has no picks or notes";
  return [where, `${holds}${slate.election.title ? `, for ${slate.election.title}` : ""}.`].filter(Boolean);
}

// Asks before putting a session back: when this browser keeps nothing, it's just restored; else the
// voter chooses to replace what's here or merge it. Once restored, the ballot page opens on it.
// Resolves false if the voter cancelled.
export async function offerSession(slate) {
  const body = fileLines(slate).map((line) => h("p", {}, line));
  let how = "replace";
  if (keepsAnything()) {
    how = await choiceDialog({
      title: "Restore this session?",
      body: [...body, h("p", {}, "This browser already keeps picks or settings. Where they differ from the file's:")],
      choices: [
        { value: "mine", label: "Merge, keep mine" },
        { value: "theirs", label: "Merge, the file's win" },
        { value: "replace", label: "Replace everything" },
      ],
    });
  } else if (!(await confirmDialog({ title: "Restore this session?", body, confirm: "Restore" }))) {
    how = null;
  }
  if (!how) return false;
  const before = restoreSession(slate.session.store, how);
  try {
    sessionStorage.setItem(RESTORED, JSON.stringify({ race: slate.session.race || "", before }));
  } catch {
    // no Undo, and no going back to the race, without it
  }
  location.assign("./");
  return true;
}

// On the ballot page, once its ballot is drawn after a restore: the race to go back to, and Undo.
export function takeRestored() {
  try {
    const restored = JSON.parse(sessionStorage.getItem(RESTORED));
    sessionStorage.removeItem(RESTORED);
    return restored && typeof restored === "object" ? restored : null;
  } catch {
    return null;
  }
}

export function offerUndoRestore(before) {
  showToast("Restored your session.", {
    label: "Undo",
    run: () => {
      undoRestore(before);
      location.reload();
    },
  });
}
