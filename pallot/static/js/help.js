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
let noteFor = null; // the button (or a tab's "?") it was last opened from
let closedAt = 0;

// Only a noteButton says whether its note is open; a tab's "?" is hidden from screen readers.
const expanded = (anchor, open) => {
  if (anchor?.hasAttribute("aria-expanded")) anchor.setAttribute("aria-expanded", String(open));
};

function noteBox() {
  if (note) return note;
  note = h("div", { id: "pop-note", popover: "auto", class: "pop-note" });
  note.addEventListener("toggle", (event) => {
    if (event.newState === "open") {
      document.addEventListener("scroll", hideNote, { capture: true, once: true, passive: true });
      return;
    }
    expanded(noteFor, false);
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

// The click that closed the note by landing on its own button doesn't open it again. ``button`` is
// what it opens beside: a noteButton, or a tab's "?" (renderTabs), tapped inside its tab.
export function toggleNote(button, content) {
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
  expanded(noteFor, false);
  noteFor = button;
  (button.closest("dialog[open]") || document.body).append(box);
  box.replaceChildren(h("div", { class: "pop-note-body", "aria-live": "polite" }, content()));
  box.showPopover();
  expanded(button, true);
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

// A card that content-visibility skips is off screen: reading its geometry would make the browser
// lay it out, every skipped card at each pass.
const skipped = (element) => element.checkVisibility?.({ contentVisibilityAuto: true }) === false;

// Wholly in the window, and not hidden.
function onScreen(element) {
  if (!element.getClientRects().length) return false;
  const box = element.getBoundingClientRect();
  return box.top >= 0 && box.bottom <= innerHeight;
}

// A card only stops being skipped at the frame after it nears the window, so a pass that skipped a
// target looks again two frames later, once, in case a jump brought it into view without more scrolling.
let recheck = 0;

// Shows the first of ``tips`` not seen yet whose ``when()`` holds and whose ``target()`` (an element
// or a list, the first on screen counting) is in the window, after ``after(target)`` (else the
// target), with an arrow at the target. No other shows until its "Got it", which runs ``next()`` to
// show the next one whose target is on screen. If the page drew it away before, only it may come
// back while it still could; once it can't (seen, its ``when()`` false, or its target gone or
// hidden), the others may show.
export function showTip(tips, next, again = true) {
  if (shown?.box.isConnected) return;
  const done = seen();
  if (shown) {
    const tip = tips.find((t) => t.id === shown.id);
    const drawn = (el) => el?.isConnected && el.getClientRects().length > 0;
    if (!tip || done.has(tip.id) || !tip.when() || ![tip.target()].flat().some(drawn)) shown = null;
  }
  let waiting = false;
  for (const tip of shown ? tips.filter((t) => t.id === shown.id) : tips) {
    if (done.has(tip.id) || !tip.when()) continue;
    for (const target of [tip.target()].flat()) {
      if (!target?.isConnected) continue;
      if (skipped(target)) {
        waiting = true;
      } else if (onScreen(target)) {
        drawTip(tip, target, next);
        return;
      }
    }
  }
  if (waiting && again && !recheck) {
    recheck = requestAnimationFrame(() => requestAnimationFrame(() => {
      recheck = 0;
      showTip(tips, next, false);
    }));
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
