// Shared by every page except the ballot: draws the left pane and the icons, lists the page's
// sections in it, shows the remembered address under "Your ballot", and opens the FAQ answer a
// link points to. The Settings page's settings.js imports it first.

import { showRememberedAddress } from "./address.js";
import { initChrome } from "./chrome.js";
import { h, onFrame, onReturn } from "./dom.js";
import { hydrateIcons, icon } from "./icons.js";
import { openPanel } from "./topbar.js";

// The page's sections (each <section> in <main>, named by the heading it's labelled by), listed
// in the left pane above the other pages, as the ballot lists its own. It goes in the aside
// before initChrome() draws the pane, which keeps it there. The section on screen is marked as
// the page scrolls: the last whose top has reached the line a jump scrolls to (the last at the
// foot of the page), or the one just jumped to while it's in view, until the voter scrolls, since
// a short section near the end never reaches that line. On a phone the list is in the Menu panel, which a jump
// closes; in the folded rail it's hidden.
function listSections() {
  const sidebar = document.querySelector(".sidebar");
  const entries = [...document.querySelectorAll("main > section[aria-labelledby]")].flatMap((section) => {
    const heading = document.getElementById(section.getAttribute("aria-labelledby"));
    return heading ? [{ section, link: h("a", { href: `#${heading.id}` }, heading.textContent.trim()) }] : [];
  });
  if (!sidebar || entries.length < 2) return;
  let jumped = null;
  const mark = () => {
    const html = document.documentElement;
    const line = (parseFloat(getComputedStyle(html).scrollPaddingTop) || 0) + 4;
    const top = (entry) => entry.section.getBoundingClientRect().top;
    let current = entries[0];
    for (const entry of entries) if (top(entry) <= line) current = entry;
    if (innerHeight + scrollY >= html.scrollHeight - 2) current = entries[entries.length - 1];
    if (jumped && top(jumped) >= 0 && top(jumped) < innerHeight) current = jumped;
    for (const { link } of entries) {
      if (link === current.link) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
  };
  for (const entry of entries) {
    entry.link.addEventListener("click", () => {
      openPanel(null);
      jumped = entry;
    });
  }
  sidebar.append(h("nav", { class: "side-section page-sections", "aria-labelledby": "page-sections-title" },
    h("h2", { class: "side-title", id: "page-sections-title" }, icon("list"), "Sections"),
    h("ul", { class: "jump-list" }, entries.map(({ link }) => h("li", {}, link)))));
  for (const type of ["wheel", "touchmove", "keydown"]) addEventListener(type, () => { jumped = null; }, { passive: true });
  addEventListener("scroll", onFrame(mark), { passive: true });
  addEventListener("resize", onFrame(mark));
  mark();
}

listSections();
initChrome();
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
onReturn(showRememberedAddress);
