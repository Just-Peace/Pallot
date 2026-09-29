// A message at the foot of the window for 10 seconds, with an optional action such as Undo:
// clearing the voter's own data happens at once and can be put back, rather than asking first.
// The element stays in the page while empty, so screen readers announce each new message.

import { h } from "./dom.js";

const toast = h("div", { class: "toast", role: "status", "aria-live": "polite" });
document.body.append(toast);
let timer = null;

// ``action``: { label, run }, a button after the message; it closes the toast, then runs.
export function showToast(message, action = null) {
  clearTimeout(timer);
  let button = null;
  if (action) {
    button = h("button", { type: "button", class: "link-btn" }, action.label);
    button.addEventListener("click", () => {
      hideToast();
      action.run();
    });
  }
  toast.replaceChildren(h("span", {}, message), button ?? "");
  timer = setTimeout(hideToast, 10000);
}

export function hideToast() {
  clearTimeout(timer);
  toast.replaceChildren();
}
