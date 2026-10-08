// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and in Details) without any code change; its ``kind``
// decides where: endorsements (TrackAIPAC, Vote for Peace and the endorsement lists) make the
// row's Endorsements line and share Details' Endorsements tab, a money card's highlights and badges
// make the row's Funding line, the filing and profile cards share Details' Profile tab, every other
// card gets its own tab, and a money or poll box folds, with its source in its corner. The row's endorsement chips link to their
// source; its Funding chips open Details' money tab.

import { extLink, h, linkedText, safeUrl, slug } from "./dom.js";
import { DOLLARS, DOLLARS_SHORT, SHORT_DATE, formatDate, percent, plural } from "./format.js";
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

export const isLikely = (card) => card?.match?.confidence === "likely";

// An endorsement chip reads one way or the other: green for one (TrackAIPAC endorsed, Vote for
// Peace's Ally, a list), amber against (TrackAIPAC's watchlist, Vote for Peace's Opposed). A
// neutral one stays in Details.
const SIDED = new Set(["good", "warn"]);
const sided = (card) => card.kind === "endorsement" ? card.badges.filter((b) => SIDED.has(b.tone)) : [];
// Green chips before amber ones, each kept in its order.
const greenFirst = (items, tone = (item) => item.tone) => [...items].sort((a, b) => (tone(a) === "good" ? 0 : 1) - (tone(b) === "good" ? 0 : 1));
// A money card's chips, on the row and its tab: what it raised (its neutral badge) first, then its
// highlights, green before amber, then outside spending (its other badges), for before against.
const fundingChips = (card) => card.kind !== "money" ? [] : [
  ...card.badges.filter((b) => b.tone === "neutral"),
  ...greenFirst(card.highlights || []),
  ...card.badges.filter((b) => b.tone !== "neutral"),
];
// Each item's chip, with the "?" of a likely match on the first of its card's.
const chipsOf = (items, chip) => {
  const seen = new Set();
  return items.map(({ b, card }) => {
    const first = !seen.has(card);
    seen.add(card);
    return chip(b, card, first);
  });
};

// The view switch (view.js) that opens or folds a race box of each kind; other boxes always show.
const FOLDS = { money: "showFunding", polls: "showPolls" };

// The "?" on a tab, badge or button whose source only likely matched the candidate.
function likelyFlag(title = "Likely match") {
  return h("span", { class: "likely-flag", title }, "?");
}

// A badge with a url links to that source's page for the candidate (opens a new tab). On
// the candidate row it carries its ``card``: the source's name, and for a likely match a
// note, plus a "?" on the ``first`` of that source's badges. With ``onOpen(card)`` it's a button
// that opens Details at the source (a Funding chip). ``label`` shows instead of the badge's text,
// which then names it and is its tooltip.
function badge(item, card = null, first = false, label = item.text, onOpen = null) {
  const likely = card && isLikely(card);
  const short = label !== item.text;
  const title = [short ? item.text : null, item.hint, card && !short ? `From ${card.label}` : null,
    likely ? "Likely match" : null].filter(Boolean).join(" · ") || null;
  const flag = likely && first ? likelyFlag() : null;
  if (onOpen) {
    return h("li", {}, h("button", { type: "button", class: ["badge badge-btn", `tone-${item.tone}`], title,
      "aria-label": `${item.text}${flag ? " (likely match)" : ""}: open in Details`, on: { click: () => onOpen(card) } }, label, flag));
  }
  const name = short ? `${item.text}${flag ? " (likely match)" : ""}` : null;
  return h("li", {}, safeUrl(item.url)
    ? extLink(item.url, [label, flag, h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗")],
        { class: ["badge badge-link", `tone-${item.tone}`], title, "aria-label": name && `${name} (opens in a new tab)` })
    : h("span", { class: ["badge", `tone-${item.tone}`], title, "aria-label": name }, label, flag));
}

let lineIds = 0;

// The candidate's Endorsements line, a ul labelled by its heading. A green chip shows just the
// source's name, since the heading says "Endorsements"; an amber one says what it is ("TrackAIPAC
// watchlist"), so it doesn't rest on the colour. With the showEndorsements view switch off, one
// button counts them ("3 endorsements") and opens them in place, until syncLines(). A chip links
// to its source's page for the candidate.
export function sourceLines(candidate) {
  const items = greenFirst(candidate.cards.flatMap((card) => sided(card).map((b) => ({ b, card }))), (item) => item.b.tone);
  const chips = chipsOf(items, (b, card, first) => badge(b, card, first, b.tone === "good" ? card.label : b.text));
  if (!chips.length) return null;
  const id = `lines-${++lineIds}`;
  const body = h("div", { class: "cand-lines-body", id }, h("div", { class: "badge-line" },
    h("span", { class: "line-title", id: `${id}-title` }, "Endorsements"),
    h("ul", { class: "badges", "aria-labelledby": `${id}-title` }, chips)));
  const show = (open) => {
    body.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  };
  const toggle = h("button", {
    type: "button", class: "link-btn lines-toggle", "aria-controls": id,
    on: { click: () => show(body.hidden) },
  }, plural(chips.length, "endorsement"));
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

// The candidate's Funding line, after their other lines: each money card's chips (fundingChips),
// as its tab in Details shows them, with a "?" on the first of a card that only likely matched. The showFunding
// view switch hides it, with the money boxes, until syncFunding(). A chip opens Details at its money source,
// ``onOpen(card)``.
export function fundingLine(candidate, onOpen) {
  const cards = candidate.cards.filter((card) => fundingChips(card).length);
  if (!cards.length) return null;
  const id = `funding-${++lineIds}`;
  const element = h("div", { class: "cand-lines funding-line", on: { "pallot:sync": () => {
    element.hidden = !viewPref("showFunding");
  } } }, h("div", { class: "badge-line" },
    h("span", { class: "line-title", id }, "Funding"),
    h("ul", { class: "badges", "aria-labelledby": id },
      chipsOf(cards.flatMap((card) => fundingChips(card).map((b) => ({ b, card }))), (b, card, first) => badge(b, card, first, b.text, onOpen)))));
  element.hidden = !viewPref("showFunding");
  return element;
}

// Every candidate's Funding line goes back to the showFunding switch.
export function syncFunding() {
  for (const element of document.querySelectorAll(".funding-line")) element.dispatchEvent(new Event("pallot:sync"));
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
    h("span", { class: "share-label" }, part.label, likely ? likelyFlag("Likely match: see Issues") : null, tagBadge(part),
      note ? h("span", { class: "share-note" }, note) : null),
    bar(scale > 0 && part.amount != null ? part.amount / scale : 0),
    h("span", { class: "share-amount" },
      part.amount == null ? "—" : DOLLARS.format(part.amount),
      showPercent && part.amount != null && scale > 0 ? h("span", { class: "share-pct" }, percent(part.amount / scale)) : null),
  );
}

const pct = (value) => `${Math.round(value)}%`;

// A "percent" Breakdown (a poll): one bar with a segment per part and the rest left grey, then
// a legend of the parts. Medians taken one candidate at a time can add up to a little over 100;
// then the segments share the whole bar.
function stackedBar(item, people) {
  const shown = item.parts.filter((p) => p.amount != null && p.amount > 0);
  const sum = shown.reduce((total, p) => total + p.amount, 0);
  const whole = Math.max(100, sum);
  const rest = 100 - sum;
  const described = [...shown.map((p) => `${p.label} ${pct(p.amount)}`), rest >= 0.5 ? `undecided or other ${pct(rest)}` : null];
  const partyAttr = (part) => (part.candidate_key && people ? people.party(part.candidate_key) : null);
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
  ];
}

// A money box's head, like a poll's: one bar for the total the race's candidates raised, a
// segment per candidate in their party's colour, then a legend with what each raised and the total.
function moneyStack(item, people) {
  const shown = item.parts.filter((p) => p.amount != null && p.amount > 0);
  const sum = shown.reduce((total, p) => total + p.amount, 0);
  const partyAttr = (part) => (part.candidate_key && people ? people.party(part.candidate_key) : null);
  const likely = (part) => (part.candidate_key && people?.likely(part.candidate_key) ? likelyFlag("Likely match: see Issues") : null);
  return [
    sum > 0
      ? h("div", { class: "stack-bar", role: "img", "aria-label": shown.map((p) => `${p.label} ${DOLLARS.format(p.amount)}`).join(", ") },
          shown.map((part) => h("span", {
            "data-party": partyAttr(part), style: `width: ${width(part.amount / sum)}`,
            title: `${part.label} ${DOLLARS.format(part.amount)}`,
          })))
      : null,
    h("ul", { class: "stack-legend" }, item.parts.map((part) => h("li", {
      "data-party": partyAttr(part), class: part.amount == null ? "rest" : null,
    },
      h("span", { class: "cmp-swatch", "aria-hidden": "true" }),
      h("span", {}, part.label, likely(part)),
      h("strong", {}, part.amount == null ? "—" : DOLLARS_SHORT.format(part.amount)))),
      sum > 0 ? h("li", { class: "stack-total" }, h("span", {}, "Total"), h("strong", {}, DOLLARS_SHORT.format(sum))) : null),
  ];
}

// A Breakdown's bars and note (``withNote``). With a total they're shares of it (and show a %);
// without one they're scaled to the largest part.
function breakdownRows(item, people = null, withNote = true) {
  const largest = Math.max(0, ...item.parts.map((p) => p.amount || 0));
  const scale = item.total || largest;
  return [
    item.unit === "percent"
      ? stackedBar(item, people)
      : h("ul", { class: "breakdown-rows" }, item.parts.map((part) => shareRow(part, scale, Boolean(item.total), people))),
    withNote && item.note ? h("p", { class: "fine" }, item.note) : null,
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

// A race box that folds: its first breakdown's title and its date ("latest poll Oct 5", "reports
// through Sep 30"), the source being in its corner, as a button that folds it to that one line,
// with ``action`` (the box's corner) beside it; folded, it names nobody. It opens as the view
// switch ``setting`` says; a click opens or folds just this one, until syncBoxes().
function foldBox(race, card, setting, action, body) {
  const id = `box-${slug(race.key)}-${card.source}`;
  const title = card.breakdowns[0]?.title || card.description;
  const text = [title, card.as_of ? `${AS_OF_WORDS[card.source] || "data as of"} ${formatDate(card.as_of, SHORT_DATE)}` : null]
    .filter(Boolean).join(" · ");
  const toggle = h("button", {
    type: "button", class: "box-toggle", "aria-controls": id,
    on: { click: () => setBoxOpen(box, box.classList.contains("collapsed")) },
  }, h("span", { class: "chevron", "aria-hidden": "true" }), text);
  const box = h("div", { class: "race-money", "data-fold": setting },
    h("div", { class: "breakdown-head" }, h("h4", { class: "breakdown-title" }, toggle), action),
    h("div", { class: "box-body", id }, body));
  setBoxOpen(box, viewPref(setting));
  return box;
}

// A poll box's corner, like a candidate's Note and Search: how many polls (its tooltip says how
// the bar is worked out, and it opens the FAQ's answer) and the source.
function pollCorner(card, head) {
  return h("span", { class: "box-links" },
    head?.count ? extLink(MONEY_FAQ.polls, plural(head.count, "poll"), { class: "icon-btn", title: head.note }) : null,
    card.url ? extLink(card.url, `${card.label} ↗`, { class: "icon-btn", title: `Open ${card.label}` }) : null);
}

// A money box's corner, like a poll box's: Compare funding (``compare``) and the source.
function moneyCorner(card, compare) {
  return h("span", { class: "box-links" },
    compare,
    card.url ? extLink(card.url, `${card.label} ↗`, { class: "icon-btn", title: `Open ${card.label}` }) : null);
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
      icon("bars"), "Compare funding");
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
    const polls = card.kind === "polls";
    return foldBox(race, card, setting, polls ? pollCorner(card, head) : moneyCorner(card, action), [
      head ? h("section", { class: "breakdown" }, polls ? breakdownRows(head, people, false) : moneyStack(head, people)) : null,
      rest.map((b) => breakdownBlock(b, people)),
    ]);
  });
}

// A card's badges and facts, as cardPanel() and moneyPanel() show them: a money card's chips on one
// Funding line, in the row's order (fundingChips).
const cardSummary = (card) => [
  fundingChips(card).length
    ? h("div", { class: "badge-line panel-funding" }, h("span", { class: "line-title" }, "Funding"),
        h("ul", { class: "badges", "aria-label": "Funding" }, fundingChips(card).map((b) => badge(b))))
    : card.badges.length ? h("ul", { class: "badges" }, card.badges.map((b) => badge(b))) : null,
  card.facts.length
    ? h("dl", { class: "facts" }, card.facts.map((f) => [h("dt", {}, f.label), h("dd", {}, f.url ? extLink(f.url, f.value) : f.value)]))
    : null,
];
const cardQuotes = (card) => card.quotes.length
  ? h("div", { class: "quotes" }, h("p", { class: "quotes-title" }, `In ${card.label}'s words`), card.quotes.map((q) => h("blockquote", {}, linkedText(q))))
  : null;
const cardLinks = (card) => card.links.length
  ? h("ul", { class: "links" }, card.links.map((l) => h("li", {}, extLink(l.url, l.label))))
  : null;

export function cardPanel(card) {
  return h(
    "div",
    { class: "card-panel" },
    card.description ? h("p", { class: "muted" }, card.description) : null,
    matchNote(card),
    cardSummary(card),
    cardQuotes(card),
    (card.breakdowns || []).map((b) => breakdownBlock(b)),
    cardLinks(card),
    sourceLine(card),
  );
}

// A box on a Details tab that folds to its summary (its name, then ``extra``, such as a "?" or
// chips) when the voter clicks it, open at first: the Profile, Issues, Endorsements and money tabs
// are made of them.
export function foldSection(name, extra, body) {
  return h("details", { class: "source-section", open: true },
    h("summary", {}, h("span", { class: "source-section-name" }, name), extra),
    h("div", { class: "section-body" }, body));
}

// Details' Profile tab: the candidate's filing with the state (Texas SOS), then Ballotpedia's
// profile, a section each with its whole card.
export function profilePanel(cards) {
  return h("div", { class: "card-panel profile" },
    cards.map((card) => foldSection(card.label, isLikely(card) ? likelyFlag() : null, cardPanel(card))));
}

// A money source's tab (FEC, TEC): its description and match, then its totals and each breakdown
// in a section of its own, then its links and where it comes from.
export function moneyPanel(card) {
  const summary = cardSummary(card).filter(Boolean);
  return h("div", { class: "card-panel money" },
    card.description ? h("p", { class: "muted" }, card.description) : null,
    matchNote(card),
    summary.length ? foldSection("Totals", null, summary) : null,
    cardQuotes(card),
    (card.breakdowns || []).map((b) => foldSection(b.title, null, breakdownRows(b))),
    cardLinks(card),
    sourceLine(card));
}

// A chip's words beside its source's name: "Endorsed by CAIR Action" is "Endorsed", "TrackAIPAC
// watchlist" "Watchlist", "Vote for Peace: Ally" "Ally".
function chipWords(item, card) {
  const words = item.text.replace(card.label, "").replace(/^[\s:]+|\s+by\s*$/g, "").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : item.text;
}

// Details' Endorsements tab: a section per source with its whole card, all open, green ones (for
// the candidate) first, then amber (against), then the rest. Folded, a section is its name, its
// "?" and its chips.
const SIDE_ORDER = { good: 0, warn: 1 };
const side = (card) => Math.min(2, ...card.badges.map((b) => SIDE_ORDER[b.tone] ?? 2));

export function endorsementsPanel(cards) {
  const sorted = [...cards].sort((a, b) => side(a) - side(b));
  const section = (card) => foldSection(card.label, [
    isLikely(card) ? likelyFlag() : null,
    card.badges.map((b) => h("span", { class: ["badge", `tone-${b.tone}`], title: b.text }, chipWords(b, card))),
  ], cardPanel(card));
  return h("div", { class: "card-panel endorsements" },
    h("p", { class: "muted" }, plural(cards.length, "endorsement")),
    sorted.map(section));
}

// WAI-ARIA tabs: one per card, arrow keys move between them. ``panelFor`` draws a card's panel.
// A tab's "?" is its card's ``likely``, or its match. ``initial`` is the tab shown first, and
// ``onSelect(index)`` hears each one picked after.
export function renderTabs(container, cards, idPrefix, panelFor = cardPanel, { initial = 0, onSelect = null } = {}) {
  const tablist = h("div", { class: "tabs", role: "tablist", "aria-label": "Sources" });
  const tabs = [];
  const panels = [];
  cards.forEach((card, i) => {
    const tabId = `${idPrefix}-tab-${i}`;
    const panelId = `${idPrefix}-panel-${i}`;
    const tab = h(
      "button",
      { class: "tab", type: "button", role: "tab", id: tabId, "aria-controls": panelId, "aria-selected": String(i === initial), tabindex: i === initial ? "0" : "-1" },
      card.label,
      (card.likely ?? isLikely(card)) ? likelyFlag() : null,
    );
    const panel = h("div", { class: "tab-panel", role: "tabpanel", id: panelId, "aria-labelledby": tabId, tabindex: "0", hidden: i !== initial }, panelFor(card));
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
    onSelect?.(index);
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
