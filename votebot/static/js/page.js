// Shared by every page except the ballot: draws the icons and shows the remembered address
// under "Your ballot" in the left pane.

import { showRememberedAddress } from "./address.js";
import { hydrateIcons } from "./icons.js";

showRememberedAddress();
hydrateIcons();

// The address may have changed on the ballot page since this page was drawn (another tab,
// or the browser's Back button showing this page as it was left).
window.addEventListener("pageshow", (event) => {
  if (event.persisted) showRememberedAddress();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) showRememberedAddress();
});
