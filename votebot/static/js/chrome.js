// The left pane every page shares, drawn into the page's <aside class="sidebar">: the brand,
// "Your ballot", the address card, then the other pages at the foot. A page can put its own
// parts in the aside: those marked data-slot="address" go under the address card (the
// ballot's form and status line), anything else goes above the other pages (the ballot's
// section list). Import this first, so the pane exists before a page's own code looks for it.

import { h } from "./dom.js";
import { icon, logo } from "./icons.js";
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
    h("a", { href: page.href, "aria-current": page.href === current ? "page" : null }, icon(page.icon), page.label))));
}

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
    h("nav", { class: "side-section site-nav", "aria-label": "Your ballot" }, pageList([BALLOT], current)),
    h("section", { class: "side-address", "aria-labelledby": "address-title" },
      h("h2", { class: "side-title", id: "address-title" }, icon("pin"), "Your address"),
      h("div", { class: "address-card", id: "address-card", hidden: true },
        h("p", { class: "address-line", id: "address-line" }),
        h("p", { class: "muted small", id: "address-sub" }),
        change),
      forAddress.length
        ? forAddress
        : h("p", { class: "muted small", id: "no-address" }, h("a", { href: BALLOT.href }, "Enter your address"), " to see your ballot.")),
    rest,
    h("nav", { class: "side-section site-nav side-bottom", "aria-label": "Settings and information" }, pageList(PAGES, current)),
  ));
  initTopBar(sidebar);
}

const sidebar = document.querySelector(".sidebar");
if (sidebar) renderSidebar(sidebar);
