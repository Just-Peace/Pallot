// A message at the foot of the window for 10 seconds, with an optional action such as Undo:
// clearing the voter's own data happens at once and can be put back, rather than asking first.
// The element is made the first time it's needed, then stays in the page while empty, so screen
// readers announce each new message; the first message waits a moment for them to notice it.

import { h } from "./dom.js";

let toast = null;
let timer = null;
let pending = null; // the first message, until it's shown

// ``action``: { label, run }, a button after the message; it closes the toast, then runs.
export function showToast(message, action = null) {
  hideToast();
  const run = () => {
    hideToast();
    action.run();
  };
  const show = () => {
    pending = null;
    toast.replaceChildren(h("span", {}, message), action ? h("button", { type: "button", class: "link-btn", on: { click: run } }, action.label) : "");
  };
  if (toast) {
    show();
  } else {
    toast = h("div", { class: "toast", role: "status", "aria-live": "polite" });
    document.body.append(toast);
    pending = setTimeout(show, 100);
  }
  timer = setTimeout(hideToast, 10000);
}

export function hideToast() {
  clearTimeout(timer);
  clearTimeout(pending);
  pending = null;
  toast?.replaceChildren();
}
