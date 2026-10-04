// The voter's picks and notes. They stay in this browser (localStorage) and are never
// sent to the server. If storage is blocked they still work until the page is closed.

import { PICKS, PICK_RULE, SETTINGS_CHANGED, readJson, removeRaw, restoreRaw, storedKeys, writeJson } from "./storage.js";

export const WRITE_IN = "write-in"; // the pick key for a name the voter types in

// Each election's picks that storage refused, so they last until the page is closed.
let unsaved = {};

// Saves one election's picks over what's stored now, so picks another tab saved meanwhile,
// for other elections, aren't overwritten.
function saveBucket(electionKey, data) {
  const all = readJson(PICKS, {});
  all[electionKey] = data;
  if (writeJson(PICKS, all)) delete unsaved[electionKey];
  else unsaved[electionKey] = data;
}

// Runs ``redraw`` when another tab changes the picks or the pick rule (a pick, Clear in Settings).
export function onPicksChanged(redraw) {
  window.addEventListener("storage", (event) => {
    if (event.key === PICKS || event.key === PICK_RULE || event.key === null) redraw();
  });
}

export class Picks {
  // One bucket per election date; candidate/race keys are stable ids from the server.
  constructor(electionKey) {
    this.key = electionKey || "undated";
    this.reload();
  }

  // Reads its election's bucket again, after another tab changed it, so whoever holds this
  // object sees the change.
  reload() {
    this.data = unsaved[this.key] || readJson(PICKS, {})[this.key] || { races: {}, notes: {} };
  }

  picked(raceKey) {
    return this.data.races[raceKey] || [];
  }

  has(raceKey) {
    return this.picked(raceKey).length > 0;
  }

  // How many of ``raceKeys`` have a pick.
  countPicked(raceKeys) {
    return raceKeys.filter((key) => this.has(key)).length;
  }

  isPicked(raceKey, candidateKey) {
    return this.picked(raceKey).includes(candidateKey);
  }

  set(raceKey, candidateKeys) {
    if (candidateKeys.length) this.data.races[raceKey] = candidateKeys;
    else delete this.data.races[raceKey];
    saveBucket(this.key, this.data);
  }

  note(candidateKey) {
    return this.data.notes[candidateKey] || "";
  }

  setNote(candidateKey, text) {
    if (text.trim()) this.data.notes[candidateKey] = text;
    else delete this.data.notes[candidateKey];
    saveBucket(this.key, this.data);
  }

  writeIn(raceKey) {
    return this.data.writeIns?.[raceKey] || "";
  }

  // The write-in as the collapsed race and the print sheet show it; ``blank`` until a name is typed.
  writeInLabel(raceKey, blank) {
    const name = this.writeIn(raceKey).trim();
    return name ? `${name} (write-in)` : blank;
  }

  setWriteIn(raceKey, name) {
    this.data.writeIns ||= {};
    if (name.trim()) this.data.writeIns[raceKey] = name;
    else delete this.data.writeIns[raceKey];
    saveBucket(this.key, this.data);
  }

  // Sets several races' picks with one save (Pick by rule), and returns what they were, for Undo.
  setMany(changes) {
    const before = {};
    for (const [raceKey, keys] of Object.entries(changes)) {
      before[raceKey] = this.picked(raceKey);
      if (keys.length) this.data.races[raceKey] = keys;
      else delete this.data.races[raceKey];
    }
    saveBucket(this.key, this.data);
    return before;
  }

  // Which race cards the voter collapsed (a view setting, kept by "Clear picks").
  isCollapsed(raceKey) {
    return Boolean(this.data.collapsed?.[raceKey]);
  }

  setCollapsed(raceKeys, collapsed) {
    this.data.collapsed ||= {};
    for (const key of [].concat(raceKeys)) {
      if (collapsed) this.data.collapsed[key] = true;
      else delete this.data.collapsed[key];
    }
    saveBucket(this.key, this.data);
  }

  // Clears the picks, notes and write-ins (not the collapsed races), and returns them for restore().
  clear() {
    const { races, notes, writeIns = {} } = this.data;
    this.data.races = {};
    this.data.notes = {};
    this.data.writeIns = {};
    saveBucket(this.key, this.data);
    return { races, notes, writeIns };
  }

  // Puts back what clear() returned: "Undo" after "Clear picks".
  restore({ races, notes, writeIns }) {
    Object.assign(this.data, { races, notes, writeIns });
    saveBucket(this.key, this.data);
  }

  // Whether there's anything for clear() to clear.
  isEmpty() {
    return [this.data.races, this.data.notes, this.data.writeIns || {}].every((part) => !Object.keys(part).length);
  }
}

// "Clear my picks & notes" in Settings: every election's picks, notes, write-ins and collapsed
// races, and the pick rule. The remembered address stays. Returns what was removed, for Undo.
export function clearPicksAndNotes() {
  unsaved = {};
  return removeRaw([PICKS, PICK_RULE]);
}

// "Clear browser data" in Settings: everything Pallot keeps in this browser, the remembered
// address and the search engine included. Returns what was removed, for Undo. The settings
// stamp stays: it isn't the voter's, and the caller renews it.
export function clearBrowserData() {
  unsaved = {};
  return removeRaw(storedKeys().filter((key) => key !== SETTINGS_CHANGED));
}

// Undo in Settings: puts back what clearPicksAndNotes() or clearBrowserData() removed.
export const restoreBrowserData = restoreRaw;
