// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and a tab in Details) without any code change.

import { extLink, formatDate, h, linkedText } from "./dom.js";

function badge(item, source) {
  return h("li", { class: `badge tone-${item.tone}`, title: source ? `From ${source}` : null }, item.text);
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

function asOf(card) {
  if (!card.as_of) return null;
  const options = { month: "short", day: "numeric", year: "numeric" };
  return `Data as of ${formatDate(card.as_of, card.as_of.length > 10 ? { ...options, hour: "numeric", minute: "2-digit" } : options)}`;
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
    card.links.length ? h("ul", { class: "links" }, card.links.map((l) => h("li", {}, extLink(l.url, l.label)))) : null,
    h("p", { class: "fine" }, asOf(card), card.as_of && card.url ? " · " : null, card.url ? extLink(card.url, `Open ${card.label}`) : null),
  );
}

// WAI-ARIA tabs: one per card, arrow keys move between them.
export function renderTabs(container, cards, idPrefix) {
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
    const panel = h("div", { class: "tab-panel", role: "tabpanel", id: panelId, "aria-labelledby": tabId, tabindex: "0", hidden: i !== 0 }, cardPanel(card));
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
