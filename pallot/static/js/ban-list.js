// The voter's ban list, kept only in this browser (BAN_LIST): entries of { text, plain }. A name
// banned from Details is plain text; an entry typed in Settings is a regular expression (plain
// text when it isn't a valid one). Either matches any part of a candidate's name, ignoring case,
// and a candidate it matches gets a red Banned pill beside their name (labels.js). Nothing is
// sent to the server.

import { BAN_LIST, writeJson } from "./storage.js";

let stored = { raw: undefined, entries: [] }; // the list as last read, kept until its stored text changes

function parse(raw) {
  let saved = null;
  try {
    saved = JSON.parse(raw);
  } catch {
    // not JSON: an empty list
  }
  return Array.isArray(saved) ? saved.filter((entry) => typeof entry?.text === "string" && entry.text.trim()) : [];
}

// The same entries (and their compiled patterns) until the stored list changes, here or in another tab.
export function banList() {
  let raw = null;
  try {
    raw = localStorage.getItem(BAN_LIST);
  } catch {
    // storage blocked: an empty list
  }
  if (raw !== stored.raw) stored = { raw, entries: parse(raw) };
  return [...stored.entries];
}

// Whether it was stored.
export const setBanList = (entries) => writeJson(BAN_LIST, entries);

export function isPattern(text) {
  try {
    new RegExp(text.trim(), "i");
    return true;
  } catch {
    return false;
  }
}

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const compiled = new WeakMap(); // entry -> its RegExp
function banPattern(entry) {
  let pattern = compiled.get(entry);
  if (!pattern) {
    const { text, plain } = entry;
    pattern = new RegExp(plain || !isPattern(text) ? escape(text.trim()) : text.trim(), "i");
    compiled.set(entry, pattern);
  }
  return pattern;
}

// The entries that match ``name``.
export function banMatches(name, entries = banList()) {
  return name ? entries.filter((entry) => banPattern(entry).test(name)) : [];
}

export const isBanned = (candidate) => banMatches(candidate.name).length > 0;

// Adds ``name`` as plain text, unless it's there already. Whether it was stored.
export function banName(name) {
  const entries = banList();
  if (entries.some((entry) => entry.text.toLowerCase() === name.toLowerCase())) return true;
  return setBanList([...entries, { text: name, plain: true }]);
}

// Takes off every entry that matches ``name`` and returns them, for Undo (restoreBans).
export function unbanName(name) {
  const entries = banList();
  const removed = banMatches(name, entries);
  setBanList(entries.filter((entry) => !removed.includes(entry)));
  return removed;
}

export function restoreBans(entries) {
  const kept = banList();
  setBanList([...kept, ...entries.filter((entry) => !kept.some((k) => k.text === entry.text))]);
}

// Hears a change to the ban list made in another tab.
export function onBanListChanged(run) {
  addEventListener("storage", (event) => {
    if (event.key === BAN_LIST || event.key === null) run();
  });
}
