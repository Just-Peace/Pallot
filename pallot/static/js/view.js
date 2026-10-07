// The View settings that shape the ballot, kept with the other view settings (storage.js,
// pallot.ui.v1). A switch the voter hasn't set follows VIEW_DEFAULTS, so a new default only
// changes the ballot of a voter who hasn't chosen.

import { setUiPref, uiPref } from "./storage.js";

export const VIEW_DEFAULTS = {
  showMap: false, // the map of your districts, folded at first
  showMoney: false, // each race's money box, folded at first
  collapseOnPick: true, // a race folds to one line once it's picked
  hidePicked: false, // only the races not picked yet
};

export function viewPref(name) {
  const value = uiPref(name);
  return typeof value === "boolean" ? value : VIEW_DEFAULTS[name];
}

export function setViewPref(name, value) {
  setUiPref(name, Boolean(value));
}
