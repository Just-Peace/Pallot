// What every page shares: the left pane, drawn into the page's <aside class="sidebar"> (the
// brand, "Your ballot", the address card, then the other pages at the foot), the footer pinned
// to the bottom of the window, and Back to top. A page can put its own parts in the aside: those
// marked data-slot="address" go under the address card (the ballot's form and status line),
// anything else goes above the other pages (the ballot's section list). Import this first, so
// the pane exists before a page's own code looks for it.
//
// Wider than 960px, « folds the pane into a rail of icons (remembered as paneCollapsed in
// votebot.ui.v1); the ballot then shows its sections as chips in the strip (onPaneToggle).

import { h } from "./dom.js";
import { icon, logo } from "./icons.js";
import { setUiPref, uiPref } from "./storage.js";
import { initTopBar } from "./topbar.js";

const BALLOT = { href: "./", icon: "ballot", label: "Your ballot" };
const PAGES = [
  { href: "settings.html", icon: "settings", label: "Settings" },
  { href: "faq.html", icon: "help", label: "FAQ" },
  { href: "about.html", icon: "info", label: "About" },
  { href: "privacy.html", icon: "shield", label: "Privacy" },
];

function currentHref() {
  const file = location.pathname.split("/").pop();
  return !file || file === "index.html" ? BALLOT.href : file;
}

function pageList(pages, current) {
  return h("ul", {}, pages.map((page) => h("li", {},
    h("a", { href: page.href, "aria-current": page.href === current ? "page" : null },
      icon(page.icon), h("span", { class: "nav-label" }, page.label)))));
}

// ---- folding the pane ------------------------------------------------------------------

const paneToggle = h("button", { type: "button", class: "icon-only pane-toggle" });
const paneListeners = [];

export function isPaneCollapsed() {
  return document.documentElement.classList.contains("pane-collapsed");
}

export function onPaneToggle(listener) {
  paneListeners.push(listener);
}

// Folds the pane to its rail of icons, or unfolds it. In the rail each link's name is a tooltip.
export function setPaneCollapsed(collapsed) {
  const changed = collapsed !== isPaneCollapsed();
  document.documentElement.classList.toggle("pane-collapsed", collapsed);
  const label = collapsed ? "Expand the left pane" : "Collapse the left pane";
  paneToggle.replaceChildren(icon(collapsed ? "chevrons-right" : "chevrons-left"));
  paneToggle.setAttribute("aria-label", label);
  paneToggle.title = label;
  for (const link of document.querySelectorAll(".sidebar .site-nav a")) {
    if (collapsed) link.title = link.textContent;
    else link.removeAttribute("title");
  }
  if (!changed) return;
  if (Boolean(uiPref("paneCollapsed")) !== collapsed) setUiPref("paneCollapsed", collapsed);
  for (const listener of paneListeners) listener();
}

paneToggle.addEventListener("click", () => setPaneCollapsed(!isPaneCollapsed()));

// ---- the pane ----------------------------------------------------------------------------

function renderSidebar(sidebar) {
  const current = currentHref();
  const own = [...sidebar.children];
  const forAddress = own.filter((el) => el.dataset.slot === "address");
  const rest = own.filter((el) => !forAddress.includes(el));
  const change = forAddress.length
    ? h("button", { class: "link-btn with-icon", id: "change-address", type: "button" }, icon("edit"), "Change")
    : h("a", { class: "link-btn with-icon", href: "./#change" }, icon("edit"), "Change");

  sidebar.replaceChildren(h("div", { class: "side-inner" },
    h("a", { class: "brand", href: BALLOT.href }, logo(), h("span", { class: "brand-name" }, "Vote", h("span", {}, "Bot"))),
    paneToggle,
    h("nav", { class: "side-section site-nav", "aria-label": "Your ballot" }, pageList([BALLOT], current)),
    h("section", { class: "side-address", "aria-label": "Your address" },
      h("div", { class: "address-card", id: "address-card", hidden: true },
        h("p", { class: "address-line", id: "address-line" }),
        h("p", { class: "muted small", id: "address-sub" }),
        h("p", { class: "muted small", id: "address-election", hidden: true }),
        change),
      forAddress.length
        ? forAddress
        : h("p", { class: "muted small", id: "no-address" }, h("a", { href: BALLOT.href }, "Enter your address"), " to see your ballot.")),
    rest,
    h("nav", { class: "side-section site-nav side-bottom", "aria-label": "Settings and information" }, pageList(PAGES, current)),
  ));
  initTopBar(sidebar);
}

// ---- the footer and Back to top -----------------------------------------------------------

function renderFooter(app) {
  const footer = h("footer", { class: "site-footer" },
    h("p", {}, "VoteBot is an unofficial helper: always check your county's official sample ballot. · ",
      h("a", { href: "about.html#credits" }, "Sources")));
  app.after(footer);
  // The content, Back to top and the toasts keep clear of it, however many lines it wraps to.
  new ResizeObserver(() => {
    document.documentElement.style.setProperty("--footer-h", `${footer.offsetHeight}px`);
  }).observe(footer);
}

function renderToTop() {
  const button = h("button", { type: "button", class: "to-top", "aria-label": "Back to top", title: "Back to top" }, icon("arrow-up"));
  button.addEventListener("click", () => {
    window.scrollTo({ top: 0 }); // smooth, unless reduced motion (the html's scroll-behavior)
    document.querySelector(".brand")?.focus({ preventScroll: true });
  });
  document.body.append(button);
  let pending = false;
  const sync = () => {
    pending = false;
    button.classList.toggle("shown", scrollY > innerHeight);
  };
  addEventListener("scroll", () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(sync);
  }, { passive: true });
  sync();
}

const sidebar = document.querySelector(".sidebar");
if (sidebar) {
  renderSidebar(sidebar);
  setPaneCollapsed(Boolean(uiPref("paneCollapsed")));
}
const app = document.querySelector(".app");
if (app) renderFooter(app);
renderToTop();
