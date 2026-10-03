// Light or dark: the voter's Appearance choice in Settings ("theme" in votebot.ui.v1), or the
// device's while it's "system". A classic script in every page's <head>, so <html> has its
// data-theme before the first paint; app.css's dark colours key off data-theme="dark". It
// follows the device, other tabs (storage) and Settings ("votebot:theme" on document).

(() => {
  const dark = matchMedia("(prefers-color-scheme: dark)");

  function choice() {
    try {
      return JSON.parse(localStorage.getItem("votebot.ui.v1"))?.theme;
    } catch {
      return undefined;
    }
  }

  function apply() {
    const theme = choice();
    document.documentElement.dataset.theme = theme === "light" || theme === "dark" ? theme : dark.matches ? "dark" : "light";
  }

  apply();
  dark.addEventListener("change", apply);
  window.addEventListener("storage", (event) => {
    if (event.key === null || event.key === "votebot.ui.v1") apply();
  });
  document.addEventListener("votebot:theme", apply);
})();
