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
import { badgeList, likelyFlag, likelyUnflagged, raceMoney } from "./source-cards.js";
import { uiPref } from "./storage.js";
import { hideToast, showToast } from "./toast.js";

let page = null; // { ballot, picks, showDetails, openPrecincts, updateProgress }
const redraw = new Map(); // race or proposition key -> redraws its card from the saved picks

export function initRaceCards(context) {
  page = context;
}

// Builds every card again, from the saved picks, notes and write-ins.
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

export function setAllCollapsed(collapsed) {
  page.picks.setCollapsed([...redraw.keys()], collapsed);
  for (const draw of redraw.values()) draw();
}

export function cardFor(key) {
  return $(`#result .race[data-race="${CSS.escape(key)}"]`);
}

// ---- collapsible cards --------------------------------------------------------------

// A card whose heading is a button that shows or hides its body. The heading stays under the
// strip while its card scrolls by. Collapsed, it's one line: the race on the left, the pick
// ("✓ James Talarico") on the right; the pick shows expanded too, once there is one. ✕ Clear,
// next to it, takes the pick back, with Undo.
function collapsibleCard(key, { title, meta, body }) {
  const { picks } = page;
  const bodyId = `body-${slug(key)}`;
  const status = h("span", { class: "race-status" });
  const fold = () => {
    picks.setCollapsed(key, !picks.isCollapsed(key));
    redrawRace(key);
  };
  const toggle = h("button", { type: "button", class: "race-toggle", "aria-controls": bodyId, on: { click: fold } },
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "race-name" }, title),
    status,
    meta ? h("span", { class: "race-meta" }, meta) : null);
  const clearPick = () => {
    const before = picks.picked(key);
    picks.set(key, []);
    refresh(key);
    toggle.focus();
    showToast(`Cleared your pick for ${title}.`, {
      label: "Undo",
      run: () => {
        picks.set(key, before);
        refresh(key);
      },
    });
  };
  const clear = h("button", { type: "button", class: "icon-btn with-icon clear-pick", hidden: true,
    "aria-label": `Clear your pick for ${title}`, title: "Clear pick", on: { click: clearPick } }, icon("x"), "Clear");
  const bodyElement = h("div", { class: "race-body", id: bodyId }, body);
  const article = h("article", { class: "race", "data-race": key },
    h("header", { class: "race-head" }, h("h3", {}, toggle), clear),
    bodyElement);
  return {
    article,
    show(statusText, done) {
      const collapsed = picks.isCollapsed(key);
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
    race.unexpired ? "Unexpired term" : null,
    race.election_name && !/general election/i.test(race.election_name) ? race.election_name : null,
    race.source === "ballotpedia" ? "Listed by Ballotpedia" : null,
  ].filter(Boolean);
  const body = h("fieldset", { class: "race-options" },
    h("legend", { class: "sr-only" }, `${race.name}: vote for ${multi ? `up to ${race.seats}` : "1"}`),
    race.candidates.length ? null : h("p", { class: "muted" }, "No candidates listed yet."),
    h("ul", { class: "cands" }, race.candidates.map((c) => candidateRow(race, c)), writeInRow(race)));
  const money = raceMoney(race, () => openCompare($("#compare"), race));
  const notes = (race.notes || []).map((note) => h("p", { class: "fine race-note" },
    `${note.source}: ${note.text}`, note.url ? [" ", extLink(note.url, `More on ${note.source}`)] : null));
  const card = collapsibleCard(race.key, {
    title: race.name, meta: meta.join(" · "), body: [...notes, money, body],
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
  });
  redrawRace(race.key);
  return card.article;
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

function candidateRow(race, candidate) {
  const { picks } = page;
  const multi = race.seats > 1;
  const id = slug(candidate.key);
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id: `pick-${id}`, class: "pick-input",
    on: { change: (event) => choose(race, candidate.key, event.target.checked) } });

  const noteText = picks.note(candidate.key);
  const textarea = h("textarea", { id: `note-${id}-text`, rows: "2", placeholder: "Your thoughts on this candidate…" });
  textarea.value = noteText;
  const saved = h("span", { class: "saved", "aria-live": "polite" });
  const noteBox = h("div", { class: "note", id: `note-${id}`, hidden: !noteText },
    h("label", { for: `note-${id}-text` }, `Your note on ${candidate.name}`), textarea, saved);
  const openNote = () => {
    const opening = noteBox.hidden;
    noteBox.hidden = !opening;
    noteButton.setAttribute("aria-expanded", String(opening));
    if (opening) textarea.focus();
  };
  const noteButton = h("button", {
    type: "button", class: ["icon-btn note-btn", noteText && "has-note"],
    "aria-expanded": String(Boolean(noteText)), "aria-controls": `note-${id}`, on: { click: openNote },
  }, "✎ Note");
  autosave(textarea, () => {
    picks.setNote(candidate.key, textarea.value);
    hideToast(); // an Undo of "Clear picks" would now lose this
    noteButton.classList.toggle("has-note", Boolean(textarea.value.trim()));
    saved.textContent = "Saved";
    setTimeout(() => { saved.textContent = ""; }, 1500);
  }, 400);

  const sources = candidate.cards.length;
  const unflagged = likelyUnflagged(candidate); // likely matches with no badge to show the "?"
  const detailsButton = h("button", { type: "button", class: "icon-btn", disabled: !sources,
    on: { click: () => page.showDetails(race, race.candidates.indexOf(candidate)) } },
    sources ? `Details · ${plural(sources, "source")}` : "No details",
    unflagged.length ? likelyFlag(`Likely match: ${unflagged.join(", ")}`) : null);

  return h(
    "li",
    { class: "cand", "data-cand": candidate.key, "data-party": candidate.party || null },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: `pick-${id}`, class: "cand-label" },
        avatar(candidate),
        h("span", { class: "cand-text" },
          h("span", { class: "cand-name" }, candidate.name),
          h("span", { class: "cand-sub" }, candidatePills(candidate)))),
      h("div", { class: "cand-actions" }, noteButton, detailsButton, searchLink(race, candidate, "icon-btn", "Web search ↗"))),
    badgeList(candidate),
    noteBox,
  );
}

// The last row of every race: a blank for someone who isn't listed. Typing a name picks
// it; emptying the box takes the pick back.
function writeInRow(race) {
  const { picks } = page;
  const multi = race.seats > 1;
  const id = `writein-${slug(race.key)}`;
  const input = h("input", { type: multi ? "checkbox" : "radio", name: `race-${slug(race.key)}`, id, class: "pick-input" });
  const name = h("input", {
    type: "text", id: `${id}-name`, class: "write-in-name", maxlength: "80", autocomplete: "off",
    placeholder: "Someone else's name", "aria-label": `Write-in name for ${race.name}`,
  });
  name.value = picks.writeIn(race.key);
  input.addEventListener("change", () => {
    choose(race, WRITE_IN, input.checked);
    if (input.checked) name.focus();
  });
  autosave(name, () => {
    picks.setWriteIn(race.key, name.value);
    const typed = Boolean(name.value.trim());
    const picked = picks.picked(race.key).includes(WRITE_IN);
    const full = multi && !picked && picks.picked(race.key).length >= race.seats;
    if (typed !== picked && !full) choose(race, WRITE_IN, typed);
    else refresh(race.key); // the collapsed line shows the new name
  }, 300);
  const note = STATES[page.ballot.location.state]?.writeInNote;
  const hint = note && race.candidates.some((c) => c.write_in) ? `${note} The ones who filed for this race are listed above.` : note;
  return h(
    "li",
    { class: "cand write-in", "data-cand": WRITE_IN },
    h("div", { class: "cand-main" },
      input,
      h("label", { for: id, class: "write-in-label" }, "Write-in"),
      name),
    hint ? h("p", { class: "fine write-in-note", hidden: true }, hint) : null,
  );
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

// After a pick that fills the race: with "Collapse a race when I pick" (View), fold the race to
// one line, and bring its heading back into view if that left it above the strip.
function settle(key, filled) {
  const fold = filled && uiPref("collapseOnPick");
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
  redrawRace(key);
  return card.article;
}
