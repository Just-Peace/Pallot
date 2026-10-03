// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and a tab in Details) without any code change.

import { extLink, h, linkedText, safeUrl } from "./dom.js";
import { DOLLARS, SHORT_DATE, formatDate, percent, plural } from "./format.js";
import { icon } from "./icons.js";

// The FAQ answers that say how each source's figures are put together.
const MONEY_FAQ = { fec: "faq.html#fec-money", tec: "faq.html#tec-money", polls: "faq.html#polls" };
// What a card's date means.
const AS_OF_WORDS = { fec: "reports through", tec: "reports through", polls: "latest poll" };

// The line under a card: "From the FEC, reports through Mar 31, 2026 · Open the FEC · How these
// figures are put together". The FAQ link, for the money sources and polls, opens a new tab, so
// the ballot and any open dialog stay put.
export function sourceLine(card) {
  const faq = MONEY_FAQ[card.source];
  return h("p", { class: "fine" },
    `From ${card.label}`,
    card.as_of ? `, ${AS_OF_WORDS[card.source] || "data as of"} ${formatDate(card.as_of, SHORT_DATE)}` : "",
    card.url ? [" · ", extLink(card.url, `Open ${card.label}`)] : null,
    faq ? [" · ", extLink(faq, "How these figures are put together")] : null);
}

const width = (fraction) => `${(Math.min(1, Math.max(0, fraction || 0)) * 100).toFixed(1)}%`;

// A bar filled to ``fraction`` (0 to 1) of its length. Given { name: fraction }, it sets each as
// the CSS variable --w-name instead, for the stylesheet to pick one.
export function bar(fraction) {
  const style = typeof fraction === "number" ? `width: ${width(fraction)}`
    : Object.entries(fraction).map(([name, f]) => `--w-${name}: ${width(f)}`).join("; ");
  return h("span", { class: "bar", "aria-hidden": "true" }, h("span", { style }));
}

const isLikely = (card) => card.match?.confidence === "likely";

// The "?" on a tab, badge or button whose source only likely matched the candidate.
export function likelyFlag(title = "Likely match") {
  return h("span", { class: "likely-flag", title }, "?");
}

// A badge with a url links to that source's page for the candidate (opens a new tab). On
// the candidate row it carries its ``card``: the source's name, and for a likely match a
// note, plus a "?" on the ``first`` of that source's badges.
function badge(item, card = null, first = false) {
  const likely = card && isLikely(card);
  const title = [item.hint, card ? `From ${card.label}` : null, likely ? "Likely match: see Details" : null]
    .filter(Boolean).join(" · ") || null;
  const flag = likely && first ? likelyFlag("Likely match: see Details") : null;
  return h("li", {}, safeUrl(item.url)
    ? extLink(item.url, [item.text, flag, h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗")],
        { class: ["badge badge-link", `tone-${item.tone}`], title })
    : h("span", { class: ["badge", `tone-${item.tone}`], title }, item.text, flag));
}

// Highlights from every source, shown under the candidate's name.
export function badgeList(candidate) {
  const items = candidate.cards.flatMap((card) => card.badges.map((b, i) => badge(b, card, i === 0)));
  return items.length ? h("ul", { class: "badges", "aria-label": "Highlights from sources" }, items) : null;
}

// The sources that only likely matched the candidate and have no badge to flag it on.
export function likelyUnflagged(candidate) {
  return candidate.cards.filter((card) => isLikely(card) && !card.badges.length).map((card) => card.label);
}

function matchNote(card) {
  if (!card.match) return null;
  const exact = card.match.confidence === "exact";
  return h(
    "p",
    { class: ["match", exact ? "match-exact" : "match-likely"] },
    h("strong", {}, exact ? "Matched" : "Likely match"),
    ` by ${card.match.method}.`,
    card.match.note ? ` ${card.match.note[0].toUpperCase()}${card.match.note.slice(1)}.` : "",
  );
}

// A word such as "for" or "against", as a small badge in the row's tone.
export function tagBadge(part) {
  return part.tag ? h("span", { class: ["badge share-tag", `tone-${part.tone || "neutral"}`] }, part.tag) : null;
}

// One row of a breakdown: the label (with its note), a bar, and the amount. partyOf maps a
// candidate key to their party, so a race comparison's bars take the party colours.
function shareRow(part, scale, showPercent, partyOf) {
  const count = part.count ? plural(part.count, "donation") : null;
  const note = [part.note, count].filter(Boolean).join(" · ");
  const party = part.candidate_key && partyOf ? partyOf(part.candidate_key) : null;
  return h(
    "li",
    { class: ["share", part.tone && `tone-${part.tone}`], "data-party": party || null },
    h("span", { class: "share-label" }, part.label, tagBadge(part), note ? h("span", { class: "share-note" }, note) : null),
    bar(scale > 0 && part.amount != null ? part.amount / scale : 0),
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
        "data-party": partyAttr(part), style: `width: ${width(part.amount / whole)}`, title: `${part.label} ${pct(part.amount)}`,
      })),
      rest >= 0.5 ? h("span", { class: "rest", style: `width: ${width(rest / 100)}`, title: `Undecided / other ${pct(rest)}` }) : null),
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
function breakdownBlock(item, partyOf = null, action = null) {
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
    button = h("button", { type: "button", class: "icon-btn compare-btn with-icon", on: { click: onCompare } },
      icon("bars"), "Compare candidates");
  }
  return race.cards.map((card) =>
    h("div", { class: "race-money" },
      card.breakdowns.map((b, j) => breakdownBlock(b, partyOf, card === first && j === 0 ? button : null)),
      sourceLine(card)));
}

function cardPanel(card) {
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
    sourceLine(card),
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
      isLikely(card) ? likelyFlag() : null,
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
