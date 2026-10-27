// The voter's picks and notes. They stay in this browser (localStorage) and are never
// sent to the server. If storage is blocked they still work until the page is closed.

import { COLLAPSED, ENDORSER_BAR, PICKS, PICK_RULE, SETTINGS_CHANGED, readJson, removeRaw, restoreRaw, storedKeys, writeJson } from "./storage.js";

export const WRITE_IN = "write-in"; // the pick key for a name the voter types in
export const ANSWERS = [["yes", "Yes"], ["no", "No"]]; // a retention question's pick keys, with their words

const UNDATED = "undated";
const KEEP_DAYS = 90; // an election's picks, notes and folded races are forgotten this long after it
const DAY = 24 * 60 * 60 * 1000;
const DATED = /^\d{4}-\d{2}-\d{2}$/; // a bucket's key when the election has a date

// Each election's picks and folded races that storage refused, so they last until the page is closed.
let unsaved = {};
let unsavedCollapsed = {};
const savedListeners = [];

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

// A stored bucket with the parts every reader indexes, or null when it isn't a bucket at all (a future
// version's, a hand edit, a partial write), so a bad one can't leave the ballot blank.
function normalize(bucket) {
  if (!isObject(bucket)) return null;
  return { ...bucket, races: isObject(bucket.races) ? bucket.races : {}, notes: isObject(bucket.notes) ? bucket.notes : {} };
}

const storedBuckets = () => {
  const all = readJson(PICKS, {});
  return isObject(all) ? all : {};
};

const storedCollapsed = () => {
  const all = readJson(COLLAPSED, {});
  return isObject(all) ? all : {};
};

// Saves one election's picks over what's stored now, so picks another tab saved meanwhile,
// for other elections, aren't overwritten. A bucket with no election date is stamped, as it has
// no date to be forgotten by.
function saveBucket(electionKey, data) {
  if (!DATED.test(electionKey)) data.saved_at = Date.now();
  const all = storedBuckets();
  all[electionKey] = data;
  if (writeJson(PICKS, all)) delete unsaved[electionKey];
  else unsaved[electionKey] = data;
  savedListeners.forEach((listener) => listener());
}

// When a ballot loads: forgets the picks, notes, write-ins and folded races of elections more than
// KEEP_DAYS past (an undated bucket KEEP_DAYS after it was last saved), as they're the most personal
// thing Pallot keeps, drops buckets that aren't buckets, and moves folded races kept in the picks
// before they had a key of their own into it, once. ``current``, the election shown, is never forgotten.
function tidy(current, now = Date.now()) {
  const buckets = storedBuckets();
  const collapsed = storedCollapsed();
  let changed = false;
  let moved = false;
  for (const [key, raw] of Object.entries(buckets)) {
    const bucket = normalize(raw);
    if (!bucket) {
      delete buckets[key];
      changed = true;
      continue;
    }
    if ("collapsed" in bucket) {
      if (isObject(bucket.collapsed)) collapsed[key] = { ...bucket.collapsed, ...collapsed[key] };
      delete bucket.collapsed;
      buckets[key] = bucket;
      changed = moved = true;
    }
    if (!DATED.test(key) && typeof bucket.saved_at !== "number") {
      buckets[key] = { ...bucket, saved_at: now };
      changed = true;
    }
  }
  const expired = new Set([...Object.keys(buckets), ...Object.keys(collapsed)].filter((key) => {
    if (key === current) return false;
    const since = DATED.test(key) ? Date.parse(key) : buckets[key]?.saved_at;
    return Number.isFinite(since) && since + KEEP_DAYS * DAY < now;
  }));
  for (const key of Object.keys(buckets).filter((key) => expired.has(key))) {
    delete buckets[key];
    delete unsaved[key];
    changed = true;
  }
  let collapsedChanged = moved;
  for (const key of Object.keys(collapsed).filter((key) => expired.has(key) || !isObject(collapsed[key]))) {
    delete collapsed[key];
    delete unsavedCollapsed[key];
    collapsedChanged = true;
  }
  if (collapsedChanged && !writeJson(COLLAPSED, collapsed) && moved) return; // the folds stay where they were
  if (changed) writeJson(PICKS, buckets);
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
    this.key = electionKey || UNDATED;
    tidy(this.key);
    this.collapsed = { ...(unsavedCollapsed[this.key] || storedCollapsed()[this.key]) };
    this.reload();
  }

  // Reads its election's bucket again, after another tab changed it, so whoever holds this
  // object sees the change.
  reload() {
    this.data = unsaved[this.key] || normalize(storedBuckets()[this.key]) || { races: {}, notes: {} };
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

  // Which race cards the voter collapsed: a view setting, kept apart from the picks so folding a race
  // doesn't rewrite them or redraw other tabs, and kept by "Clear picks".
  isCollapsed(raceKey) {
    return Boolean(this.collapsed[raceKey]);
  }

  // Saves only these races over what's stored, so races another tab folded meanwhile stay folded.
  setCollapsed(raceKeys, collapsed) {
    const all = storedCollapsed();
    const stored = { ...(unsavedCollapsed[this.key] || all[this.key]) };
    for (const key of [].concat(raceKeys)) {
      for (const map of [this.collapsed, stored]) {
        if (collapsed) map[key] = true;
        else delete map[key];
      }
    }
    if (Object.keys(stored).length) all[this.key] = stored;
    else delete all[this.key];
    if (writeJson(COLLAPSED, all)) delete unsavedCollapsed[this.key];
    else unsavedCollapsed[this.key] = stored;
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

  // Puts in what a picks file or link brings (share.js's planImport) with one save, as the voter's
  // own picks, and returns what was there, for restore().
  merge({ races = {}, writeIns = {}, notes = {} }) {
    const before = structuredClone({ races: this.data.races, notes: this.data.notes, writeIns: this.data.writeIns || {}, auto: this.data.auto || {} });
    for (const [raceKey, keys] of Object.entries(races)) {
      this.data.races[raceKey] = keys;
      this.setAuto(raceKey, []);
    }
    this.data.writeIns = { ...this.data.writeIns, ...writeIns };
    Object.assign(this.data.notes, notes);
    saveBucket(this.key, this.data);
    return before;
  }

  // Puts back what clear() or merge() returned: "Undo" after "Clear picks", or after opening picks.
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
export const hasAnyPicks = () => Object.values(storedBuckets()).some((bucket) => Object.keys(normalize(bucket)?.races || {}).length > 0);

// "Clear my picks & notes" in Settings: every election's picks, notes, write-ins and collapsed
// races, and the pick rule with Help me pick's choices. The remembered address stays. Returns what was removed, for Undo.
export function clearPicksAndNotes() {
  unsaved = {};
  unsavedCollapsed = {};
  return removeRaw([PICKS, COLLAPSED, PICK_RULE, ENDORSER_BAR]);
}

// "Clear browser data" in Settings: everything Pallot keeps in this browser, the remembered
// address and the search engine included. Returns what was removed, for Undo. The settings
// stamp stays: it isn't the voter's, and the caller renews it.
export function clearBrowserData() {
  unsaved = {};
  unsavedCollapsed = {};
  return removeRaw(storedKeys().filter((key) => key !== SETTINGS_CHANGED));
}

// Undo in Settings: puts back what clearPicksAndNotes() or clearBrowserData() removed.
export const restoreBrowserData = restoreRaw;
