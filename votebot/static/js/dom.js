// Small DOM helpers. Everything from the API is inserted as text, never as HTML.

export const $ = (selector) => document.querySelector(selector);

// ``class`` is a string or an array, whose falsy entries are dropped; ``on`` is { event: listener }.
function build(el, props, children) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "on") {
      for (const [type, listener] of Object.entries(value)) el.addEventListener(type, listener);
    } else if (key === "class") {
      const names = [value].flat().filter(Boolean).join(" ");
      if (names) el.setAttribute("class", names);
    } else {
      el.setAttribute(key, value === true ? "" : value);
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function h(tag, props = {}, ...children) {
  return build(document.createElement(tag), props, children);
}

export function svg(tag, props = {}, ...children) {
  return build(document.createElementNS("http://www.w3.org/2000/svg", tag), props, children);
}

// Only http(s) and mailto links are ever rendered.
export function safeUrl(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url, location.href);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

// A link that opens in a new tab (mailto: aside). ``label`` is text, a node or a list of them;
// without a usable url it's shown unlinked.
export function extLink(url, label, props = {}) {
  const href = safeUrl(url);
  if (!href) return h("span", {}, label);
  const external = !href.startsWith("mailto:");
  return h("a", { href, ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}), ...props }, label);
}

// Text that may contain markdown-style [label](url) links (TrackAIPAC notes do). Only full
// URLs become links: a bare path would resolve against VoteBot itself.
export function linkedText(text) {
  const parts = [];
  const pattern = /\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    const [, label, url] = match;
    parts.push(text.slice(last, match.index), /^(https?:\/\/|mailto:)/i.test(url) ? extLink(url, label) : label);
    last = pattern.lastIndex;
  }
  parts.push(text.slice(last));
  return parts;
}

export function initials(name) {
  const words = name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  return ((words[0]?.[0] || "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

export function slug(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// A status line: ``kind`` is busy, ok, error or info.
export function setStatus(box, message, kind = "info") {
  box.className = `status status-${kind}`;
  box.textContent = message || "";
}

// ``run``, at most once a frame however often the returned function is called (scrolling).
export function onFrame(run) {
  let pending = false;
  return () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      run();
    });
  };
}

// Keeps ``element``'s height in the page's CSS variable ``name``, and passes it to ``then``.
export function trackHeight(element, name, then = null) {
  new ResizeObserver(() => {
    const height = element.getBoundingClientRect().height;
    document.documentElement.style.setProperty(name, `${height}px`);
    then?.(height);
  }).observe(element);
}

// Runs ``run`` when the voter comes back to the page: from another tab, or with Back, which can
// show the page as it was left.
export function onReturn(run) {
  addEventListener("pageshow", (event) => {
    if (event.persisted) run();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) run();
  });
}

// Saves a box ``wait`` ms after the last keystroke, and at once on leaving it (e.g. for another page).
export function autosave(field, save, wait) {
  let timer = null;
  const now = () => {
    clearTimeout(timer);
    save();
  };
  field.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(now, wait);
  });
  field.addEventListener("change", now);
}

// A dialog's heading row: ``content``, then ``buttons`` and ✕, which closes it. ``close`` is
// the ✕, to focus.
export function dialogHead(dialog, content, ...buttons) {
  const close = h("button", { type: "button", class: "icon-btn close", "aria-label": "Close", on: { click: () => dialog.close() } }, "✕");
  return { head: h("div", { class: "details-head" }, content, h("div", { class: "details-nav" }, buttons, close)), close };
}

// A click on the backdrop, outside the dialog's box, closes it, with no returnValue.
export function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    const inside = event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
    if (!inside) dialog.close("");
  });
}
