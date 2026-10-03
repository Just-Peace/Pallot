// What VoteBot keeps in this browser (localStorage). Nothing here is sent to the server. If
// storage is blocked, reads give the fallback and writes are dropped.

export const PICKS = "votebot.picks.v1";
export const LAST_LOOKUP = "votebot.lastLookup.v1";
export const ADDRESS_CARD = "votebot.addressCard.v1";
export const SETTINGS_CHANGED = "votebot.settingsChanged.v1";
export const PICK_RULE = "votebot.pickRule.v1"; // Pick by rule's last rule, for every election
const UI = "votebot.ui.v1";

// The Settings page stamps every change that affects the ballot, so a ballot page that was
// open meanwhile (in another tab, or kept for the Back button) can tell it's out of date.
export const markSettingsChanged = () => writeJson(SETTINGS_CHANGED, Date.now());
export const settingsStamp = () => readJson(SETTINGS_CHANGED, null);

export function readJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

// Whether it was stored.
export function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

// A view setting: the appearance, the search engine, the folded left pane, Compare's scale, the map.
export const uiPref = (name) => readJson(UI, {})[name];

export function setUiPref(name, value) {
  writeJson(UI, { ...readJson(UI, {}), [name]: value });
}

// Every key VoteBot uses starts with "votebot.".
export function storedKeys() {
  try {
    return Object.keys(localStorage).filter((key) => key.startsWith("votebot."));
  } catch {
    return [];
  }
}

// Removes ``keys`` and returns what they held, for restoreRaw().
export function removeRaw(keys) {
  const removed = {};
  try {
    for (const key of keys) {
      const value = localStorage.getItem(key);
      if (value === null) continue;
      removed[key] = value;
      localStorage.removeItem(key);
    }
  } catch {
    // nothing stored
  }
  return removed;
}

export function restoreRaw(removed) {
  try {
    for (const [key, value] of Object.entries(removed)) localStorage.setItem(key, value);
  } catch {
    // storage unavailable: there was nothing to put back
  }
}
