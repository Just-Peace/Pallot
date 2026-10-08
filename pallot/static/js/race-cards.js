// The ballot's race and proposition cards: the groups, the sections that may not be on the
// ballot, and the propositions, each card collapsible, with its candidates, notes and write-in.
// Picking here saves to ``page.picks``; ballot.js hands over the context (initRaceCards).

import { ballotSections, measureKey, pickLabels } from "./ballot-shared.js";
import { banName, isBanned, restoreBans, unbanName } from "./ban-list.js";
import { openCompare } from "./compare.js";
import { $, autosave, extLink, h, initials, safeUrl, slug } from "./dom.js";
import { plural } from "./format.js";
import { icon } from "./icons.js";
import { STATES, candidatePills } from "./labels.js";
import { WRITE_IN } from "./picks.js";
import { searchHref, searchTitle, searchWord } from "./search.js";
import { fundingLine, raceMoney, sourceLines } from "./source-cards.js";
import { hideToast, showToast } from "./toast.js";
import { viewPref } from "./view.js";

let page = null; // { ballot, picks, loadingCards, showDetails, openPrecincts, updateProgress, openRules }
const redraw = new Map(); // race or proposition key -> redraws its card from the saved picks
const fills = new Map(); // race key -> builds what its cards make again, in place

export const STILL_LOADING = "Available once everything has loaded";

export function initRaceCards(context) {
  page = context;
}

// Builds every card again, blank: redrawCards() then fills them in.
export function renderCards() {
  redraw.clear();
  fills.clear();
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

// Every race's money and poll boxes, open seat and candidates' card parts, from the cards now in
// ``page.ballot``; the picks, notes and folding stay as they are.
export function refillCards() {
  for (const fill of fills.values()) fill();
  for (const button of document.querySelectorAll("#result .rule-btn")) {
    button.disabled = page.loadingCards;
    button.title = page.loadingCards ? STILL_LOADING : "Pick by rule";
  }
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
  const metaLine = h("span", { class: "race-meta", hidden: !meta }, meta);
  const fold = () => {
    page.picks.setCollapsed(key, !page.picks.isCollapsed(key));
    redrawRace(key);
  };
  const toggle = h("button", { type: "button", class: "race-toggle", "aria-controls": bodyId, on: { click: fold } },
    h("span", { class: "chevron", "aria-hidden": "true" }),
    h("span", { class: "race-name" }, title),
    status,
    metaLine);
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
    setMeta(text) {
      metaLine.textContent = text;
      metaLine.hidden = !text;
    },
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
  const meta = () => [
    multi ? `Vote for up to ${race.seats}` : null,
    race.open_seat ? "Open seat" : null,
    race.unexpired ? "Unexpired term" : null,
    race.election_name && !/general election/i.test(race.election_name) ? race.election_name : null,
    race.source === "ballotpedia" ? "Listed by Ballotpedia" : null,
  ].filter(Boolean).join(" · ");
  const rows = [...race.candidates.map((c) => candidateRow(race, c)), writeInRow(race)];
  const body = h("fieldset", { class: "race-options" },
    h("legend", { class: "sr-only" }, `${race.name}: vote for ${multi ? `up to ${race.seats}` : "1"}`),
    race.candidates.length ? null : h("p", { class: "muted" }, "No candidates listed yet."),
    h("ul", { class: "cands" }, rows.map((r) => r.row)));
  const money = part(() => raceMoney(race, () => openCompare($("#compare"), race)));
  const notes = (race.notes || []).map((note) => h("p", { class: "fine race-note" },
    `${note.source}: ${note.text}`, note.url ? [" ", extLink(note.url, `More on ${note.source}`)] : null));
  // Pick by rule for this race, when there's a choice to make (once the cards it decides by are in).
  const ruleButton = race.candidates.length > 1
    ? h("button", { type: "button", class: "icon-btn rule-btn", title: page.loadingCards ? STILL_LOADING : "Pick by rule",
      "aria-label": `Pick by rule in ${race.name}`, disabled: page.loadingCards,
      on: { click: () => page.openRules(race.key) } }, icon("filter"))
    : null;
  const card = collapsibleCard(race.key, {
    title: race.name, meta: meta(), body: [...notes, money.nodes, body], tools: ruleButton,
  });
  fills.set(race.key, () => {
    card.setMeta(meta());
    money.refill();
    for (const row of rows) row.fill?.();
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
export function candidateQuery(race, candidate) {
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
  return extLink(searchHref(candidateQuery(race, candidate)), label, {
    class: className,
    title: searchTitle(candidate.name),
    "aria-label": `${searchTitle(candidate.name)} (opens in a new tab)`,
  });
}

// Ban adds the candidate's name to the ban list (ban-list.js) as plain text; Unban takes off every
// entry that matches them, a pattern typed in Settings included. Either offers Undo, then refills
// the ballot's rows and runs ``after`` (Details' head).
export function toggleBan(candidate, after = null) {
  const changed = () => {
    refillCards();
    after?.();
  };
  if (!isBanned(candidate)) {
    if (banName(candidate.name)) {
      showToast(`${candidate.name} is on your ban list.`, { label: "Undo", run: () => { unbanName(candidate.name); changed(); } });
    } else {
      showToast("This browser didn't let Pallot save your ban list.");
    }
    changed();
    return;
  }
  const removed = unbanName(candidate.name);
  const patterns = removed.filter((entry) => entry.text.toLowerCase() !== candidate.name.toLowerCase());
  showToast(patterns.length
    ? `Removed ${patterns.map((entry) => `“${entry.text}”`).join(", ")} from your ban list, which may unban others too.`
    : `${candidate.name} is off your ban list.`,
  { label: "Undo", run: () => { restoreBans(removed); changed(); } });
  changed();
}

// The row's Ban (Unban once banned), beside Note and Search.
function banButton(candidate) {
  const on = isBanned(candidate);
  const name = on ? `Take ${candidate.name} off your ban list` : `Add ${candidate.name} to your ban list`;
  return h("button", { type: "button", class: ["icon-btn ban-btn with-icon", on && "is-banned"], title: name, "aria-label": name,
    on: { click: () => {
      toggleBan(candidate);
      $(`#result .cand[data-cand="${CSS.escape(candidate.key)}"] .ban-btn`)?.focus(); // the refill drew a new one
    } } }, icon("ban"), on ? "Unban" : "Ban");
}

// A candidate's row, and ``sync``, which puts its saved note in the note box.
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
  // A box opened for a new note stays open until its note changes elsewhere.
  const sync = () => {
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

  const index = () => race.candidates.indexOf(candidate);
  const openAt = (card) => page.showDetails(race, index(), null, card.source);
  const profileButton = () => {
    const sources = candidate.cards.length;
    const waiting = page.loadingCards;
    return h("button", { type: "button", class: "icon-btn profile-btn", disabled: waiting,
      title: waiting ? STILL_LOADING : `${candidate.name}'s profile: ${sources ? `${plural(sources, "source")} and issues` : "issues"}`,
      on: { click: () => page.showDetails(race, index()) } },
      "Profile");
  };
  // What the cards make, in the order fill() builds it again.
  const profile = part(profileButton);
  const photo = part(() => avatar(candidate));
  const pills = part(() => candidatePills(candidate, race));
  const lines = part(() => sourceLines(candidate));
  const funding = part(() => fundingLine(candidate, openAt));
  const ban = part(() => banButton(candidate));
  const fill = () => {
    [profile, photo, pills, lines, funding, ban].forEach((p) => p.refill());
    row.classList.toggle("banned", isBanned(candidate));
  };

  const row = h(
    "li",
    { class: "cand", "data-cand": candidate.key, "data-party": candidate.party || null },
    // The name with its pills beside it, Profile under them (outside the label, so it doesn't pick),
    // and Note and Search to the side (beside Profile, on a phone).
    h("div", { class: "cand-main cand-grid" },
      input,
      h("label", { for: `pick-${id}`, class: "cand-label" },
        photo.nodes,
        h("span", { class: "cand-text" },
          h("span", { class: "cand-name" }, candidate.name),
          h("span", { class: "cand-sub" }, pills.nodes))),
      h("div", { class: "cand-profile" }, profile.nodes),
      h("div", { class: "cand-actions" },
        noteButton, ban.nodes, searchLink(race, candidate, "icon-btn", `${searchWord()} ↗`))),
    lines.nodes,
    funding.nodes,
    noteBox,
  );
  row.classList.toggle("banned", isBanned(candidate));
  return { row, sync, fill };
}

// What ``build()`` makes (a node, a list of them or nothing), behind a marker so ``refill()`` can
// build it again in the same place, leaving the rest of the card (a note being typed) alone.
function part(build) {
  const marker = document.createComment("");
  const make = () => [build()].flat(Infinity).filter(Boolean);
  let nodes = make();
  return {
    nodes: [marker, ...nodes],
    refill() {
      for (const node of nodes) node.remove();
      nodes = make();
      marker.after(...nodes);
    },
  };
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

// After a pick that fills the race: with "Collapse a race when I pick" (Options, on at first), fold the race to
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
