// The ballot's race and proposition cards: the groups, the sections that may not be on the
// ballot, and the propositions, each card collapsible, with its candidates, notes and write-in.
// Picking here saves to ``page.picks``; ballot.js hands over the context (initRaceCards).

import { ballotSections, measureKey, pickLabels } from "./ballot-shared.js";
import { openCompare } from "./compare.js";
import { $, autosave, extLink, h, initials, safeUrl, slug } from "./dom.js";
import { plural } from "./format.js";
import { icon } from "./icons.js";
import { STATES, candidatePills } from "./labels.js";
import { WRITE_IN } from "./picks.js";
import { currentEngine, searchHref } from "./search.js";
import { fundingLine, likelyFlag, likelyUnflagged, profileLinks, raceMoney, sourceLines } from "./source-cards.js";
import { hideToast, showToast } from "./toast.js";
import { viewPref } from "./view.js";

let page = null; // { ballot, picks, marks, showDetails, openPrecincts, updateProgress, openRules }
const redraw = new Map(); // race or proposition key -> redraws its card from the saved picks

export function initRaceCards(context) {
  page = context;
}

// Builds every card again, blank: redrawCards() then fills them in.
export function renderCards() {
  redraw.clear();
  const sections = ballotSections(page.ballot);
  $("#groups").replaceChildren(...sections.filter((s) => !s.maybe).map((section) =>
    h("section", { class: "group", id: section.id, "aria-labelledby": `${section.id}-title` },
      h("h2", { class: "group-title", id: `${section.id}-title` }, section.title),
      section.races.map(raceCard))));
  $("#maybe").replaceChildren(...sections.filter((s) => s.maybe).map((section) =>
    h("section", { class: "group maybe", id: section.id, "aria-labelledby": `${section.id}-title` },
      h("h2", { class: "group-title", id: `${section.id}-title` }, section.title),
      h("p", { class: "muted explain" }, section.explanation),
      section.kind === "precinct" ? precinctLink() : null,
      section.races.map(raceCard))));
  const { measures } = page.ballot;
  $("#measures").replaceChildren(
    measures.length
      ? h("section", { class: "group", id: "measures-section" }, h("h2", { class: "group-title" }, "Propositions"), measures.map(measureCard))
      : "",
  );
}

export function redrawRace(key) {
  redraw.get(key)?.();
}

// Every card, in place, from the saved picks, notes, write-ins and folding.
export function redrawCards() {
  for (const draw of redraw.values()) draw();
}

export function setAllCollapsed(collapsed) {
  page.picks.setCollapsed([...redraw.keys()], collapsed);
  redrawCards();
}

export function cardFor(key) {
  return $(`#result .race[data-race="${CSS.escape(key)}"]`);
}

// ---- collapsible cards --------------------------------------------------------------

// A card whose heading is a button that shows or hides its body. The heading stays under the
// strip while its card scrolls by. Collapsed, it's one line: the race on the left, the pick
// ("✓ James Talarico") on the right; the pick shows expanded too, once there is one. ✕ Clear,
// next to it, takes the pick back, with Undo. ``tools``: more buttons after it (a race's funnel).
function collapsibleCard(key, { title, meta, body, tools = null }) {
  const bodyId = `body-${slug(key)}`;
  const status = h("span", { class: "race-status" });
  const fold = () => {
    page.picks.setCollapsed(key, !page.picks.isCollapsed(key));
    redrawRace(key);
  };
  const toggle = h("button", { type: "button", class: "race-toggle", "aria-controls": bodyId, on: { click: fold } },
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "race-name" }, title),
    status,
    meta ? h("span", { class: "race-meta" }, meta) : null);
  const clearPick = () => {
    const before = page.picks.picked(key);
    page.picks.set(key, []);
    refresh(key);
    toggle.focus();
    showToast(`Cleared your pick for ${title}.`, {
      label: "Undo",
      run: () => {
        page.picks.set(key, before);
        refresh(key);
      },
    });
  };
  const clear = h("button", { type: "button", class: "icon-btn with-icon clear-pick", hidden: true,
    "aria-label": `Clear your pick for ${title}`, title: "Clear pick", on: { click: clearPick } }, icon("x"), "Clear");
  const bodyElement = h("div", { class: "race-body", id: bodyId }, body);
  const article = h("article", { class: "race", "data-race": key },
    h("header", { class: "race-head" }, h("h3", {}, toggle), clear, tools),
    bodyElement);
  return {
    article,
    show(statusText, done) {
      const collapsed = page.picks.isCollapsed(key);
      article.classList.toggle("collapsed", collapsed);
      article.classList.toggle("has-pick", done);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      bodyElement.hidden = collapsed;
      status.textContent = statusText;
      status.title = statusText;
      status.classList.toggle("done", done);
      clear.hidden = !done;
    },
  };
}

function raceCard(race) {
  const multi = race.seats > 1;
  const meta = [
    multi ? `Vote for up to ${race.seats}` : null,
    race.open_seat ? "Open seat" : null,
    race.unexpired ? "Unexpired term" : null,
    race.election_name && !/general election/i.test(race.election_name) ? race.election_name : null,
    race.source === "ballotpedia" ? "Listed by Ballotpedia" : null,
  ].filter(Boolean);
  const rows = [...race.candidates.map((c) => candidateRow(race, c)), writeInRow(race)];
  const body = h("fieldset", { class: "race-options" },
    h("legend", { class: "sr-only" }, `${race.name}: vote for ${multi ? `up to ${race.seats}` : "1"}`),
    race.candidates.length ? null : h("p", { class: "muted" }, "No candidates listed yet."),
    h("ul", { class: "cands" }, rows.map((r) => r.row)));
  const money = raceMoney(race, () => openCompare($("#compare"), race));
  const notes = (race.notes || []).map((note) => h("p", { class: "fine race-note" },
    `${note.source}: ${note.text}`, note.url ? [" ", extLink(note.url, `More on ${note.source}`)] : null));
  // Pick by rule for this race, when there's a choice to make.
  const ruleButton = race.candidates.length > 1
    ? h("button", { type: "button", class: "icon-btn rule-btn", title: "Pick by rule", "aria-label": `Pick by rule in ${race.name}`,
      on: { click: () => page.openRules(race.key) } }, icon("filter"))
    : null;
  const card = collapsibleCard(race.key, {
    title: race.name, meta: meta.join(" · "), body: [...notes, money, body], tools: ruleButton,
  });

  redraw.set(race.key, () => {
    const picked = page.picks.picked(race.key);
    // Colour the race by its pick's party (neutral when the picks are from different parties).
    const parties = new Set(picked.map((key) => race.candidates.find((c) => c.key === key)?.party || "none"));
    if (parties.size === 1) card.article.dataset.pickParty = [...parties][0];
    else delete card.article.dataset.pickParty;
    const text = picked.length ? pickLabels(race, picked, page.picks, { unnamed: "Write-in (no name yet)" }).join(", ") : "Not picked yet";
    card.show(text, picked.length > 0);
    for (const row of card.article.querySelectorAll(".cand")) {
      const on = picked.includes(row.dataset.cand);
      row.classList.toggle("picked", on);
      const input = row.querySelector(".pick-input");
      input.checked = on;
      if (multi) input.disabled = !on && picked.length >= race.seats;
      const note = row.querySelector(".write-in-note");
      if (note) note.hidden = !on;
    }
    for (const { sync } of rows) sync();
  });
  return card.article;
}

// Puts ``text`` in a box the voter isn't typing in, if it changed (another tab, Clear picks, Undo).
// Returns whether it did.
function syncBox(box, text) {
  if (document.activeElement === box || box.value === text) return false;
  box.value = text;
  return true;
}

export function avatar(candidate, extraClass = null) {
  const src = safeUrl(candidate.photo_url);
  return src
    ? h("img", { class: ["avatar", extraClass], src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
    : h("span", { class: ["avatar", extraClass], "aria-hidden": "true" }, initials(candidate.name));
}

// What to search the web for: the candidate plus the office and place, so common names find the right person.
function searchQuery(race, candidate) {
  const { ballot } = page;
  const { county, state_name: stateName } = ballot.location;
  const terms = [candidate.name, race.name];
  if ((race.group === "county" || race.group === "precinct") && county && !race.name.includes(county)) {
    terms.push(`${county} County`);
  }
  if (stateName && !race.name.includes(stateName)) terms.push(stateName);
  if (ballot.election_date) terms.push(ballot.election_date.slice(0, 4));
  return terms.join(" ");
}

export function searchLink(race, candidate, className, label) {
  return extLink(searchHref(searchQuery(race, candidate)), label, {
    class: className,
    title: `Search ${currentEngine().label} for ${candidate.name}`,
    "aria-label": `Search the web for ${candidate.name} (opens in a new tab)`,
  });
}

// A candidate's row, and ``sync``, which puts its saved note in the note box and its Pick by rule
// mark ("Mark who matches") under the name.
function candidateRow(race, candidate) {
  const multi = race.seats > 1;
  const id = slug(candidate.key);
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id: `pick-${id}`, class: "pick-input",
    on: { change: (event) => choose(race, candidate.key, event.target.checked) } });

  const textarea = h("textarea", { id: `note-${id}-text`, rows: "2", placeholder: "Your thoughts on this candidate…" });
  const saved = h("span", { class: "saved", "aria-live": "polite" });
  const noteBox = h("div", { class: "note", id: `note-${id}`, hidden: true },
    h("label", { for: `note-${id}-text` }, `Your note on ${candidate.name}`), textarea, saved);
  const showNote = (open) => {
    noteBox.hidden = !open;
    noteButton.setAttribute("aria-expanded", String(open));
  };
  const openNote = () => {
    const opening = noteBox.hidden;
    showNote(opening);
    if (opening) textarea.focus();
  };
  const noteButton = h("button", {
    type: "button", class: "icon-btn note-btn", "aria-expanded": "false", "aria-controls": `note-${id}`, on: { click: openNote },
  }, "✎ Note");
  const mark = h("span", { class: "pill rule-mark", hidden: true });
  const syncMark = () => {
    const verdict = page.marks?.get(candidate.key);
    mark.hidden = !verdict;
    if (!verdict) return;
    const skipped = verdict.avoid.length > 0;
    mark.classList.toggle("tone-warn", skipped);
    mark.classList.toggle("tone-good", !skipped);
    mark.textContent = skipped ? `✕ Your rule skips: ${verdict.avoid.join(", ")}` : "✓ Matches your rule";
  };
  // A box opened for a new note stays open until its note changes elsewhere.
  const sync = () => {
    syncMark();
    const text = page.picks.note(candidate.key);
    if (!syncBox(textarea, text)) return;
    noteButton.classList.toggle("has-note", Boolean(text));
    showNote(Boolean(text));
  };
  autosave(textarea, () => {
    page.picks.setNote(candidate.key, textarea.value);
    hideToast(); // an Undo of "Clear picks" would now lose this
    noteButton.classList.toggle("has-note", Boolean(textarea.value.trim()));
    saved.textContent = "Saved";
    setTimeout(() => { saved.textContent = ""; }, 1500);
  }, 400);

  const sources = candidate.cards.length;
  const flag = likelyFlag();
  // The "?" for likely matches with no badge on the row to show it, their lines' too while those are hidden.
  let linesShown = false;
  const flagUnshown = (shown = linesShown) => {
    linesShown = shown;
    const unflagged = likelyUnflagged(candidate, !linesShown);
    flag.hidden = !unflagged.length;
    flag.title = `Likely match: ${unflagged.join(", ")}`;
  };
  flagUnshown(false);
  const lines = sourceLines(candidate, flagUnshown);
  const funding = fundingLine(candidate, () => flagUnshown());
  const detailsButton = h("button", { type: "button", class: "icon-btn", disabled: !sources,
    on: { click: () => page.showDetails(race, race.candidates.indexOf(candidate)) } },
    sources ? `Details · ${plural(sources, "source")}` : "No details", flag);

  const row = h(
    "li",
    { class: "cand", "data-cand": candidate.key, "data-party": candidate.party || null },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: `pick-${id}`, class: "cand-label" },
        avatar(candidate),
        h("span", { class: "cand-text" },
          h("span", { class: "cand-name" }, candidate.name),
          h("span", { class: "cand-sub" }, candidatePills(candidate, race), mark))),
      h("div", { class: "cand-actions" },
        noteButton, detailsButton, searchLink(race, candidate, "icon-btn", "Web search ↗"), profileLinks(candidate))),
    lines,
    funding,
    noteBox,
  );
  return { row, sync };
}

// The last row of every race: a blank for someone who isn't listed. Typing a name picks
// it; emptying the box takes the pick back. ``sync`` puts the saved name in the box.
function writeInRow(race) {
  const multi = race.seats > 1;
  const id = `writein-${slug(race.key)}`;
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id, class: "pick-input" });
  const name = h("input", {
    type: "text", id: `${id}-name`, class: "write-in-name", maxlength: "80", autocomplete: "off",
    placeholder: "Someone else's name", "aria-label": `Write-in name for ${race.name}`,
  });
  input.addEventListener("change", () => {
    choose(race, WRITE_IN, input.checked);
    if (input.checked) name.focus();
  });
  autosave(name, () => {
    const { picks } = page;
    picks.setWriteIn(race.key, name.value);
    const typed = Boolean(name.value.trim());
    const picked = picks.picked(race.key).includes(WRITE_IN);
    const full = multi && !picked && picks.picked(race.key).length >= race.seats;
    if (typed !== picked && !full) choose(race, WRITE_IN, typed);
    else refresh(race.key); // the collapsed line shows the new name
  }, 300);
  const note = STATES[page.ballot.location.state]?.writeInNote;
  const hint = note && race.candidates.some((c) => c.write_in) ? `${note} The ones who filed for this race are listed above.` : note;
  const row = h(
    "li",
    { class: "cand write-in", "data-cand": WRITE_IN },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: id, class: "write-in-label" }, "Write-in"),
      name),
    hint ? h("p", { class: "fine write-in-note", hidden: true }, hint) : null,
  );
  return { row, sync: () => syncBox(name, page.picks.writeIn(race.key)) };
}

// ---- picking ------------------------------------------------------------------------

export function choose(race, key, checked) {
  const { picks } = page;
  let keys = picks.picked(race.key).filter((k) => k !== key);
  if (checked) keys = race.seats > 1 ? [...keys, key] : [key];
  picks.set(race.key, keys);
  // A write-in doesn't fold the race: its name box would go while the voter types.
  settle(race.key, checked && key !== WRITE_IN && keys.length >= race.seats);
}

function refresh(key) {
  hideToast(); // an Undo of "Clear picks" would now lose this change
  redrawRace(key);
  page.updateProgress();
}

// After a pick that fills the race: with "Collapse a race when I pick" (View, on at first), fold the race to
// one line, and bring its heading back into view if that left it above the strip.
function settle(key, filled) {
  const fold = filled && viewPref("collapseOnPick");
  if (fold) page.picks.setCollapsed(key, true);
  refresh(key);
  const card = fold ? cardFor(key) : null;
  if (card && card.getBoundingClientRect().top < $("#progress-strip").getBoundingClientRect().bottom) card.scrollIntoView({ block: "start" });
}

// ---- precincts, propositions --------------------------------------------------------

function precinctLink() {
  return h("p", { class: "precinct-link" },
    h("button", { type: "button", class: "link-btn", on: { click: () => page.openPrecincts() } }, "Enter your commissioner and JP precincts"));
}

function measureCard(measure) {
  const key = measureKey(measure);
  const name = `measure-${slug(measure.key)}`;
  const options = [["for", "For"], ["against", "Against"]].map(([value, label]) => {
    const vote = () => {
      page.picks.set(key, [value]);
      settle(key, true);
    };
    const input = h("input", { type: "radio", name, id: `${name}-${value}`, value, on: { change: vote } });
    return { value, input, label: h("label", { class: "measure-option", for: `${name}-${value}` }, input, label) };
  });
  const body = [
    measure.summary ? h("p", {}, measure.summary) : null,
    h("fieldset", { class: "measure-options" }, h("legend", { class: "sr-only" }, measure.title), options.map((o) => o.label)),
    measure.url ? h("p", { class: "fine" }, extLink(measure.url, "Read more on Ballotpedia")) : null,
  ];
  const card = collapsibleCard(key, { title: measure.title, meta: measure.district, body });
  card.article.classList.add("measure");
  redraw.set(key, () => {
    const vote = page.picks.picked(key)[0];
    for (const option of options) option.input.checked = option.value === vote;
    card.show(vote ? `Voting ${vote}` : "Not decided yet", Boolean(vote));
  });
  return card.article;
}
