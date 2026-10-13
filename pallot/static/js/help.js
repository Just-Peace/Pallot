// Help where it's needed: a "?" opening the FAQ's answer in a new tab, a note that opens over the
// page on a click or a tap (what a pill means, the Funding chips' colors), so nothing is told only in
// a tooltip, and the first-run tips, one at a time beside what they're about, each until "Got it".
// The tips seen are kept in this browser (TIPS); Settings' "Show tips again" forgets them.

import { extLink, h } from "./dom.js";
import { TIPS, readJson, writeJson } from "./storage.js";
import { showToast } from "./toast.js";

const popovers = () => typeof HTMLElement !== "undefined" && Object.hasOwn(HTMLElement.prototype, "popover");

// A "?" opening the FAQ's answer ``anchor`` in a new tab; ``topic`` names it for a screen reader.
export function helpLink(anchor, topic) {
  const name = `Help: ${topic}`;
  return h("a", { href: `faq.html#${anchor}`, target: "_blank", rel: "noopener", class: "help-link", title: name,
    "aria-label": `${name} (opens in a new tab)` }, "?");
}

// The one note over the page, made the first time it's needed; it goes into an open dialog when its
// button is in one, since the rest of the page is inert then. Scrolling closes it.
let note = null;
let noteFor = null; // the button it was last opened from
let closedAt = 0;

function noteBox() {
  if (note) return note;
  note = h("div", { id: "pop-note", popover: "auto", class: "pop-note" });
  note.addEventListener("toggle", (event) => {
    if (event.newState === "open") {
      document.addEventListener("scroll", hideNote, { capture: true, once: true, passive: true });
      return;
    }
    noteFor?.setAttribute("aria-expanded", "false");
    closedAt = performance.now();
  });
  return note;
}

function hideNote() {
  if (note?.matches(":popover-open")) note.hidePopover();
}

function placeNote(button) {
  const box = button.getBoundingClientRect();
  const below = box.bottom + 4;
  const fits = below + note.offsetHeight <= innerHeight - 8;
  note.style.top = `${fits ? below : Math.max(8, box.top - note.offsetHeight - 4)}px`;
  note.style.left = `${Math.max(8, Math.min(box.left, innerWidth - note.offsetWidth - 8))}px`;
}

// The click that closed the note by landing on its own button doesn't open it again.
function toggleNote(button, content) {
  if (!popovers()) {
    showToast(h("span", {}, content()));
    return;
  }
  const box = noteBox();
  if (noteFor === button && (box.matches(":popover-open") || performance.now() - closedAt < 400)) {
    hideNote();
    closedAt = 0;
    return;
  }
  hideNote();
  noteFor?.setAttribute("aria-expanded", "false");
  noteFor = button;
  (button.closest("dialog[open]") || document.body).append(box);
  box.replaceChildren(h("div", { class: "pop-note-body", "aria-live": "polite" }, content()));
  box.showPopover();
  button.setAttribute("aria-expanded", "true");
  placeNote(button);
}

// A button that opens ``content()`` (text, a node or a list of them) in the note. ``props`` are the
// button's own; its words say what it is, and the note says the rest.
export function noteButton(props, label, content) {
  const button = h("button", { type: "button", "aria-expanded": "false", "aria-controls": "pop-note", ...props,
    on: { click: (event) => {
      event.preventDefault();
      toggleNote(button, content);
    } } }, label);
  return button;
}

// The "?" beside a Funding line's heading: what the chips' colors and words mean.
export function fundingHelp() {
  return noteButton({ class: "help-link", "aria-label": "What the Funding chips' colors mean" }, "?", () => [
    h("p", {}, h("span", { class: "badge tone-good" }, "Green"), " Money from many people, from home."),
    h("p", {}, h("span", { class: "badge tone-warn" }, "Amber"), " From a few, from far away, or the candidate."),
    h("p", {}, h("span", { class: "badge tone-info" }, "Blue"), " Outside spending for them."),
    h("p", {}, h("strong", {}, "Mostly"), " is over half; ", h("strong", {}, "Overwhelmingly"), " over three quarters."),
    h("p", {}, extLink("faq.html#funding", "More on the Funding chips")),
  ]);
}

// ---- first-run tips ---------------------------------------------------------------------

const seen = () => new Set(readJson(TIPS, []));
let shown = null; // the tip showing, { id, box }, until its "Got it": one at a time

export function forgetTips() {
  writeJson(TIPS, []);
}

// Wholly in the window, and not hidden.
function onScreen(element) {
  if (!element?.isConnected || !element.getClientRects().length) return false;
  const box = element.getBoundingClientRect();
  return box.top >= 0 && box.bottom <= innerHeight;
}

// Shows the first of ``tips`` not seen yet whose ``when()`` holds and whose ``target()`` (an element
// or a list, the first on screen counting) is in the window, after ``after(target)`` (else the
// target), with an arrow at the target. No other shows until its "Got it", which runs ``next()`` to
// show the next one whose target is on screen; if the page drew it away before, only it may come back.
export function showTip(tips, next) {
  if (shown?.box.isConnected) return;
  const done = seen();
  for (const tip of shown ? tips.filter((t) => t.id === shown.id) : tips) {
    if (done.has(tip.id) || !tip.when()) continue;
    const target = [tip.target()].flat().find(onScreen);
    if (target) {
      drawTip(tip, target, next);
      return;
    }
  }
}

function drawTip(tip, target, next) {
  const got = h("button", { type: "button", class: "btn small", on: { click: () => {
    writeJson(TIPS, [...seen(), tip.id]);
    row.remove();
    shown = null;
    target.focus?.({ preventScroll: true });
    next?.();
  } } }, "Got it");
  const box = h("div", { class: "tip", role: "note" }, h("p", {}, tip.text()), got);
  const row = h("div", { class: "tip-row" }, box);
  (tip.after?.(target) || target).after(row);
  const at = target.getBoundingClientRect();
  const left = box.getBoundingClientRect().left;
  box.style.setProperty("--tip-x", `${Math.round(Math.max(14, Math.min(at.left + at.width / 2 - left, box.offsetWidth - 14)))}px`);
  shown = { id: tip.id, box: row };
}
