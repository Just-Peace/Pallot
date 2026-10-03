// The print-only sheet: the voter's picks in ballot order, to take to the polls. A full
// page, or a wallet card to cut out.

import { h } from "./dom.js";
import { formatDate } from "./format.js";
import { earlyVotingText } from "./key-dates.js";
import { GROUP_LABELS, GROUP_ORDER, STATES, districtLine, partyName } from "./labels.js";
import { WRITE_IN } from "./picks.js";

const ELECTION_DAY = { weekday: "long", month: "long", day: "numeric", year: "numeric" };
const PARTY_LETTERS = new Set(["R", "D", "L", "G"]); // the wallet card's "(D)"; other parties spelled out

// ``short``: parties as one letter where there's one, for the wallet card.
function pickText(race, keys, picks, { short = false } = {}) {
  return keys
    .map((key) => {
      if (key === WRITE_IN) return picks.writeInLabel(race.key, "Write-in: ____________________");
      const candidate = race.candidates.find((c) => c.key === key);
      if (!candidate) return null;
      if (candidate.write_in) return `${candidate.name} (write-in)`;
      const party = short && PARTY_LETTERS.has(candidate.party) ? candidate.party : partyName(candidate);
      return party && party !== "Nonpartisan" ? `${candidate.name} (${party})` : candidate.name;
    })
    .filter(Boolean);
}

function sections(ballot) {
  const out = [];
  for (const group of GROUP_ORDER) {
    const races = ballot.races.filter((r) => r.group === group);
    if (races.length) out.push({ title: GROUP_LABELS[group], races });
  }
  for (const section of ballot.maybe) out.push({ title: section.title, races: section.races, maybe: true });
  return out;
}

// "Election day: Tuesday, November 3, 2026 · <the elections' names>"
function electionLine(ballot) {
  const day = ballot.election_date ? `Election day: ${formatDate(ballot.election_date, ELECTION_DAY)}` : null;
  return [day, ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · ");
}

// "Early voting: Mon, Oct 19 – Fri, Oct 30 · Polls open 7 a.m. – 7 p.m. on Election Day"
function whenLine(ballot) {
  const hours = STATES[ballot.location.state]?.pollHours;
  return [earlyVotingText(ballot), hours && `Polls open ${hours} on Election Day`].filter(Boolean).join(" · ");
}

// The races to print, per section: those picked, and with ``includeBlank`` the rest (except
// the ones that may not be on the ballot).
function printedSections(ballot, picks, includeBlank) {
  return sections(ballot)
    .map((section) => ({
      ...section,
      races: section.races.filter((race) => picks.has(race.key) || (includeBlank && !section.maybe)),
    }))
    .filter((section) => section.races.length);
}

function printedMeasures(ballot, picks, includeBlank) {
  return ballot.measures
    .map((m) => ({ m, vote: picks.picked(`measure:${m.key}`)[0] }))
    .filter(({ vote }) => vote || includeBlank);
}

const voteText = (vote) => (vote === "for" ? "For" : "Against");

// A card about 3.5 inches wide, to cut out along its dashed edge (and fold, if it's long):
// the election day and early voting, then a line per race with the pick. No notes: they
// don't fit.
function walletCard(ballot, picks, includeBlank) {
  const blocks = printedSections(ballot, picks, includeBlank).map(({ title, races }) => [
    h("h2", {}, title),
    races.map((race) => {
      const keys = picks.picked(race.key);
      return h("p", { class: "wallet-line" },
        h("span", { class: "wallet-race" }, race.name, race.unexpired ? " (unexpired)" : "", ": "),
        h("span", { class: keys.length ? "wallet-pick" : "wallet-pick blank" }, keys.length ? pickText(race, keys, picks, { short: true }).join("; ") : ""));
    }),
  ]);
  const measures = printedMeasures(ballot, picks, includeBlank);
  if (measures.length) {
    blocks.push([h("h2", {}, "Propositions"), measures.map(({ m, vote }) => h("p", { class: "wallet-line" },
      h("span", { class: "wallet-race" }, m.title, ": "),
      h("span", { class: vote ? "wallet-pick" : "wallet-pick blank" }, vote ? voteText(vote) : "")))]);
  }
  const early = earlyVotingText(ballot, { short: true });
  return h("div", { class: "wallet-card" },
    h("h1", {}, "My ballot picks"),
    h("p", { class: "wallet-day" }, electionLine(ballot), early ? [h("br"), h("span", { class: "wallet-early" }, early)] : null),
    blocks.length ? blocks : h("p", {}, "No picks yet."),
    h("p", { class: "wallet-foot" }, `Made with VoteBot on ${formatDate(new Date().toISOString())}. Unofficial.`));
}

export function buildPrintSheet(ballot, picks, { includeNotes, includeBlank, wallet = false }) {
  const sheet = document.getElementById("print-sheet");
  if (wallet) {
    sheet.replaceChildren(walletCard(ballot, picks, includeBlank));
    return;
  }
  const headers = ["Race", "My pick", ...(includeNotes ? ["Note"] : [])];
  let rows = 0;

  const tables = printedSections(ballot, picks, includeBlank).map(({ title, races, maybe }) => {
    const body = races.map((race) => {
      const keys = picks.picked(race.key);
      rows += 1;
      const notes = includeNotes ? keys.map((k) => picks.note(k)).filter(Boolean).join(" / ") : "";
      return h(
        "tr",
        {},
        h("td", {}, race.name, race.unexpired ? " (unexpired term)" : ""),
        h("td", { class: keys.length ? "" : "blank" }, keys.length ? pickText(race, keys, picks).join("; ") : ""),
        includeNotes ? h("td", {}, notes) : null,
      );
    });
    return h(
      "section",
      {},
      h("h2", {}, maybe ? `${title} (may not be on your ballot)` : title),
      h("table", { class: includeNotes ? "with-notes" : null },
        h("thead", {}, h("tr", {}, headers.map((t) => h("th", {}, t)))), h("tbody", {}, body)),
    );
  });

  const measures = printedMeasures(ballot, picks, includeBlank)
    .map(({ m, vote }) => h("tr", {}, h("td", {}, m.title), h("td", { class: vote ? "" : "blank" }, vote ? voteText(vote) : "")));
  if (measures.length) {
    rows += measures.length;
    tables.push(h("section", {}, h("h2", {}, "Propositions"), h("table", { class: "measures" }, h("tbody", {}, measures))));
  }

  const state = STATES[ballot.location.state];
  const tips = state?.printTips ?? ["Bring this sheet with you: many polling places don't allow phones in the voting booth."];
  const districts = districtLine(ballot.districts, { precinct: " Pct" });
  const when = whenLine(ballot);

  sheet.replaceChildren(
    h("header", {},
      h("h1", {}, "My ballot picks"),
      h("p", { class: "election-day" }, electionLine(ballot)),
      when ? h("p", {}, when) : null,
      h("p", {}, ballot.location.matched_address || ballot.location.input_address),
      districts ? h("p", { class: "small" }, districts) : null),
    ...(rows ? tables : [h("p", {}, "No picks yet. Pick candidates on the ballot page, then print again.")]),
    h("footer", {},
      h("p", {}, tips.join(" ")),
      h("p", { class: "small" }, `Made with VoteBot on ${formatDate(new Date().toISOString())}. Unofficial: check your county's `
        + `official sample ballot${state ? ` or ${state.site.label}` : ""}.`)),
  );
}
