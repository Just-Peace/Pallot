// A whole session: everything Pallot keeps in this browser (storage.js), as a Pallot file holds it
// (share.js's buildSession), and putting one back: replacing what's here, or merged with it, the
// file's or this browser's winning where they differ, with what was here kept for Undo. An address
// the file has that's the same as this browser's, or for the same districts, leaves this browser's.

import { sameDistricts, samePlace } from "./share.js";
import { ADDRESS_CARD, LAST_DISTRICTS, LAST_LOOKUP, SETTINGS_CHANGED, removeRaw, restoreRaw, storedKeys } from "./storage.js";

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const kept = () => storedKeys().filter((key) => key !== SETTINGS_CHANGED);
const PLACE = ["address", "state", "county", "precinct", "districts", "precincts"];

function parsed(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// Every key this browser keeps, as stored, but the settings stamp, which isn't the voter's.
export function sessionStore() {
  const store = {};
  try {
    for (const key of kept()) store[key] = localStorage.getItem(key);
  } catch {
    // nothing stored
  }
  return store;
}

export const keepsAnything = () => kept().length > 0;

// Two values of one key merged: objects key by key, all the way down; a list that is the whole value
// (the Avoid list, the tips seen) joined; anything else the winner's.
function merge(mine, theirs, theirsWin, top = true) {
  if (isObject(mine) && isObject(theirs)) {
    const out = { ...mine };
    for (const [key, value] of Object.entries(theirs)) out[key] = key in mine ? merge(mine[key], value, theirsWin, false) : value;
    return out;
  }
  if (top && Array.isArray(mine) && Array.isArray(theirs)) {
    const seen = new Set(mine.map((item) => JSON.stringify(item)));
    return [...mine, ...theirs.filter((item) => !seen.has(JSON.stringify(item)))];
  }
  return theirsWin ? theirs : mine;
}

// Puts ``store`` (a file's) in this browser: ``how`` "replace" for it alone, "theirs" merged with the
// file's winning, "mine" merged with this browser's winning. Returns what was here, for undoRestore().
export function restoreSession(store, how) {
  const before = removeRaw(kept());
  const next = { ...store };
  if (how !== "replace") {
    for (const [key, raw] of Object.entries(before)) {
      if (!(key in next)) next[key] = raw;
      else if (how === "mine") next[key] = raw;
      const a = parsed(raw);
      const b = parsed(store[key]);
      if (key in store && a !== null && b !== null) next[key] = JSON.stringify(merge(a, b, how === "theirs"));
    }
  }
  const mine = parsed(before[LAST_LOOKUP]);
  const theirs = parsed(store[LAST_LOOKUP]);
  if (mine && theirs && (samePlace(mine, theirs) || sameDistricts(parsed(before[LAST_DISTRICTS]), parsed(store[LAST_DISTRICTS])))) {
    const place = Object.fromEntries(Object.entries(mine).filter(([key]) => PLACE.includes(key)));
    const rest = Object.fromEntries(Object.entries(theirs).filter(([key]) => !PLACE.includes(key)));
    next[LAST_LOOKUP] = JSON.stringify(how === "mine" ? mine : { ...place, ...rest });
    for (const key of [ADDRESS_CARD, LAST_DISTRICTS]) {
      if (key in before) next[key] = before[key];
      else delete next[key];
    }
  }
  restoreRaw(next);
  return before;
}

// Undo after restoreSession(): this browser as it was.
export function undoRestore(before) {
  removeRaw(kept());
  restoreRaw(before);
}
