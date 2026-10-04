// Light or dark: the voter's Appearance choice in Settings ("theme" in pallot.ui.v1), or the
// device's while it's "system". A classic script in every page's <head>, so <html> has its
// data-theme before the first paint; app.css's dark colours key off data-theme="dark". It
// follows the device, other tabs (storage) and Settings ("pallot:theme" on document).
// It also folds the left pane before the first paint when the voter left it folded
// (paneCollapsed), so it doesn't show open until chrome.js has loaded and draws it.

(() => {
  const dark = matchMedia("(prefers-color-scheme: dark)");

  function prefs() {
    try {
      return JSON.parse(localStorage.getItem("pallot.ui.v1")) ?? {};
    } catch {
      return {};
    }
  }

  function apply() {
    const theme = prefs().theme;
    document.documentElement.dataset.theme = theme === "light" || theme === "dark" ? theme : dark.matches ? "dark" : "light";
  }

  apply();
  if (prefs().paneCollapsed) document.documentElement.classList.add("pane-collapsed");
  dark.addEventListener("change", apply);
  window.addEventListener("storage", (event) => {
    if (event.key === null || event.key === "pallot.ui.v1") apply();
  });
  document.addEventListener("pallot:theme", apply);
})();
