// A swipe sideways with a finger or a pen: to the left for the next, to the right for the previous
// (Details' candidates). A mostly vertical move is a scroll, and a slow or short one a tap or a drag.

const SWIPE = { distance: 60, ratio: 2, ms: 700 };

// 1 (the next), -1 (the previous) or 0 for a move of ``dx`` and ``dy`` pixels over ``ms``.
export function swipeStep(dx, dy, ms) {
  if (ms > SWIPE.ms || Math.abs(dx) < SWIPE.distance || Math.abs(dx) < SWIPE.ratio * Math.abs(dy)) return 0;
  return dx < 0 ? 1 : -1;
}

// Something between ``node`` and ``within`` that scrolls sideways (the tab row): a swipe there is its own.
function scrollsSideways(node, within) {
  for (let el = node; el && el !== within; el = el.parentElement) {
    if (el.scrollWidth > el.clientWidth + 1 && /auto|scroll/.test(getComputedStyle(el).overflowX)) return true;
  }
  return false;
}

// Calls ``step(1 | -1)`` on a swipe across ``element``. The element's CSS leaves sideways moves to
// the page (touch-action: pan-y), or the browser would take the pointer over and cancel it.
export function onSwipe(element, step) {
  let start = null;
  element.addEventListener("pointerdown", (event) => {
    start = null;
    if (event.pointerType === "mouse" || !event.isPrimary) return;
    if (event.target.closest("input, textarea, select, [contenteditable]") || scrollsSideways(event.target, element)) return;
    start = { x: event.clientX, y: event.clientY, at: event.timeStamp, id: event.pointerId };
  });
  element.addEventListener("pointerup", (event) => {
    if (event.pointerId !== start?.id) return;
    const way = swipeStep(event.clientX - start.x, event.clientY - start.y, event.timeStamp - start.at);
    start = null;
    if (way) step(way);
  });
  element.addEventListener("pointercancel", () => {
    start = null;
  });
}
