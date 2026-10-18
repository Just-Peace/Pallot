// Renders SourceCards. Every source's card has the same shape, so a new source shows up
// here (as badges on the candidate row and in Details) without any code change; its ``kind``
// decides where: endorsements (TrackAIPAC, Vote for Peace and the endorsement lists) make the
// row's Endorsements line and share Details' Endorsements tab, a money card's highlights and badges
// make the row's Funding line, the filing and profile cards share Details' Profile tab, every other
// card gets its own tab, and a money or poll box folds, with its source in its corner. The row's endorsement chips link to their
// source, or open a menu that also offers Help me pick; its Funding chips open Details' money tab.

import { extLink, h, linkedText, phoneWords, safeUrl, slug } from "./dom.js";
import { DOLLARS, DOLLARS_SHORT, SHORT_DATE, formatDate, percent, plural } from "./format.js";
import { fundingHelp, helpLink, toggleNote } from "./help.js";
import { icon } from "./icons.js";
import { chooseInHelp } from "./endorser-bar.js";
import { barChoice } from "./pick-rules.js";
import { viewPref } from "./view.js";

// The FAQ answers that say how each source's figures are put together.
const MONEY_FAQ = { fec: "fec-money", tec: "tec-money", polls: "polls" };
// What a card's date means.
const AS_OF_WORDS = { fec: "reports through", tec: "reports through", polls: "latest poll" };

// A link to another website, with the badges' ↗ after its label (none for an email address).
function webLink(url, label) {
  return extLink(url, url.startsWith("mailto:") ? label : [label, " ", h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗")]);
}

// The line under a Compare panel and a race box that doesn't fold: "From the FEC, reports through
// Mar 31, 2026 · Open the FEC · How these figures are put together". The FAQ link, for the money
// sources and polls, opens a new tab, so the ballot and any open dialog stay put.
export function sourceLine(card) {
  const faq = MONEY_FAQ[card.source];
  return h("p", { class: "fine" },
    `From ${card.label}`,
    card.as_of ? `, ${AS_OF_WORDS[card.source] || "data as of"} ${formatDate(card.as_of, SHORT_DATE)}` : "",
    card.url ? [" · ", webLink(card.url, `Open ${card.label}`)] : null,
    faq ? [" · ", extLink(`faq.html#${faq}`, "How these figures are put together")] : null);
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

// The view switch (view.js) that shows a race box of each kind, and the one that opens it rather
// than folding it (openBoxes, or a focus), as they do the Funding line; other boxes always show,
// open. Each box's short heading, and a shorter one on a phone, where the head stays on one line.
const FOLDS = { money: "showFunding", polls: "showPolls" };
const OPENS = { money: "openMoney", polls: "openPolls" };
const SHORT_TITLES = { money: "Money raised", polls: "Polls" };
const PHONE_TITLES = { money: "Money", polls: "Polls" };

// The "?" on a tab, badge or button whose source only likely matched the candidate.
function likelyFlag(title = "Likely match") {
  return h("span", { class: "likely-flag", title }, "?");
}

// A badge with a url links to that source's page for the candidate (opens a new tab). On
// the candidate row it carries its ``card``: the source's name, and for a likely match a
// note, plus a "?" on the ``first`` of that source's badges. With ``onOpen(card)`` it's a button,
// drawn like Profile with a chevron, that opens Details at the source to see who gave to ``who`` (a
// Funding chip). ``label`` shows instead of the badge's text, which then names it and is its tooltip.
function badge(item, card = null, first = false, label = item.text, onOpen = null, who = null) {
  const likely = card && isLikely(card);
  const short = label !== item.text;
  const flag = likely && first ? likelyFlag() : null;
  if (onOpen) {
    const see = `See who gave to ${who}`;
    return h("li", {}, h("button", { type: "button", class: ["badge badge-btn badge-open", `tone-${item.tone}`],
      title: [see, item.hint, likely ? "Likely match" : null].filter(Boolean).join(" · "),
      "aria-label": `${item.text}${flag ? " (likely match)" : ""}: ${see.toLowerCase()}`, on: { click: () => onOpen(card) } },
    label, flag, h("span", { class: "badge-chevron", "aria-hidden": "true" }, "›")));
  }
  const title = [short ? item.text : null, item.hint, card && !short ? `From ${card.label}` : null,
    likely ? "Likely match" : null].filter(Boolean).join(" · ") || null;
  const name = short ? `${item.text}${flag ? " (likely match)" : ""}` : null;
  return h("li", {}, safeUrl(item.url)
    ? extLink(item.url, [label, flag, h("span", { class: "badge-arrow", "aria-hidden": "true" }, "↗")],
        { class: ["badge badge-link", `tone-${item.tone}`], title, "aria-label": name && `${name} (opens in a new tab)` })
    : h("span", { class: ["badge", `tone-${item.tone}`], title, "aria-label": name }, label, flag));
}

let lineIds = 0;
const POPOVERS = Object.hasOwn(HTMLElement.prototype, "popover");

// A chip Help me pick knows (barChoice in pick-rules.js): a button opening a small menu, over the
// page, with its source's page for the candidate (the plain chip's link) and "Pick List A's
// candidates" (or Avoid, for an amber one), which chooses it in Help me pick. A browser without
// popovers gets the plain chip.
function chipMenu(item, card, first, label, choice) {
  const flag = isLikely(card) && first ? likelyFlag() : null;
  const id = `chip-menu-${++lineIds}`;
  const add = () => {
    menu.hidePopover();
    chooseInHelp(choice);
  };
  const button = h("button", {
    type: "button", class: ["badge badge-btn chip-menu-btn", `tone-${item.tone}`], popovertarget: id,
    title: [label !== item.text ? item.text : null, item.hint, isLikely(card) ? "Likely match" : null].filter(Boolean).join(" · ") || null,
    "aria-label": `${item.text}${flag ? " (likely match)" : ""}: open, or ${choice.kind === "endorsers" ? "pick who it endorses" : "avoid on the ballot"}`,
  }, label, flag, h("span", { class: "badge-caret", "aria-hidden": "true" }, "▾"));
  const menu = h("div", { id, popover: "auto", class: "chip-menu" },
    safeUrl(item.url) ? webLink(item.url, `Open ${card.label}`) : null,
    h("button", { type: "button", class: "link-btn", on: { click: add } },
      choice.kind === "endorsers" ? `Pick ${choice.label}'s candidates` : `Avoid “${choice.label}” on the ballot`));
  const place = (box) => {
    const below = box.bottom + 4;
    const fits = below + menu.offsetHeight <= innerHeight - 8;
    menu.style.top = `${fits ? below : Math.max(8, box.top - menu.offsetHeight - 4)}px`;
    menu.style.left = `${Math.max(8, Math.min(box.left, innerWidth - menu.offsetWidth - 8))}px`;
  };
  const close = () => {
    if (menu.matches(":popover-open")) menu.hidePopover();
  };
  menu.addEventListener("toggle", (event) => {
    if (event.newState !== "open") return;
    place(button.getBoundingClientRect());
    addEventListener("scroll", close, { once: true, passive: true });
  });
  menu.addEventListener("beforetoggle", (event) => {
    if (event.newState === "open") place(button.getBoundingClientRect());
  });
  return h("li", {}, button, menu);
}

// A candidate's line that folds: ``body`` (with an id) under a button, ``label``, that opens it in
// place. The view switch ``shown`` shows the line; with ``opens`` on, it's open and the button
// hidden. A "pallot:sync" puts it back to the two switches, opened by hand or not.
function foldLine(className, body, label, shown, opens) {
  const show = (open) => {
    body.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  };
  const toggle = h("button", {
    type: "button", class: "link-btn lines-toggle", "aria-controls": body.id,
    on: { click: () => show(body.hidden) },
  }, label);
  const sync = () => {
    const open = viewPref(opens);
    element.hidden = !viewPref(shown);
    toggle.hidden = open;
    show(open);
  };
  const element = h("div", { class: className, on: { "pallot:sync": sync } }, toggle, body);
  sync();
  return element;
}

// The candidate's Endorsements line, a ul labelled by its heading. A green chip shows just the
// source's name, since the heading says "Endorsements"; an amber one says what it is ("TrackAIPAC
// watchlist"), so it doesn't rest on the colour. It folds (foldLine) by the showEndorsements and
// openEndorsements switches, to a count ("3 endorsements"), until syncLines(). A chip links to its
// source's page for the candidate, or opens chipMenu() when Help me pick knows it.
export function sourceLines(candidate) {
  const items = greenFirst(candidate.cards.flatMap((card) => sided(card).map((b) => ({ b, card }))), (item) => item.b.tone);
  const chips = chipsOf(items, (b, card, first) => {
    const label = b.tone === "good" ? card.label : b.text;
    const choice = POPOVERS ? barChoice(card, b) : null;
    return choice ? chipMenu(b, card, first, label, choice) : badge(b, card, first, label);
  });
  if (!chips.length) return null;
  const id = `lines-${++lineIds}`;
  const body = h("div", { class: "cand-lines-body", id }, h("div", { class: "badge-line" },
    h("span", { class: "line-title", id: `${id}-title` }, "Endorsements"),
    h("ul", { class: "badges", "aria-labelledby": `${id}-title` }, chips)));
  return foldLine("cand-lines", body, plural(chips.length, "endorsement"), "showEndorsements", "openEndorsements");
}

// Every candidate's lines go back to their view switches, opened by hand or not.
export function syncLines() {
  for (const element of document.querySelectorAll(".cand-lines")) element.dispatchEvent(new Event("pallot:sync"));
}

// The candidate's Funding line, after their other lines: each money card's chips (fundingChips),
// as its tab in Details shows them, with a "?" on the first of a card that only likely matched. It
// folds (foldLine) as the Endorsements line does, by the showFunding switch (with the money boxes)
// and openMoney, to a count ("Funding · 4"), until syncFunding(). A chip opens Details at its money
// source, ``onOpen(card)``. The "?" beside its heading says what the colors mean (fundingHelp).
export function fundingLine(candidate, onOpen) {
  const cards = candidate.cards.filter((card) => fundingChips(card).length);
  if (!cards.length) return null;
  const id = `funding-${++lineIds}`;
  const chips = chipsOf(cards.flatMap((card) => fundingChips(card).map((b) => ({ b, card }))),
    (b, card, first) => badge(b, card, first, b.text, onOpen, candidate.name));
  const body = h("div", { class: "cand-lines-body", id }, h("div", { class: "badge-line" },
    h("span", { class: "line-title" }, h("span", { id: `${id}-title` }, "Funding"), fundingHelp()),
    h("ul", { class: "badges", "aria-labelledby": `${id}-title` }, chips)));
  return foldLine("cand-lines funding-line", body, `Funding · ${chips.length}`, "showFunding", "openMoney");
}

// A write-in whose row would show nothing but their name: no endorsement either way, and no money
// or polling in the race's boxes. The race lists such write-ins on one line (race-cards.js).
export function quietWriteIn(race, candidate) {
  if (!candidate.write_in || candidate.cards.some((card) => sided(card).length)) return false;
  return !(race.cards || []).some((card) => card.breakdowns?.[0]?.parts.some((p) => p.candidate_key === candidate.key && p.amount > 0));
}

// Every candidate's Funding line goes back to the showFunding and openMoney switches.
export function syncFunding() {
  for (const element of document.querySelectorAll(".funding-line")) element.dispatchEvent(new Event("pallot:sync"));
}


// " by full name, in the same seat. Party differs."
const matchWhy = (match) => ` by ${match.method}.${match.note ? ` ${match.note[0].toUpperCase()}${match.note.slice(1)}.` : ""}`;

// A word such as "for" or "against", as a small badge in the row's tone.
export function tagBadge(part) {
  return part.tag ? h("span", { class: ["badge share-tag", `tone-${part.tone || "neutral"}`] }, part.tag) : null;
}

// A poll row's tag: the lead over the closest rival ("+1.9"), who is named in its tooltip and,
// for touch screens and screen readers, in a "vs Ken Paxton" after it.
function marginTag(part) {
  const said = part.tag === "Tied" ? `Tied with ${part.versus}`
    : `${part.tone === "good" ? "Ahead of" : "Behind"} ${part.versus} by ${part.tag.slice(1)} points`;
  return [h("span", { class: ["badge share-tag", `tone-${part.tone || "neutral"}`], title: said, "aria-hidden": "true" }, part.tag),
    h("span", { class: "share-versus" }, h("span", { class: "sr-only" }, `${said}. `), h("span", { "aria-hidden": "true" }, `vs ${part.versus}`))];
}

// One row of a breakdown: the label (with its note), a bar, and the amount. In a race's box,
// ``people`` knows each candidate (by key): their party, so the bars take the party colours,
// and whether the box's source only likely matched them, which puts a "?" after the name.
// In "points" (a poll each) the amount is the candidate's share, the label links to the poll,
// and the tag is marginTag().
function shareRow(part, scale, showPercent, people, points = false) {
  const count = part.count ? plural(part.count, "donation") : null;
  const note = [part.note, count].filter(Boolean).join(" · ");
  const party = part.candidate_key && people ? people.party(part.candidate_key) : null;
  const likely = part.candidate_key && people?.likely(part.candidate_key);
  const label = points && safeUrl(part.url) ? webLink(part.url, part.label) : part.label;
  return h(
    "li",
    { class: ["share", !points && part.tone && `tone-${part.tone}`], "data-party": party || null },
    h("span", { class: "share-label" }, label, likely ? likelyFlag("Likely match: see Issues") : null,
      points && part.versus ? marginTag(part) : tagBadge(part),
      note ? h("span", { class: "share-note" }, note) : null),
    bar(scale > 0 && part.amount != null ? part.amount / scale : 0),
    h("span", { class: "share-amount" },
      part.amount == null ? "—" : points ? `${part.amount}%` : DOLLARS.format(part.amount),
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
// ``parts`` are only those who raised something (raceMoney).
function moneyStack(parts, people) {
  const sum = parts.reduce((total, p) => total + p.amount, 0);
  const partyAttr = (part) => (part.candidate_key && people ? people.party(part.candidate_key) : null);
  const likely = (part) => (part.candidate_key && people?.likely(part.candidate_key) ? likelyFlag("Likely match: see Issues") : null);
  return [
    h("div", { class: "stack-bar", role: "img", "aria-label": parts.map((p) => `${p.label} ${DOLLARS.format(p.amount)}`).join(", ") },
      parts.map((part) => h("span", {
        "data-party": partyAttr(part), style: `width: ${width(part.amount / sum)}`,
        title: `${part.label} ${DOLLARS.format(part.amount)}`,
      }))),
    h("ul", { class: "stack-legend" }, parts.map((part) => h("li", { "data-party": partyAttr(part) },
      h("span", { class: "cmp-swatch", "aria-hidden": "true" }),
      h("span", {}, part.label, likely(part)),
      h("strong", {}, DOLLARS_SHORT.format(part.amount)))),
      h("li", { class: "stack-total" }, h("span", {}, "Total"), h("strong", {}, DOLLARS_SHORT.format(sum)))),
  ];
}

// A Breakdown's bars and note. With a total they're shares of it (and show a %); without one
// they're scaled to the largest part. In "points" each bar is 0-100, with its ``mark`` (the
// median) a line across them. ``tail`` goes at the right of the note.
function breakdownRows(item, people = null, tail = null) {
  const largest = Math.max(0, ...item.parts.map((p) => p.amount || 0));
  const points = item.unit === "points";
  const scale = points ? 100 : item.total || largest;
  return [
    item.unit === "percent"
      ? stackedBar(item, people)
      : h("ul", { class: ["breakdown-rows", points && "poll-rows", points && item.mark != null && "marked"],
          style: points && item.mark != null ? `--mark: ${width(item.mark / 100)}` : null },
        item.parts.map((part) => shareRow(part, scale, Boolean(item.total), people, points))),
    tail ? h("div", { class: "box-foot" }, item.note ? h("p", { class: "fine" }, item.note) : null, tail)
      : item.note ? h("p", { class: "fine" }, item.note) : null,
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
  const asOf = box.querySelector(".box-asof");
  if (asOf) asOf.hidden = !open;
}

// A race box that folds: its short heading ("Money raised", "Polls") as a button that folds it to
// that one line, with ``action`` (the box's corner) at the right; folded, it names nobody. Open, the
// rest of its first breakdown's title, or just its brackets' period, and its date ("since Nov 6, 2024
// · reports through Sep 24, 2026", "latest poll Oct 5, 2026") sit in small print beside the heading,
// hidden from screen readers since the button's name is the whole title and date. The view switch
// ``setting`` shows or hides it, and its kind's OPENS opens or folds it; a click opens or folds just
// this one, until syncBoxes().
function foldBox(race, card, setting, action, body) {
  const id = `box-${slug(race.key)}-${card.source}`;
  const title = card.breakdowns[0]?.title || card.description;
  const short = SHORT_TITLES[card.kind];
  const rest = title.startsWith(short) ? title.slice(short.length).trim() : title;
  const period = /\(([^()]+)\)$/.exec(rest)?.[1] || rest;
  const asOf = card.as_of ? `${AS_OF_WORDS[card.source] || "data as of"} ${formatDate(card.as_of, SHORT_DATE)}` : null;
  const toggle = h("button", {
    type: "button", class: "box-toggle", "aria-controls": id, "aria-label": [title, asOf].filter(Boolean).join(" · "),
    on: { click: () => setBoxOpen(box, box.classList.contains("collapsed")) },
  }, h("span", { class: "chevron", "aria-hidden": "true" }), phoneWords(short, PHONE_TITLES[card.kind]));
  // a poll box's date in short, "updated Oct 16"; the button's name keeps it in full
  const shownAsOf = card.kind === "polls" && card.as_of ? `updated ${formatDate(card.as_of, { month: "short", day: "numeric" })}` : asOf;
  const foot = [period, shownAsOf].filter(Boolean).join(" · ");
  const box = h("div", { class: "race-money", "data-show": setting, "data-open": OPENS[card.kind], hidden: !viewPref(setting) },
    h("div", { class: "breakdown-head" }, h("h4", { class: "breakdown-title" }, toggle),
      foot ? h("span", { class: "box-asof", "aria-hidden": "true" }, foot) : null, action),
    h("div", { class: "box-body", id }, body));
  setBoxOpen(box, viewPref(OPENS[card.kind]));
  return box;
}

// A poll box's corner: only the "?" to the FAQ's answer on how the bar is worked out. The count is in
// the median line, and the source's link at its end (pollSource), so the head stays one short line.
function pollCorner() {
  return h("span", { class: "box-links" }, helpLink(MONEY_FAQ.polls, "how the poll bar is worked out"));
}

// The poll source's link, at the right of the median line under the bars.
function pollSource(card) {
  return card.url ? extLink(card.url, `${card.label} ↗`, { class: "icon-btn", title: `Open ${card.label}` }) : null;
}

// A money box's corner, like a poll box's: Compare funding (``compare``), the source, and a "?" to
// the FAQ's answer on how its figures are put together.
function moneyCorner(card, compare) {
  const faq = MONEY_FAQ[card.source];
  return h("span", { class: "box-links" },
    compare,
    card.url ? extLink(card.url, `${card.label} ↗`, { class: "icon-btn", title: `Open ${card.label}` }) : null,
    faq ? helpLink(faq, `how ${card.label}'s figures are put together`) : null);
}

// After a view switch changes: openMoney or openPolls opens or folds every box of its kind, whether
// it was opened or folded by hand; showFunding or showPolls shows or hides its kind of box.
export function syncBoxes(setting) {
  for (const box of document.querySelectorAll(".race-money[data-show]")) {
    if (box.dataset.open === setting) setBoxOpen(box, viewPref(setting));
    else if (box.dataset.show === setting) box.hidden = !viewPref(setting);
  }
}

const pollHead = (race) => (race.cards || []).find((card) => card.kind === "polls")?.breakdowns?.[0];

// Whether the race's poll box has anyone polling above zero.
export const hasPolls = (race) => Boolean(pollHead(race)?.parts.some((p) => p.amount > 0));

// With the pollChips switch, a pill on a polled candidate's row: "47% in polls".
export function pollPill(race, candidate) {
  const share = viewPref("pollChips") ? pollHead(race)?.parts.find((p) => p.candidate_key === candidate.key)?.amount : null;
  return share > 0 ? h("span", { class: "pill poll-pill", title: "Their share in the race's poll box" }, `${pct(share)} in polls`) : null;
}

// A race's cards (money raised per money source, then polls), shown above its candidates.
// With ``onCompare``, the first comparable one has a button for the Compare dialog. A money or
// poll box shows only the candidates with something above zero; with nobody left, it isn't drawn.
// Compare, Details and Pick by rule still have everyone.
export function raceMoney(race, onCompare = null) {
  if (!race.cards?.length) return null;
  const candidate = (key) => race.candidates.find((c) => c.key === key);
  const [first] = comparable(race);
  let button = null;
  if (onCompare && first) {
    button = h("button", { type: "button", class: "icon-btn compare-btn with-icon", "aria-label": `Compare funding in ${race.name}`,
      on: { click: onCompare } }, icon("bars"), phoneWords("Compare funding", "Compare"));
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
    const shown = head ? head.parts.filter((p) => p.amount > 0) : [];
    if (!shown.length && !rest.length) return null;
    const polls = card.kind === "polls";
    return foldBox(race, card, setting, polls ? pollCorner() : moneyCorner(card, action), [
      shown.length ? h("section", { class: "breakdown" }, polls ? breakdownRows({ ...head, parts: shown }, people, pollSource(card)) : moneyStack(shown, people)) : null,
      rest.map((b) => breakdownBlock(b, people)),
    ]);
  });
}

// A card's badges and facts, as a source's tab (sourcePanel) shows them: a money card's chips on one
// Funding line, in the row's order (fundingChips).
const cardSummary = (card) => [
  fundingChips(card).length
    ? h("div", { class: "badge-line panel-funding" }, h("span", { class: "line-title" }, "Funding"),
        h("ul", { class: "badges", "aria-label": "Funding" }, fundingChips(card).map((b) => badge(b))))
    : card.badges.length ? h("ul", { class: "badges" }, card.badges.map((b) => badge(b))) : null,
  cardFacts(card),
];
const cardFacts = (card) => card.facts.length
  ? h("dl", { class: "facts" }, card.facts.map((f) => [h("dt", {}, f.label), h("dd", {}, f.url ? webLink(f.url, f.value) : f.value)]))
  : null;
const cardQuotes = (card) => card.quotes.length
  ? h("div", { class: "quotes" }, h("p", { class: "quotes-title" }, `In ${card.label}'s words`), card.quotes.map((q) => h("blockquote", {}, linkedText(q))))
  : null;
const cardLinks = (card) => card.links.length
  ? h("ul", { class: "links" }, card.links.map((l) => h("li", {}, webLink(l.url, l.label))))
  : null;

// A source's tab's links, each once: the card's own, its source's page unless one of them is it,
// and, for a money source or polls, the FAQ's answer on how its figures are put together.
function sourceLinks(card) {
  const faq = MONEY_FAQ[card.source];
  const links = safeUrl(card.url) && !card.links.some((l) => l.url === card.url)
    ? [{ url: card.url, label: `Open ${card.label}` }, ...card.links] : card.links;
  const items = [...links.map((l) => h("li", {}, webLink(l.url, l.label))),
    faq ? h("li", {}, extLink(`faq.html#${faq}`, "How these figures are put together")) : null].filter(Boolean);
  return items.length ? h("ul", { class: "links" }, items) : null;
}

// A source's tab in Details (a money source's, or any other drawn by cardPanel), matched as the
// Profile tab is: its description and a likely match's reason (likelyLine), then its summary (titled
// ``summaryTitle``) and each breakdown in a section of its own, the first with how it matched and the
// day of the source's copy (sectionMeta), then its links (sourceLinks).
function sourcePanel(card, className, summaryTitle) {
  const summary = cardSummary(card).filter(Boolean);
  const meta = sectionMeta(card);
  const head = summary.length ? foldSection(summaryTitle, meta, summary) : null;
  return h("div", { class: ["card-panel", className] },
    card.description ? h("p", { class: "muted" }, card.description) : null,
    likelyLine(card),
    head,
    cardQuotes(card),
    (card.breakdowns || []).map((b, i) => foldSection(b.title, !head && i === 0 ? meta : null, breakdownRows(b))),
    sourceLinks(card));
}

export function cardPanel(card) {
  return sourcePanel(card, null, "Summary");
}

// A money source's tab (FEC, TEC): its totals, then who gave, as sourcePanel() lays it out.
export function moneyPanel(card) {
  return sourcePanel(card, "money", "Totals");
}

// A box on a Details tab that folds to its summary (its name, then ``extra``, such as a "?" or
// chips) when the voter clicks it, open at first: the Profile, Issues, Endorsements and money tabs
// are made of them. ``tone`` ("good", "warn") colours its edge.
export function foldSection(name, extra, body, tone = null) {
  return h("details", { class: ["source-section", tone && `tone-${tone}`], open: true },
    h("summary", {}, h("span", { class: "source-section-name" }, name), extra),
    h("div", { class: "section-body" }, body));
}

// A Details section's title line, at the right (every tab's, on its first section): how it matched
// and the day of the source's copy ("Exact match · Oct 8, 2026"), or just the day for a source with
// no match (Texas SOS, polls). The match's reason is in its tooltip and, for screen readers, after it.
function sectionMeta(card) {
  const exact = card.match?.confidence === "exact";
  const parts = [exact ? "Exact match" : null, card.as_of ? formatDate(card.as_of, SHORT_DATE) : null].filter(Boolean);
  if (!parts.length) return null;
  return h("span", { class: "section-meta", title: [exact ? `Matched${matchWhy(card.match)}` : null,
    card.as_of ? `${card.label}'s data as of ${formatDate(card.as_of, SHORT_DATE)}` : null].filter(Boolean).join(" ") },
    parts.join(" · "), exact ? h("span", { class: "sr-only" }, `: matched${matchWhy(card.match)}`) : null);
}

const likelyLine = (card) => isLikely(card)
  ? h("p", { class: "match-line" }, h("strong", {}, "Likely match"), matchWhy(card.match))
  : null;

// A Profile section's body: a likely match's reason, the facts, the quotes and the links, with no
// match box, chips or "Open …" line, since the title line has the match and the links the pages.
function profileBody(card) {
  return h("div", { class: "card-panel" }, likelyLine(card), cardFacts(card), cardQuotes(card), cardLinks(card));
}

// Details' Profile tab: the candidate's filing with the state (Texas SOS), then Wikidata's
// profile, a section each; with none, a line saying so about ``name``.
export function profilePanel(cards, name) {
  return h("div", { class: "card-panel profile" },
    cards.length
      ? cards.map((card) => foldSection(card.label, [isLikely(card) ? likelyFlag() : null, sectionMeta(card)], profileBody(card)))
      : h("p", { class: "muted" }, `None of Pallot's sources has a profile of ${name} yet.`));
}

// Details' Polls tab: the candidate's median, large, over one bar in their party's colour, with
// how it's worked out, and the day of the latest poll in its title line (sectionMeta); then a bar
// per poll on the same 0-100 scale, the median a line across them, each pollster linking to its
// poll; then the source's links (sourceLinks). The rows name no other candidate but in a margin's "vs".
export function pollsPanel(card, party) {
  const [each] = card.breakdowns;
  const median = card.figures?.poll;
  const people = { party: () => party || null, likely: () => false };
  return h("div", { class: "card-panel polls" },
    likelyLine(card),
    median != null ? foldSection("Median", sectionMeta(card), [
      h("div", { class: "poll-median", "data-party": party || null },
        h("strong", { class: "poll-median-value" }, `${median}%`), bar(median / 100)),
      each?.note ? h("p", { class: "fine" }, each.note) : null,
    ]) : null,
    each ? foldSection(each.title, each.count ? h("span", { class: "section-meta" }, plural(each.count, "poll")) : null,
      breakdownRows({ ...each, note: null }, people)) : null,
    sourceLinks(card));
}

// A chip's words beside its source's name: "Endorsed by CAIR Action" is "Endorsed", "TrackAIPAC
// watchlist" "Watchlist", "Vote for Peace: Ally" "Ally".
function chipWords(item, card) {
  const words = item.text.replace(card.label, "").replace(/^[\s:]+|\s+by\s*$/g, "").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : item.text;
}

// Details' Endorsements tab: a section per source, all open, green ones (for the candidate) first,
// then amber (against), then the rest, each with its side's colour on its edge. Its title line has
// the source, its chips (what the source says, open or folded), and at the right how it matched and
// the day of the source's copy ("Exact match · Oct 8, 2026"), so the body doesn't repeat them: a
// likely match's reason, the facts (the office, linked to the source's page for the candidate), the
// quotes and the links. The match isn't a green box there, which would read as one more endorsement.
const SIDE_ORDER = { good: 0, warn: 1 };
const SIDE_TONES = ["good", "warn", null];
const side = (card) => Math.min(2, ...card.badges.map((b) => SIDE_ORDER[b.tone] ?? 2));

// The facts, an Office as a chip linking to the source's page for the candidate (no "Office" label)
// and the rest as rows, in order: TrackAIPAC's figures follow the listing they're from.
function endorsementFacts(card) {
  const blocks = [];
  for (const fact of card.facts) {
    if (fact.label === "Office") {
      blocks.push(h("ul", { class: "badges office-chip" }, badge({ text: fact.value, tone: "neutral", url: fact.url })));
    } else {
      if (blocks.at(-1)?.tagName !== "DL") blocks.push(h("dl", { class: "facts" }));
      blocks.at(-1).append(h("dt", {}, fact.label), h("dd", {}, fact.url ? webLink(fact.url, fact.value) : fact.value));
    }
  }
  return blocks;
}

function endorsementBody(card) {
  return h("div", { class: "card-panel" },
    likelyLine(card),
    endorsementFacts(card),
    cardQuotes(card),
    cardLinks(card));
}

export function endorsementsPanel(cards) {
  const sorted = [...cards].sort((a, b) => side(a) - side(b));
  const section = (card) => foldSection(card.label, [
    card.badges.map((b) => h("span", { class: ["badge", `tone-${b.tone}`], title: b.text }, chipWords(b, card))),
    isLikely(card) ? likelyFlag() : null,
    sectionMeta(card),
  ], endorsementBody(card), SIDE_TONES[side(card)]);
  return h("div", { class: "card-panel endorsements" },
    h("p", { class: "muted" }, plural(cards.length, "endorsement")),
    sorted.map(section));
}

// A tab's "?": its name says "likely match" to a screen reader, and a tap on the "?" opens a note
// saying why (a button can't sit inside the tab, nor beside it in the tab row). A tab of one card
// gives its match's reason; one gathering several (Profile, Endorsements) points to its sections.
function tabFlag(card) {
  const one = [card.card, card].find((c) => c?.match);
  const why = isLikely(one) ? `Likely match${matchWhy(one.match)} Check it's the same person.`
    : "Likely match: a source on this tab may not be this candidate. Its section says why.";
  const flag = h("span", { class: "likely-flag", "aria-hidden": "true" }, "?");
  flag.note = () => [h("p", {}, why), h("p", {}, extLink("faq.html#matches", "Exact and likely matches"))];
  return [h("span", { class: "sr-only" }, ", likely match"), flag];
}

// The tab row scrolls sideways when its tabs don't fit (on a phone), and fades at an edge with more
// tabs past it, so a cut-off tab reads as "scroll for more".
function fadeEdges(tablist) {
  const sync = () => {
    const end = tablist.scrollWidth - tablist.clientWidth;
    tablist.classList.toggle("more-before", tablist.scrollLeft > 1);
    tablist.classList.toggle("more-after", tablist.scrollLeft < end - 1);
  };
  tablist.addEventListener("scroll", sync, { passive: true });
  new ResizeObserver(sync).observe(tablist);
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
      (card.likely ?? isLikely(card)) ? tabFlag(card) : null,
    );
    const panel = h("div", { class: "tab-panel", role: "tabpanel", id: panelId, "aria-labelledby": tabId, tabindex: "0", hidden: i !== initial }, panelFor(card));
    tabs.push(tab);
    panels.push(panel);
  });

  // A tap on a "?" leaves the row where it is: scrolling it would close the note it opens.
  function select(index, focus = true, scroll = true) {
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      panels[i].hidden = i !== index;
    });
    if (scroll) tabs[index].scrollIntoView({ block: "nearest", inline: "nearest" }); // the row scrolls sideways on a phone
    if (focus) tabs[index].focus();
    onSelect?.(index);
  }

  tablist.addEventListener("click", (event) => {
    const index = tabs.indexOf(event.target.closest('[role="tab"]'));
    if (index < 0) return;
    const flag = event.target.closest(".likely-flag");
    select(index, false, !flag);
    if (flag) toggleNote(flag, flag.note);
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
  fadeEdges(tablist);
}
