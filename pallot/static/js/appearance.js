// Appearance: System, Light or Dark, the "theme" view setting (storage.js) that theme.js, in every
// page's <head>, applies. Settings' Appearance and the View menu's toggle both set it here, and it
// applies at once, in this tab ("pallot:theme" on document) and in others (storage).

import { icon } from "./icons.js";
import { UI, setUiPref, uiPref } from "./storage.js";

export const THEMES = {
  system: { label: "System", icon: "monitor" },
  light: { label: "Light", icon: "sun" },
  dark: { label: "Dark", icon: "moon" },
};

export function currentTheme() {
  const theme = uiPref("theme");
  return Object.hasOwn(THEMES, theme ?? "") ? theme : "system";
}

// theme.js applies what's stored again, and every onThemeChange() callback runs.
export const applyTheme = () => document.dispatchEvent(new Event("pallot:theme"));

export function setTheme(theme) {
  setUiPref("theme", theme);
  applyTheme();
}

// ``callback`` runs after the appearance changes, on this page or in another tab.
export function onThemeChange(callback) {
  document.addEventListener("pallot:theme", callback);
  addEventListener("storage", (event) => {
    if (event.key === null || event.key === UI) callback();
  });
}

// One icon button stepping System → Light → Dark, its icon, name and tooltip saying which is on.
export function bindThemeToggle(button) {
  const order = Object.keys(THEMES);
  const next = () => order[(order.indexOf(currentTheme()) + 1) % order.length];
  const show = () => {
    const { label, icon: name } = THEMES[currentTheme()];
    button.replaceChildren(icon(name));
    button.setAttribute("aria-label", `Appearance: ${label}`);
    button.title = `Appearance: ${label}. Switch to ${THEMES[next()].label}`;
  };
  button.addEventListener("click", () => setTheme(next()));
  onThemeChange(show);
  show();
}
