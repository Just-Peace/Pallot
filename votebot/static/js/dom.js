// Small DOM helpers. Everything from the API is inserted as text, never as HTML.

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
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

export function extLink(url, label, props = {}) {
  const href = safeUrl(url);
  if (!href) return document.createTextNode(label);
  const external = !href.startsWith("mailto:");
  return h("a", { href, ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}), ...props }, label);
}

// Text that may contain markdown-style [label](url) links (TrackAIPAC notes do).
export function linkedText(text) {
  const parts = [];
  const pattern = /\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    parts.push(text.slice(last, match.index), extLink(match[2], match[1]));
    last = pattern.lastIndex;
  }
  parts.push(text.slice(last));
  return parts;
}

export function formatDate(iso, options = { month: "long", day: "numeric", year: "numeric" }) {
  if (!iso) return "";
  const date = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(undefined, options);
}

export function relativeTime(iso) {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  const steps = [[60, "second"], [60, "minute"], [24, "hour"], [30, "day"], [12, "month"], [Infinity, "year"]];
  let value = seconds;
  for (const [size, unit] of steps) {
    if (Math.abs(value) < size) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(-value, unit);
    }
    value = Math.round(value / size);
  }
  return iso;
}

export function formatBytes(bytes) {
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function initials(name) {
  const words = name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  return ((words[0]?.[0] || "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

export function slug(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}
