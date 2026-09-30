// Shared by every page except the ballot: draws the left pane and the icons, shows the
// remembered address under "Your ballot", and opens the FAQ answer a link points to.

import "./chrome.js";
import { showRememberedAddress } from "./address.js";
import { hydrateIcons } from "./icons.js";

showRememberedAddress();
hydrateIcons();

// A link to one FAQ answer (faq.html#tec-money) opens it: not every browser opens a closed
// <details> for its #id.
function openLinkedAnswer() {
  const target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  const answer = target?.closest("details");
  if (!answer) return;
  answer.open = true;
  target.scrollIntoView();
}
openLinkedAnswer();
window.addEventListener("hashchange", openLinkedAnswer);

// The address may have changed on the ballot page since this page was drawn (another tab,
// or the browser's Back button showing this page as it was left).
window.addEventListener("pageshow", (event) => {
  if (event.persisted) showRememberedAddress();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) showRememberedAddress();
});
