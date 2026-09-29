// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and a tab in Details) without any code change.

import { extLink, formatDate, h, linkedText, safeUrl } from "./dom.js";
import { icon } from "./icons.js";

// The FAQ answers that say how each source's figures are put together.
const MONEY_FAQ = { fec: "faq.html#fec-money", tec: "faq.html#tec-money", polls: "faq.html#polls" };
// What a race card's date means ("reports through" for the money sources).
const AS_OF_WORDS = { polls: "latest poll" };

// " · How these figures are put together" after a money card's source line (a new tab, so
// the ballot and any open dialog stay put); nothing for other sources.
export function howCounted(card) {
  const href = MONEY_FAQ[card.source];
  return href ? [" · ", extLink(href, "How these figures are put together")] : null;
}

// A badge with a url links to that source's page for the candidate (opens a new tab).
function badge(item, source) {
  const title = [item.hint, source ? `From ${source}` : null].filter(Boolean).join(" · ") || null;
  const href = safeUrl(item.url);
  return h("li", {}, href
    ? h("a", { class: `badge badge-link tone-${item.tone}`, href, target: "_blank", rel: "noopener noreferrer", title },
        item.text, h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗"))
    : h("span", { class: `badge tone-${item.tone}`, title }, item.text));
}

// Highlights from every source, shown under the candidate's name.
export function badgeList(candidate) {
  const items = candidate.cards.flatMap((card) => card.badges.map((b) => badge(b, card.label)));
  return items.length ? h("ul", { class: "badges", "aria-label": "Highlights from sources" }, items) : null;
}

function matchNote(card) {
  if (!card.match) return null;
  const exact = card.match.confidence === "exact";
  return h(
    "p",
    { class: `match ${exact ? "match-exact" : "match-likely"}` },
    h("strong", {}, exact ? "Matched" : "Likely match"),
    ` by ${card.match.method}.`,
    card.match.note ? ` ${card.match.note[0].toUpperCase()}${card.match.note.slice(1)}.` : "",
  );
}

export const SHORT_DATE = { month: "short", day: "numeric", year: "numeric" };
export const DOLLARS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const DOLLARS_SHORT = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
export const COUNT = new Intl.NumberFormat("en-US");

function asOf(card) {
  return card.as_of ? `Data as of ${formatDate(card.as_of, SHORT_DATE)}` : null;
}

export function percent(share) {
  if (share <= 0) return "0%";
  return share < 0.01 ? "<1%" : `${Math.round(share * 100)}%`;
}

// A word such as "for" or "against", as a small badge in the row's tone.
export function tagBadge(part) {
  return part.tag ? h("span", { class: `badge share-tag tone-${part.tone || "neutral"}` }, part.tag) : null;
}

// One row of a breakdown: the label (with its note), a bar, and the amount. partyOf maps a
// candidate key to their party, so a race comparison's bars take the party colours.
function shareRow(part, scale, showPercent, partyOf) {
  const width = scale > 0 && part.amount != null ? Math.min(100, Math.max(0, (part.amount / scale) * 100)) : 0;
  const count = part.count ? `${COUNT.format(part.count)} donation${part.count === 1 ? "" : "s"}` : null;
  const note = [part.note, count].filter(Boolean).join(" · ");
  const party = part.candidate_key && partyOf ? partyOf(part.candidate_key) : null;
  return h(
    "li",
    { class: `share${part.tone ? ` tone-${part.tone}` : ""}`, "data-party": party || null },
    h("span", { class: "share-label" }, part.label, tagBadge(part), note ? h("span", { class: "share-note" }, note) : null),
    h("span", { class: "bar", "aria-hidden": "true" }, h("span", { style: `width: ${width.toFixed(1)}%` })),
    h("span", { class: "share-amount" },
      part.amount == null ? "—" : DOLLARS.format(part.amount),
      showPercent && part.amount != null && scale > 0 ? h("span", { class: "share-pct" }, percent(part.amount / scale)) : null),
  );
}

const pct = (value) => `${Math.round(value)}%`;

// A "percent" Breakdown (a poll): one bar with a segment per part and the rest left grey,
// then a legend. Medians taken one candidate at a time can add up to a little over 100;
// then the segments share the whole bar.
function stackedBar(item, partyOf) {
  const shown = item.parts.filter((p) => p.amount != null && p.amount > 0);
  const sum = shown.reduce((total, p) => total + p.amount, 0);
  const whole = Math.max(100, sum);
  const rest = 100 - sum;
  const described = [...shown.map((p) => `${p.label} ${pct(p.amount)}`), rest >= 0.5 ? `undecided or other ${pct(rest)}` : null];
  const partyAttr = (part) => (part.candidate_key && partyOf ? partyOf(part.candidate_key) : null);
  return [
    h("div", { class: "stack-bar", role: "img", "aria-label": described.filter(Boolean).join(", ") },
      shown.map((part) => h("span", {
        "data-party": partyAttr(part), style: `width: ${((part.amount / whole) * 100).toFixed(1)}%`, title: `${part.label} ${pct(part.amount)}`,
      })),
      rest >= 0.5 ? h("span", { class: "rest", style: `width: ${rest.toFixed(1)}%`, title: `Undecided / other ${pct(rest)}` }) : null),
    h("ul", { class: "stack-legend" },
      item.parts.map((part) => h("li", { "data-party": partyAttr(part) },
        h("span", { class: "cmp-swatch", "aria-hidden": "true" }),
        h("span", {}, part.label),
        part.amount != null ? h("strong", {}, pct(part.amount)) : h("span", { class: "muted" }, part.note || "no figure"))),
      rest >= 0.5
        ? h("li", { class: "rest" }, h("span", { class: "cmp-swatch", "aria-hidden": "true" }), h("span", {}, "Undecided / other"),
            h("strong", {}, pct(rest)))
        : null),
  ];
}

// A Breakdown: labelled bars. With a total they're shares of it (and show a %); without
// one they're scaled to the largest part. ``action`` goes at the right of the title.
export function breakdownBlock(item, partyOf = null, action = null) {
  const largest = Math.max(0, ...item.parts.map((p) => p.amount || 0));
  const scale = item.total || largest;
  const title = h("h4", { class: "breakdown-title" }, item.title);
  return h(
    "section",
    { class: "breakdown" },
    action ? h("div", { class: "breakdown-head" }, title, action) : title,
    item.unit === "percent"
      ? stackedBar(item, partyOf)
      : h("ul", { class: "breakdown-rows" }, item.parts.map((part) => shareRow(part, scale, Boolean(item.total), partyOf))),
    item.note ? h("p", { class: "fine" }, item.note) : null,
  );
}

// The race cards whose source can put two or more of its candidates side by side.
export function comparable(race) {
  return (race.cards || []).filter((card) => card.comparison?.candidates.length > 1);
}

// A race's cards (money raised per money source, then polls), shown above its candidates.
// With ``onCompare``, the first comparable one has a button for the Compare dialog.
export function raceMoney(race, onCompare = null) {
  if (!race.cards?.length) return null;
  const partyOf = (key) => race.candidates.find((c) => c.key === key)?.party || null;
  const [first] = comparable(race);
  let button = null;
  if (onCompare && first) {
    button = h("button", { type: "button", class: "icon-btn compare-btn with-icon" }, icon("bars"), "Compare candidates");
    button.addEventListener("click", onCompare);
  }
  return race.cards.map((card) =>
    h("div", { class: "race-money" },
      card.breakdowns.map((b, j) => breakdownBlock(b, partyOf, card === first && j === 0 ? button : null)),
      h("p", { class: "fine" },
        `From ${card.label}`,
        card.as_of ? `, ${AS_OF_WORDS[card.source] || "reports through"} ${formatDate(card.as_of, SHORT_DATE)}` : "",
        card.url ? [" · ", extLink(card.url, `Open ${card.label}`)] : null,
        howCounted(card))));
}

export function cardPanel(card) {
  return h(
    "div",
    { class: "card-panel" },
    card.description ? h("p", { class: "muted" }, card.description) : null,
    matchNote(card),
    card.badges.length ? h("ul", { class: "badges" }, card.badges.map((b) => badge(b))) : null,
    card.facts.length
      ? h("dl", { class: "facts" }, card.facts.map((f) => [h("dt", {}, f.label), h("dd", {}, f.url ? extLink(f.url, f.value) : f.value)]))
      : null,
    card.quotes.length
      ? h("div", { class: "quotes" }, h("p", { class: "quotes-title" }, `In ${card.label}'s words`), card.quotes.map((q) => h("blockquote", {}, linkedText(q))))
      : null,
    (card.breakdowns || []).map((b) => breakdownBlock(b)),
    card.links.length ? h("ul", { class: "links" }, card.links.map((l) => h("li", {}, extLink(l.url, l.label)))) : null,
    h("p", { class: "fine" }, asOf(card), card.as_of && card.url ? " · " : null, card.url ? extLink(card.url, `Open ${card.label}`) : null,
      howCounted(card)),
  );
}

// WAI-ARIA tabs: one per card, arrow keys move between them. ``panelFor`` draws a card's panel.
export function renderTabs(container, cards, idPrefix, panelFor = cardPanel) {
  const tablist = h("div", { class: "tabs", role: "tablist", "aria-label": "Sources" });
  const tabs = [];
  const panels = [];
  cards.forEach((card, i) => {
    const tabId = `${idPrefix}-tab-${i}`;
    const panelId = `${idPrefix}-panel-${i}`;
    const tab = h(
      "button",
      { class: "tab", type: "button", role: "tab", id: tabId, "aria-controls": panelId, "aria-selected": String(i === 0), tabindex: i === 0 ? "0" : "-1" },
      card.label,
      card.match && card.match.confidence !== "exact" ? h("span", { class: "tab-flag", title: "Likely match" }, "?") : null,
    );
    const panel = h("div", { class: "tab-panel", role: "tabpanel", id: panelId, "aria-labelledby": tabId, tabindex: "0", hidden: i !== 0 }, panelFor(card));
    tabs.push(tab);
    panels.push(panel);
  });

  function select(index, focus = true) {
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      panels[i].hidden = i !== index;
    });
    if (focus) tabs[index].focus();
  }

  tablist.addEventListener("click", (event) => {
    const index = tabs.indexOf(event.target.closest('[role="tab"]'));
    if (index >= 0) select(index, false);
  });
  tablist.addEventListener("keydown", (event) => {
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    const next = { ArrowRight: current + 1, ArrowLeft: current - 1, Home: 0, End: tabs.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    select((next + tabs.length) % tabs.length);
  });

  tablist.append(...tabs);
  container.replaceChildren(tablist, ...panels);
}
