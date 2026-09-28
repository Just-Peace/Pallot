// The voter's picks and notes. They stay in this browser (localStorage) and are never
// sent to the server. If storage is blocked they still work until the page is closed.

const PICKS_KEY = "votebot.picks.v1";
const LOOKUP_KEY = "votebot.lastLookup.v1";
const UI_KEY = "votebot.ui.v1";

export const WRITE_IN = "write-in"; // the pick key for a name the voter types in

let memory = null;

function readAll() {
  if (memory) return memory;
  try {
    memory = JSON.parse(localStorage.getItem(PICKS_KEY) || "{}") || {};
  } catch {
    memory = {};
  }
  return memory;
}

function writeAll() {
  try {
    localStorage.setItem(PICKS_KEY, JSON.stringify(memory));
  } catch {
    // storage unavailable: keep going in memory
  }
}

export class Picks {
  // One bucket per election date; candidate/race keys are stable ids from the server.
  constructor(electionKey) {
    const all = readAll();
    this.data = all[electionKey || "undated"] ||= { races: {}, notes: {} };
  }

  picked(raceKey) {
    return this.data.races[raceKey] || [];
  }

  isPicked(raceKey, candidateKey) {
    return this.picked(raceKey).includes(candidateKey);
  }

  set(raceKey, candidateKeys) {
    if (candidateKeys.length) this.data.races[raceKey] = candidateKeys;
    else delete this.data.races[raceKey];
    writeAll();
  }

  note(candidateKey) {
    return this.data.notes[candidateKey] || "";
  }

  setNote(candidateKey, text) {
    if (text.trim()) this.data.notes[candidateKey] = text;
    else delete this.data.notes[candidateKey];
    writeAll();
  }

  writeIn(raceKey) {
    return this.data.writeIns?.[raceKey] || "";
  }

  setWriteIn(raceKey, name) {
    this.data.writeIns ||= {};
    if (name.trim()) this.data.writeIns[raceKey] = name;
    else delete this.data.writeIns[raceKey];
    writeAll();
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
    writeAll();
  }

  clear() {
    this.data.races = {};
    this.data.notes = {};
    this.data.writeIns = {};
    writeAll();
  }
}

export function loadUi() {
  try {
    return JSON.parse(localStorage.getItem(UI_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

export function saveUi(prefs) {
  try {
    localStorage.setItem(UI_KEY, JSON.stringify(prefs));
  } catch {
    // not remembered; fine
  }
}

export function clearAllPicks() {
  memory = {};
  try {
    localStorage.removeItem(PICKS_KEY);
    localStorage.removeItem(LOOKUP_KEY);
  } catch {
    // nothing stored
  }
}

export function saveLastLookup(request) {
  try {
    localStorage.setItem(LOOKUP_KEY, JSON.stringify(request));
  } catch {
    // not remembered; fine
  }
}

export function loadLastLookup() {
  try {
    return JSON.parse(localStorage.getItem(LOOKUP_KEY) || "null");
  } catch {
    return null;
  }
}
