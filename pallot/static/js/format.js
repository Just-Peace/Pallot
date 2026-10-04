// Turning values into the words and figures the voter reads: dates, money, counts, sizes and lists.

export const SHORT_DATE = { month: "short", day: "numeric", year: "numeric" };
export const DOLLARS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const DOLLARS_SHORT = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
export const COUNT = new Intl.NumberFormat("en-US");
const LIST = new Intl.ListFormat("en-GB", { type: "conjunction" }); // "A, B and C", with no comma before "and"
const EITHER = new Intl.ListFormat("en-GB", { type: "disjunction" }); // "A, B or C"

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

export function percent(share) {
  if (share <= 0) return "0%";
  return share < 0.01 ? "<1%" : `${Math.round(share * 100)}%`;
}

// "1 race", "1,204 donations"
export const plural = (count, word) => `${COUNT.format(count)} ${word}${count === 1 ? "" : "s"}`;

// "U.S. House, State House and SBOE"
export const listed = (names) => LIST.format(names);

// "Democratic, Green or write-in"
export const either = (names) => EITHER.format(names);
