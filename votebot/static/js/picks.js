// The voter's picks and notes. They stay in this browser (localStorage) and are never
// sent to the server. If storage is blocked they still work until the page is closed.

const PICKS_KEY = "votebot.picks.v1";
const LOOKUP_KEY = "votebot.lastLookup.v1";
const UI_KEY = "votebot.ui.v1";
const SETTINGS_CHANGED_KEY = "votebot.settingsChanged.v1";
const ADDRESS_CARD_KEY = "votebot.addressCard.v1";

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

  // The write-in as the collapsed race and the print sheet show it; ``blank`` until a name is typed.
  writeInLabel(raceKey, blank) {
    const name = this.writeIn(raceKey).trim();
    return name ? `${name} (write-in)` : blank;
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

// The Settings page stamps every change that affects the ballot, so a ballot page that was
// open meanwhile (in another tab, or kept for the Back button) can tell it's out of date.
export function markSettingsChanged() {
  try {
    localStorage.setItem(SETTINGS_CHANGED_KEY, String(Date.now()));
  } catch {
    // storage unavailable: nothing else can have remembered the old settings either
  }
}

export function settingsStamp() {
  try {
    return localStorage.getItem(SETTINGS_CHANGED_KEY);
  } catch {
    return null;
  }
}

// "Clear my picks & notes" in Settings: every election's picks, notes, write-ins and collapsed
// races. The remembered address stays.
export function clearPicksAndNotes() {
  memory = {};
  try {
    localStorage.removeItem(PICKS_KEY);
  } catch {
    // nothing stored
  }
}

// "Clear all browser data" in Settings: everything VoteBot keeps in this browser, the remembered
// address and the search engine included. Every key it uses starts with "votebot.".
export function clearBrowserData() {
  memory = {};
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("votebot.")) localStorage.removeItem(key);
    }
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

// What the left pane's address card shows for the last lookup (the address, its city and
// county, its districts), so every page can show it without looking the address up again.
export function saveAddressCard(card) {
  try {
    localStorage.setItem(ADDRESS_CARD_KEY, JSON.stringify(card));
  } catch {
    // not remembered; fine
  }
}

export function loadAddressCard() {
  try {
    return JSON.parse(localStorage.getItem(ADDRESS_CARD_KEY) || "null");
  } catch {
    return null;
  }
}

export function loadLastLookup() {
  try {
    return JSON.parse(localStorage.getItem(LOOKUP_KEY) || "null");
  } catch {
    return null;
  }
}
