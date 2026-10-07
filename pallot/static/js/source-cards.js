// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and a tab in Details) without any code change; its
// ``kind`` decides where: endorsements and scorecards each get a line on the row, a profile a
// link beside Web search, a money card's badges stay in Details, and a money or poll box folds.

import { extLink, h, linkedText, safeUrl, slug } from "./dom.js";
import { DOLLARS, SHORT_DATE, formatDate, percent, plural } from "./format.js";
import { icon } from "./icons.js";
import { viewPref } from "./view.js";

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

const isLikely = (card) => card?.match?.confidence === "likely";

// The candidate row's lines, one per kind, each under its heading. An endorsement's chip shows
// just the list's name, since the heading says "Endorsed by".
const LINES = [
  { kind: "endorsement", title: "Endorsed by", noun: "endorsement", short: true },
  { kind: "scorecard", title: "Scorecards", noun: "scorecard" },
];
const onLine = (card) => LINES.some((line) => line.kind === card.kind) && card.badges.length > 0;
// A profile's page (Ballotpedia's), a link in the row's actions.
const profileUrl = (card) => (card.kind === "profile" ? safeUrl(card.badges[0]?.url) : null);

// The view switch (view.js) that opens or folds a race box of each kind; other boxes always show.
const FOLDS = { money: "showMoney", polls: "showPolls" };

// The "?" on a tab, badge or button whose source only likely matched the candidate.
export function likelyFlag(title = "Likely match") {
  return h("span", { class: "likely-flag", title }, "?");
}

// A badge with a url links to that source's page for the candidate (opens a new tab). On
// the candidate row it carries its ``card``: the source's name, and for a likely match a
// note, plus a "?" on the ``first`` of that source's badges. ``label`` shows instead of the
// badge's text, which then names it and is its tooltip.
function badge(item, card = null, first = false, label = item.text) {
  const likely = card && isLikely(card);
  const short = label !== item.text;
  const title = [short ? item.text : null, item.hint, card && !short ? `From ${card.label}` : null,
    likely ? "Likely match: see Details" : null].filter(Boolean).join(" · ") || null;
  const flag = likely && first ? likelyFlag("Likely match: see Details") : null;
  const name = short ? `${item.text}${flag ? " (likely match)" : ""}` : null;
  return h("li", {}, safeUrl(item.url)
    ? extLink(item.url, [label, flag, h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗")],
        { class: ["badge badge-link", `tone-${item.tone}`], title, "aria-label": name && `${name} (opens in a new tab)` })
    : h("span", { class: ["badge", `tone-${item.tone}`], title, "aria-label": name }, label, flag));
}

let lineIds = 0;

// The candidate's endorsements and scorecards: a line for each kind that has any, a ul labelled
// by its heading. With the showEndorsements view switch off, one button counts them ("3
// endorsements · 1 scorecard") and opens them in place, until syncLines(). ``onShow(shown)``
// hears whether they show, so the Details button can carry their "?" while they're hidden.
export function sourceLines(candidate, onShow) {
  const lines = LINES.map((line) => ({ ...line, cards: candidate.cards.filter((card) => card.kind === line.kind && onLine(card)) }))
    .filter((line) => line.cards.length);
  if (!lines.length) return null;
  const id = `lines-${++lineIds}`;
  const body = h("div", { class: "cand-lines-body", id }, lines.map((line, n) => h("div", { class: "badge-line" },
    h("span", { class: "line-title", id: `${id}-${n}` }, line.title),
    h("ul", { class: "badges", "aria-labelledby": `${id}-${n}` },
      line.cards.flatMap((card) => card.badges.map((b, j) => badge(b, card, j === 0, line.short ? card.label : b.text)))))));
  const show = (open) => {
    body.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    onShow(open);
  };
  const toggle = h("button", {
    type: "button", class: "link-btn lines-toggle", "aria-controls": id,
    on: { click: () => show(body.hidden) },
  }, lines.map((line) => plural(line.cards.length, line.noun)).join(" · "));
  const sync = () => {
    toggle.hidden = viewPref("showEndorsements");
    show(viewPref("showEndorsements"));
  };
  const element = h("div", { class: "cand-lines", on: { "pallot:sync": sync } }, toggle, body);
  sync();
  return element;
}

// Every candidate's lines go back to the showEndorsements switch, opened by hand or not.
export function syncLines() {
  for (const element of document.querySelectorAll(".cand-lines")) element.dispatchEvent(new Event("pallot:sync"));
}

// A profile card (Ballotpedia's) is a link in the row's actions, with its "?" for a likely match.
export function profileLinks(candidate) {
  return candidate.cards.filter(profileUrl).map((card) => extLink(profileUrl(card),
    [card.label, isLikely(card) ? likelyFlag("Likely match: see Details") : null, " ↗"],
    { class: "icon-btn", title: card.badges[0].text }));
}

// The sources that only likely matched the candidate and have nothing on the row to flag it on
// (``hidden``: counting their lines, while those are folded away).
export function likelyUnflagged(candidate, hidden = false) {
  return candidate.cards.filter((card) => isLikely(card) && !profileUrl(card) && (hidden || !onLine(card)))
    .map((card) => card.label);
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

// One row of a breakdown: the label (with its note), a bar, and the amount. In a race's box,
// ``people`` knows each candidate (by key): their party, so the bars take the party colours,
// and whether the box's source only likely matched them, which puts a "?" after the name.
function shareRow(part, scale, showPercent, people) {
  const count = part.count ? plural(part.count, "donation") : null;
  const note = [part.note, count].filter(Boolean).join(" · ");
  const party = part.candidate_key && people ? people.party(part.candidate_key) : null;
  const likely = part.candidate_key && people?.likely(part.candidate_key);
  return h(
    "li",
    { class: ["share", part.tone && `tone-${part.tone}`], "data-party": party || null },
    h("span", { class: "share-label" }, part.label, likely ? likelyFlag("Likely match: see Details") : null, tagBadge(part),
      note ? h("span", { class: "share-note" }, note) : null),
    bar(scale > 0 && part.amount != null ? part.amount / scale : 0),
    h("span", { class: "share-amount" },
      part.amount == null ? "—" : DOLLARS.format(part.amount),
      showPercent && part.amount != null && scale > 0 ? h("span", { class: "share-pct" }, percent(part.amount / scale)) : null),
  );
}

const pct = (value) => `${Math.round(value)}%`;

// A "percent" Breakdown (a poll): one bar with a segment per part and the rest left grey,
// then a legend of the parts with a figure, and one muted line naming the rest. Medians taken
// one candidate at a time can add up to a little over 100; then the segments share the whole bar.
function stackedBar(item, people) {
  const shown = item.parts.filter((p) => p.amount != null && p.amount > 0);
  const sum = shown.reduce((total, p) => total + p.amount, 0);
  const whole = Math.max(100, sum);
  const rest = 100 - sum;
  const described = [...shown.map((p) => `${p.label} ${pct(p.amount)}`), rest >= 0.5 ? `undecided or other ${pct(rest)}` : null];
  const partyAttr = (part) => (part.candidate_key && people ? people.party(part.candidate_key) : null);
  const missing = item.parts.filter((p) => p.amount == null).map((p) => p.label);
  return [
    h("div", { class: "stack-bar", role: "img", "aria-label": described.filter(Boolean).join(", ") },
      shown.map((part) => h("span", {
        "data-party": partyAttr(part), style: `width: ${width(part.amount / whole)}`, title: `${part.label} ${pct(part.amount)}`,
      })),
      rest >= 0.5 ? h("span", { class: "rest", style: `width: ${width(rest / 100)}`, title: `Undecided / other ${pct(rest)}` }) : null),
    h("ul", { class: "stack-legend" },
      item.parts.filter((part) => part.amount != null).map((part) => h("li", { "data-party": partyAttr(part) },
        h("span", { class: "cmp-swatch", "aria-hidden": "true" }),
        h("span", {}, part.label),
        h("strong", {}, pct(part.amount)))),
      rest >= 0.5
        ? h("li", { class: "rest" }, h("span", { class: "cmp-swatch", "aria-hidden": "true" }), h("span", {}, "Undecided / other"),
            h("strong", {}, pct(rest)))
        : null),
    missing.length ? h("p", { class: "fine muted stack-missing" }, `Not in these polls: ${missing.join(", ")}`) : null,
  ];
}

// A Breakdown's bars and note. With a total they're shares of it (and show a %); without
// one they're scaled to the largest part.
function breakdownRows(item, people = null) {
  const largest = Math.max(0, ...item.parts.map((p) => p.amount || 0));
  const scale = item.total || largest;
  return [
    item.unit === "percent"
      ? stackedBar(item, people)
      : h("ul", { class: "breakdown-rows" }, item.parts.map((part) => shareRow(part, scale, Boolean(item.total), people))),
    item.note ? h("p", { class: "fine" }, item.note) : null,
  ];
}

// A Breakdown under its title. ``action`` goes at the right of the title.
function breakdownBlock(item, people = null, action = null) {
  const title = h("h4", { class: "breakdown-title" }, item.title);
  return h("section", { class: "breakdown" },
    action ? h("div", { class: "breakdown-head" }, title, action) : title,
    breakdownRows(item, people));
}

// The race cards whose source can put two or more of its candidates side by side.
export function comparable(race) {
  return (race.cards || []).filter((card) => card.comparison?.candidates.length > 1);
}

function setBoxOpen(box, open) {
  box.classList.toggle("collapsed", !open);
  box.querySelector(".box-toggle").setAttribute("aria-expanded", String(open));
  box.querySelector(".box-body").hidden = !open;
}

// A race box that folds: its first breakdown's title and the source (with a poll's date), as a
// button that folds it to that one line, with ``action`` (Compare) beside it; folded, it names
// nobody. It opens as the view switch ``setting`` says; a click opens or folds just this one,
// until syncBoxes().
function foldBox(race, card, setting, action, body) {
  const id = `box-${slug(race.key)}-${card.source}`;
  const dated = card.kind === "polls" && card.as_of ? `, ${AS_OF_WORDS.polls} ${formatDate(card.as_of, SHORT_DATE)}` : "";
  const toggle = h("button", {
    type: "button", class: "box-toggle", "aria-controls": id,
    on: { click: () => setBoxOpen(box, box.classList.contains("collapsed")) },
  }, h("span", { class: "chevron", "aria-hidden": "true" }), `${card.breakdowns[0]?.title || card.description} · ${card.label}${dated}`);
  const box = h("div", { class: "race-money", "data-fold": setting },
    h("div", { class: "breakdown-head" }, h("h4", { class: "breakdown-title" }, toggle), action),
    h("div", { class: "box-body", id }, body));
  setBoxOpen(box, viewPref(setting));
  return box;
}

// Every race box that ``setting`` folds goes back to it, whether it was opened or folded by hand.
export function syncBoxes(setting) {
  for (const box of document.querySelectorAll(`.race-money[data-fold="${setting}"]`)) setBoxOpen(box, viewPref(setting));
}

// A race's cards (money raised per money source, then polls), shown above its candidates.
// With ``onCompare``, the first comparable one has a button for the Compare dialog.
export function raceMoney(race, onCompare = null) {
  if (!race.cards?.length) return null;
  const candidate = (key) => race.candidates.find((c) => c.key === key);
  const [first] = comparable(race);
  let button = null;
  if (onCompare && first) {
    button = h("button", { type: "button", class: "icon-btn compare-btn with-icon", on: { click: onCompare } },
      icon("bars"), "Compare candidates");
  }
  return race.cards.map((card) => {
    const people = {
      party: (key) => candidate(key)?.party || null,
      likely: (key) => isLikely(candidate(key)?.cards.find((c) => c.source === card.source)),
    };
    const action = card === first ? button : null;
    const setting = FOLDS[card.kind];
    if (!setting) {
      return h("div", { class: "race-money" },
        card.breakdowns.map((b, j) => breakdownBlock(b, people, j === 0 ? action : null)),
        sourceLine(card));
    }
    const [head, ...rest] = card.breakdowns;
    return foldBox(race, card, setting, action,
      [head ? h("section", { class: "breakdown" }, breakdownRows(head, people)) : null, rest.map((b) => breakdownBlock(b, people)), sourceLine(card)]);
  });
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
    tabs[index].scrollIntoView({ block: "nearest", inline: "nearest" }); // the row scrolls sideways on a phone
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
