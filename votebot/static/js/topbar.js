// Phones and narrow windows (960px and less): the left pane becomes a one-line top bar, with
// the address and the page links each behind a button. The buttons are added from here, so
// the five pages' copies of the left pane stay as they are; wider, the CSS hides them.

import { h } from "./dom.js";
import { icon } from "./icons.js";

const sidebar = document.querySelector(".sidebar");
const addressPanel = sidebar?.querySelector(".side-address");
const navs = [...(sidebar?.querySelectorAll(".site-nav") || [])];

const addressLabel = h("span", { class: "topbar-address" }, "Your address");
const buttons = {
  address: h("button", { type: "button", class: "topbar-btn", "aria-expanded": "false" }, icon("pin"), addressLabel),
  menu: h("button", { type: "button", class: "topbar-btn", "aria-expanded": "false" }, icon("menu"), "Menu"),
};

// Shows one panel ("address" or "menu") under the top bar, or none. No effect when wide.
export function openPanel(name) {
  if (!sidebar) return;
  if (name) sidebar.dataset.open = name;
  else delete sidebar.dataset.open;
  for (const [key, button] of Object.entries(buttons)) button.setAttribute("aria-expanded", String(key === name));
}

// The address button's label: the street part of the address.
export function setTopBarAddress(address) {
  addressLabel.textContent = address ? address.split(",")[0].trim() : "Your address";
  buttons.address.title = address || "";
}

if (sidebar && addressPanel) {
  addressPanel.id ||= "side-address";
  navs.forEach((nav, i) => { nav.id ||= `site-nav-${i + 1}`; });
  buttons.address.setAttribute("aria-controls", addressPanel.id);
  buttons.menu.setAttribute("aria-controls", navs.map((nav) => nav.id).join(" "));
  for (const [name, button] of Object.entries(buttons)) {
    button.addEventListener("click", () => openPanel(sidebar.dataset.open === name ? null : name));
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
}
