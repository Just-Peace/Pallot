// The voter's picks and notes. They stay in this browser (localStorage) and are never
// sent to the server. If storage is blocked they still work until the page is closed.

import { ENDORSER_BAR, PICKS, PICK_RULE, SETTINGS_CHANGED, readJson, removeRaw, restoreRaw, storedKeys, writeJson } from "./storage.js";

export const WRITE_IN = "write-in"; // the pick key for a name the voter types in

// Each election's picks that storage refused, so they last until the page is closed.
let unsaved = {};
const savedListeners = [];

// Saves one election's picks over what's stored now, so picks another tab saved meanwhile,
// for other elections, aren't overwritten.
function saveBucket(electionKey, data) {
  const all = readJson(PICKS, {});
  all[electionKey] = data;
  if (writeJson(PICKS, all)) delete unsaved[electionKey];
  else unsaved[electionKey] = data;
  savedListeners.forEach((listener) => listener());
}

// Runs ``listener`` after every change of the picks in this tab: a pick, a note, a write-in.
export function onPicksSaved(listener) {
  savedListeners.push(listener);
}

// Runs ``redraw`` when another tab changes the picks (a pick, Clear in Settings).
export function onPicksChanged(redraw) {
  window.addEventListener("storage", (event) => {
    if (event.key === PICKS || event.key === null) redraw();
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

  // A pick by hand: the race's picks Help me pick's endorsers made stay theirs only while still picked.
  set(raceKey, candidateKeys) {
    if (candidateKeys.length) this.data.races[raceKey] = candidateKeys;
    else delete this.data.races[raceKey];
    this.setAuto(raceKey, this.auto(raceKey).filter((key) => candidateKeys.includes(key)));
    saveBucket(this.key, this.data);
  }

  // The picks in a race that Help me pick's endorsers made, which dropping them takes back; any
  // other pick there is the voter's own.
  auto(raceKey) {
    return this.data.auto?.[raceKey] || [];
  }

  setAuto(raceKey, candidateKeys) {
    this.data.auto ||= {};
    if (candidateKeys.length) this.data.auto[raceKey] = candidateKeys;
    else delete this.data.auto[raceKey];
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

  // Sets several races' picks with one save (Pick by rule, Help me pick), and returns what they were,
  // for Undo, as { picks, auto }. ``auto``: each race's picks Help me pick's endorsers made (else
  // those still picked stay theirs).
  setMany(changes, auto = null) {
    const before = { picks: {}, auto: {} };
    for (const [raceKey, keys] of Object.entries(changes)) {
      before.picks[raceKey] = this.picked(raceKey);
      before.auto[raceKey] = this.auto(raceKey);
      if (keys.length) this.data.races[raceKey] = keys;
      else delete this.data.races[raceKey];
      this.setAuto(raceKey, auto ? auto[raceKey] || [] : this.auto(raceKey).filter((key) => keys.includes(key)));
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
    const { races, notes, writeIns = {}, auto = {} } = this.data;
    this.data.races = {};
    this.data.notes = {};
    this.data.writeIns = {};
    this.data.auto = {};
    saveBucket(this.key, this.data);
    return { races, notes, writeIns, auto };
  }

  // Puts back what clear() returned: "Undo" after "Clear picks".
  restore({ races, notes, writeIns, auto = {} }) {
    Object.assign(this.data, { races, notes, writeIns, auto });
    saveBucket(this.key, this.data);
  }

  // Whether there's anything for clear() to clear.
  isEmpty() {
    return [this.data.races, this.data.notes, this.data.writeIns || {}].every((part) => !Object.keys(part).length);
  }
}

// Whether any election has a pick stored in this browser.
export const hasAnyPicks = () => Object.values(readJson(PICKS, {})).some((bucket) => Object.keys(bucket?.races || {}).length > 0);

// "Clear my picks & notes" in Settings: every election's picks, notes, write-ins and collapsed
// races, and the pick rule with Help me pick's choices. The remembered address stays. Returns what was removed, for Undo.
export function clearPicksAndNotes() {
  unsaved = {};
  return removeRaw([PICKS, PICK_RULE, ENDORSER_BAR]);
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
