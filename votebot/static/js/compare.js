// The Compare dialog: a race's candidates side by side for one money source (the TEC for
// state races, the FEC for federal ones). A category every candidate has ("Individuals")
// is a tight group of bars, one per candidate; named donors and spenders are columns, with a
// name more than one candidate has flagged. The server builds the Comparison; this draws it.

import { dialogHead, h, slug } from "./dom.js";
import { DOLLARS, DOLLARS_SHORT, SHORT_DATE, formatDate, percent, plural } from "./format.js";
import { partyName } from "./labels.js";
import { setUiPref, uiPref } from "./storage.js";
import { bar, comparable, renderTabs, sourceLine, tagBadge } from "./source-cards.js";

const SCALES = [["dollars", "Dollars"], ["share", "Share of their money"]];

const counted = (count, what) => (count ? plural(count, what) : "");

function amountText(amount, share) {
  return [
    amount == null ? "—" : (Math.abs(amount) < 1000 ? DOLLARS : DOLLARS_SHORT).format(amount), // "$539", "$1.2K"
    share != null ? h("span", { class: "share-pct" }, percent(share)) : null,
  ];
}

// ---- the candidates ------------------------------------------------------------------

function legend(race, comparison, source) {
  const dates = new Set(Object.values(comparison.as_of));
  return h("ul", { class: "cmp-legend", "aria-label": "Candidates" }, race.candidates.map((candidate) => {
    const has = comparison.candidates.includes(candidate.key);
    const through = comparison.as_of[candidate.key];
    const sub = !has ? `No ${source} data` : dates.size > 1 && through ? `Reports through ${formatDate(through, SHORT_DATE)}` : null;
    return h("li", { class: ["cmp-chip", !has && "missing"], "data-party": candidate.party || null },
      h("span", { class: "cmp-swatch", "aria-hidden": "true" }),
      h("span", { class: "cmp-chip-name" }, candidate.name),
      partyName(candidate) ? h("span", { class: "cmp-chip-sub" }, partyName(candidate)) : null,
      sub ? h("span", { class: "cmp-chip-sub" }, sub) : null);
  }));
}

// ---- grouped bars ----------------------------------------------------------------------

// One candidate's bar. It carries both widths; the dialog's data-scale picks one.
function barRow(value, candidate, largest, whole, what) {
  const { amount } = value;
  const share = whole && amount != null ? amount / whole : null;
  const dollars = largest > 0 && amount ? amount / largest : 0;
  return h("li", { class: "cmp-bar", "data-party": candidate?.party || null },
    h("span", { class: "cmp-name", title: candidate?.name }, candidate?.name || "Unknown"),
    bar({ dollars, share: share ?? dollars }),
    h("span", { class: "cmp-amount", title: amount != null ? DOLLARS.format(amount) : "No figure from this source" },
      amountText(amount, share)),
    h("span", { class: "cmp-count" }, counted(value.count, what)));
}

function barsSection(section, byKey) {
  const largest = Math.max(0, ...section.rows.flatMap((row) => row.values.map((v) => v.amount || 0)));
  const shares = Object.keys(section.totals).length > 0;
  return h("section", { class: ["cmp-section", shares && "has-shares"] },
    h("h3", { class: "breakdown-title" }, section.title),
    h("div", { class: "cmp-grid" }, section.rows.map((row) =>
      h("div", { class: "cmp-group" },
        h("p", { class: "cmp-cat" }, row.label),
        h("ul", { class: "cmp-bars", "aria-label": row.label },
          row.values.map((value) => barRow(value, byKey.get(value.candidate_key), largest,
            section.totals[value.candidate_key], row.counted || section.counted)))))),
    section.note ? h("p", { class: "fine" }, section.note) : null);
}

// ---- side-by-side columns --------------------------------------------------------------

function entryRow(entry, largest, byKey, what) {
  const others = entry.shared_with.map((key) => byKey.get(key)?.name).filter(Boolean);
  const note = [entry.note, counted(entry.count, what)].filter(Boolean).join(" · ");
  return h("li", {
    class: ["cmp-entry", entry.tone && `tone-${entry.tone}`, others.length && "shared"],
    "data-match": entry.match_key || null,
    tabindex: others.length ? "0" : null,
    title: others.length === 1 ? `Also in ${others[0]}'s list` : others.length ? `Also in the lists of ${others.join(", ")}` : null,
  },
  h("span", { class: "cmp-entry-name" },
    others.length ? h("span", { class: "cmp-flag", "aria-hidden": "true" }, "⇄") : null, entry.label, tagBadge(entry)),
  h("span", { class: "cmp-amount", title: entry.amount != null ? DOLLARS.format(entry.amount) : null }, amountText(entry.amount, null)),
  note ? h("span", { class: "cmp-entry-note" }, note) : null,
  others.length ? h("span", { class: "cmp-also" }, `Also: ${others.join(", ")}`) : null,
  bar(largest > 0 && entry.amount ? entry.amount / largest : 0));
}

function columnsSection(section, comparison, byKey) {
  const entries = Object.values(section.columns).flat();
  const largest = Math.max(0, ...entries.map((e) => e.amount || 0));
  // Each shared name is in 1 + shared_with.length columns, so this counts every name once.
  const sharedNames = Math.round(entries.reduce((n, e) => n + (e.shared_with.length ? 1 / (e.shared_with.length + 1) : 0), 0));
  const element = h("section", { class: "cmp-section" },
    h("h3", { class: "breakdown-title" }, section.title),
    sharedNames
      ? h("p", { class: "cmp-shared-note" }, h("span", { class: "cmp-flag", "aria-hidden": "true" }, "⇄"),
          `${sharedNames} ${sharedNames === 1 ? "name appears" : "names appear"} for more than one candidate.`)
      : null,
    h("div", { class: "cmp-columns" }, comparison.candidates.map((key) => {
      const candidate = byKey.get(key);
      const list = section.columns[key] || [];
      return h("section", { class: "cmp-col", "data-party": candidate?.party || null },
        h("h4", { class: "cmp-col-head" }, candidate?.name || key),
        list.length
          ? h("ol", { class: "cmp-list" }, list.map((entry) => entryRow(entry, largest, byKey, section.counted)))
          : h("p", { class: "muted small" }, "None reported."));
    })),
    section.note ? h("p", { class: "fine" }, section.note) : null);

  // Pointing at (or tabbing to) a shared name lights it up in every column.
  const light = (event, on) => {
    const entry = event.target.closest?.(".cmp-entry[data-match]");
    if (!entry) return;
    for (const same of element.querySelectorAll(".cmp-entry[data-match]")) {
      if (same.dataset.match === entry.dataset.match) same.classList.toggle("linked", on);
    }
  };
  element.addEventListener("mouseover", (event) => light(event, true));
  element.addEventListener("mouseout", (event) => light(event, false));
  element.addEventListener("focusin", (event) => light(event, true));
  element.addEventListener("focusout", (event) => light(event, false));
  return element;
}

// ---- the dialog ------------------------------------------------------------------------

function comparisonPanel(race) {
  const byKey = new Map(race.candidates.map((c) => [c.key, c]));
  return (card) => {
    const { comparison } = card;
    return h("div", { class: "cmp-panel" },
      legend(race, comparison, card.label),
      comparison.sections.map((section) =>
        (Object.keys(section.columns).length ? columnsSection(section, comparison, byKey) : barsSection(section, byKey))),
      sourceLine(card));
  };
}

function scaleToggle(dialog) {
  const current = dialog.dataset.scale;
  return h("fieldset", { class: "seg" },
    h("legend", { class: "sr-only" }, "Bar length"),
    SCALES.map(([value, label]) => {
      const change = () => {
        dialog.dataset.scale = value;
        setUiPref("compareScale", value);
      };
      return h("label", { class: "seg-option" },
        h("input", { type: "radio", name: "cmp-scale", value, checked: value === current, on: { change } }), label);
    }));
}

export function openCompare(dialog, race) {
  const cards = comparable(race);
  if (!cards.length) return;
  dialog.dataset.scale = uiPref("compareScale") === "share" ? "share" : "dollars";
  const body = h("div", { class: "details-tabs" });
  const panel = comparisonPanel(race);
  if (cards.length > 1) renderTabs(body, cards, `cmp-${slug(race.key)}`, panel);
  else body.append(h("div", { class: "tab-panel" }, panel(cards[0])));

  const { head, close } = dialogHead(dialog,
    h("div", { class: "details-title" }, h("h2", { id: "compare-title" }, "Compare candidates"), h("p", { class: "muted" }, race.name)));
  dialog.replaceChildren(
    head,
    h("div", { class: "cmp-controls" },
      scaleToggle(dialog),
      h("p", { class: "fine" }, "Share: each bar is that part of the candidate's own money, so a small campaign's mix "
        + "compares with a big one's. Totals and name lists stay in dollars.")),
    body,
  );
  dialog.showModal();
  close.focus();
}
