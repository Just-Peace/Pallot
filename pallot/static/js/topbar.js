// Phones and narrow windows (``narrow`` in chrome.js): the left pane becomes a one-line top bar, with
// the address and the page links (and a page's sections) each behind a button. chrome.js draws the pane, then calls
// initTopBar() to add the two buttons; wider, the CSS hides them.

import { h } from "./dom.js";
import { icon } from "./icons.js";

let sidebar = null;
let openedAt = 0; // scrollY when the panel opened
const CLOSE_AFTER_SCROLL = 48;
const addressLabel = h("span", { class: "topbar-address" }, "Enter address");
let addressKnown = false;
// What the address button does with no address yet, in place of opening a panel with nothing in it:
// the ballot page's entry card (by default, from any other page).
let enterAddress = () => { location.href = "./#change"; };
const buttons = {
  address: h("button", { type: "button", class: "topbar-btn", "aria-expanded": "false" }, icon("pin"), addressLabel),
  menu: h("button", { type: "button", class: "topbar-btn", "aria-expanded": "false" }, icon("menu"), "Menu"),
};

// Shows one panel ("address" or "menu") under the top bar, or none. No effect when wide.
export function openPanel(name) {
  if (!sidebar) return;
  if (name) sidebar.dataset.open = name;
  else delete sidebar.dataset.open;
  openedAt = scrollY;
  for (const [key, button] of Object.entries(buttons)) button.setAttribute("aria-expanded", String(key === name));
}

// The address button's label: the street part of the address, or "Enter address" before there's one.
export function setTopBarAddress(address) {
  addressKnown = Boolean(address);
  addressLabel.textContent = address ? address.split(",")[0].trim() : "Enter address";
  buttons.address.title = address || "";
}

// What the address button does before there's an address (the ballot page: show its entry card).
export function onEnterAddress(run) {
  enterAddress = run;
}

export function initTopBar(pane) {
  const addressPanel = pane.querySelector(".side-address");
  const navs = [...pane.querySelectorAll(".site-nav, .page-sections")];
  if (!addressPanel) return;
  sidebar = pane;
  addressPanel.id ||= "side-address";
  navs.forEach((nav, i) => { nav.id ||= `site-nav-${i + 1}`; });
  buttons.address.setAttribute("aria-controls", addressPanel.id);
  buttons.menu.setAttribute("aria-controls", navs.map((nav) => nav.id).join(" "));
  for (const [name, button] of Object.entries(buttons)) {
    button.addEventListener("click", () => {
      if (name === "address" && !addressKnown) {
        openPanel(null);
        enterAddress();
        return;
      }
      openPanel(sidebar.dataset.open === name ? null : name);
    });
  }
  sidebar.querySelector(".brand").after(h("div", { class: "topbar-buttons" }, ...Object.values(buttons)));
  // Esc closes the open panel, unless it's in use (the address suggestions close first).
  document.addEventListener("keydown", (event) => {
    const open = sidebar.dataset.open;
    if (event.key !== "Escape" || event.defaultPrevented || !open || !buttons[open].offsetParent) return;
    if (event.target.closest?.("input, select, textarea")) return;
    openPanel(null);
    buttons[open].focus();
  });
  // Phones have no Esc: a tap outside the top bar closes the panel, and so does scrolling the page,
  // unless the voter is typing in it (a phone's keyboard scrolls the page), a dialog is asking, or
  // it's the ballot's entry card, which stays until it's sent or cancelled.
  const shown = () => sidebar.dataset.open && buttons[sidebar.dataset.open].offsetParent
    && !(sidebar.dataset.open === "address" && addressPanel.querySelector(".entry:not([hidden])"));
  document.addEventListener("pointerdown", (event) => {
    if (shown() && !sidebar.contains(event.target) && !event.target.closest?.("dialog")) openPanel(null);
  });
  addEventListener("scroll", () => {
    if (!shown() || sidebar.contains(document.activeElement) || document.querySelector("dialog[open]")) return;
    if (Math.abs(scrollY - openedAt) > CLOSE_AFTER_SCROLL) openPanel(null);
  }, { passive: true });
}
