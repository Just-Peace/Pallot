// What Pallot keeps in this browser (localStorage). Nothing here is sent to the server, except
// the voter's choice of sources (SOURCES), which every call carries (api.js) so the server builds
// their ballot with them. If storage is blocked, reads give the fallback and writes are dropped.

export const PICKS = "pallot.picks.v1";
export const LAST_LOOKUP = "pallot.lastLookup.v1";
export const ADDRESS_CARD = "pallot.addressCard.v1";
export const SETTINGS_CHANGED = "pallot.settingsChanged.v1";
export const PICK_RULE = "pallot.pickRule.v1"; // Pick by rule's last rule, for every election
export const SOURCES = "pallot.sources.v1"; // the sources the voter turned on or off: id → true or false
export const UI = "pallot.ui.v1"; // the view settings (uiPref), several at once with setUiPrefs

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

// The voter's own switches in Settings; a source they haven't switched follows Pallot's default.
export const sourceChoices = () => readJson(SOURCES, {});

export function setSourceChoices(changes) {
  writeJson(SOURCES, { ...sourceChoices(), ...changes });
}

// A view setting: the appearance, the search engine, the folded left pane, Compare's scale, the map.
export const uiPref = (name) => readJson(UI, {})[name];

export function setUiPref(name, value) {
  setUiPrefs({ [name]: value });
}

export function setUiPrefs(changes) {
  writeJson(UI, { ...readJson(UI, {}), ...changes });
}

// Every key Pallot uses starts with "pallot.".
export function storedKeys() {
  try {
    return Object.keys(localStorage).filter((key) => key.startsWith("pallot."));
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
