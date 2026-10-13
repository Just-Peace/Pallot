// The More sheet: on narrow screens the toolbar stays under the heading and scrolls away, so More,
// in the sticky strip, opens a sheet from the foot of the screen with what the voter may want from
// anywhere on the ballot. The sheet is a container: each part of the page adds its own section with
// addMoreSection(), and moreAction() makes a button that closes the sheet before it runs.

import { $, closeOnBackdrop, h } from "./dom.js";
import { icon } from "./icons.js";

const sheet = $("#more-sheet");
const body = $("#more-body");

// Adds a section under its heading, or after the section ``after`` (an id given earlier), and returns it.
export function addMoreSection({ id, label, after = null }, ...children) {
  const section = h("section", { class: "sheet-section", "data-section": id, "aria-labelledby": `more-${id}` },
    h("h3", { class: "sheet-label", id: `more-${id}` }, label), children);
  const before = after ? body.querySelector(`[data-section="${after}"]`)?.nextElementSibling : null;
  body.insertBefore(section, before ?? null);
  return section;
}

// A row of the sheet: an icon and a label. ``props`` are the button's own (a class, an id).
export function moreAction(label, iconName, run, props = {}) {
  const click = () => {
    sheet.close();
    run();
  };
  return h("button", { type: "button", ...props, class: ["sheet-action", props.class], on: { click } }, icon(iconName), label);
}

export function initMoreSheet(button) {
  closeOnBackdrop(sheet);
  button.addEventListener("click", () => sheet.showModal());
}
