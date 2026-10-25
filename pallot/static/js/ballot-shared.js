// What the ballot page and the print sheet both work out from a ballot: its sections in order,
// the labels of a race's picks, and the election line (long and short).

import { formatDate, ordinal } from "./format.js";
import { GROUP_LABELS, GROUP_ORDER, coverageOf, partyName } from "./labels.js";
import { WRITE_IN } from "./picks.js";

const ELECTION_DAY = { weekday: "long", month: "long", day: "numeric", year: "numeric" };
const SHORT_DAY = { month: "short", day: "numeric" };
const PARTY_LETTERS = new Set(["R", "D", "L", "G"]); // the wallet card's "(D)"; other parties spelled out

// The race sections in ballot order: the groups ("group-federal"), then the sections whose races
// may not be on the ballot ("maybe-precinct", with ``maybe`` and the section's own explanation).
export function ballotSections(ballot) {
  const sections = [];
  const sboe = coverageOf(ballot).districts.includes("sboe");
  for (const group of GROUP_ORDER) {
    const races = ballot.races.filter((r) => r.group === group);
    const title = group === "legislature" && !sboe ? "Legislature" : GROUP_LABELS[group];
    if (races.length) sections.push({ id: `group-${group}`, title, races, maybe: false });
  }
  for (const section of ballot.maybe) {
    sections.push({ ...section, id: `maybe-${section.id}`, kind: section.id, maybe: true });
  }
  return sections;
}

// Whether a pick leaves nothing more to pick in the race, so it may fold: never in a ranked-choice
// race, where the voter may rank more.
export const raceFilled = (race, keys) => !race.ranked_choice && keys.length >= race.seats;

// A label per pick in a race: "Jane Doe (write-in)" for a declared write-in, and the voter's own
// write-in by its typed name, or ``unnamed``. ``party``: "name" adds the candidate's party
// ("John Roe (Democratic)"), "letter" its letter where there's one, for the wallet card. In a
// ranked-choice race each is led by its rank: "1st Jane Doe".
export function pickLabels(race, keys, picks, { unnamed, party = null }) {
  const labels = keys
    .map((key) => {
      if (key === WRITE_IN) return picks.writeInLabel(race.key, unnamed);
      const candidate = race.candidates.find((c) => c.key === key);
      if (!candidate) return null;
      if (candidate.write_in) return `${candidate.name} (write-in)`;
      const named = party === "letter" && PARTY_LETTERS.has(candidate.party) ? candidate.party : partyName(candidate);
      return party && named && named !== "Nonpartisan" ? `${candidate.name} (${named})` : candidate.name;
    })
    .filter(Boolean);
  return race.ranked_choice ? labels.map((label, i) => `${ordinal(i + 1)} ${label}`) : labels;
}

// "November 3, 2026 · 2026 November General Election", under the ballot's heading and on the
// address card; with ``day``, "Election Day: Tuesday, November 3, 2026 · …", on the print sheet.
export function electionLine(ballot, { day = false } = {}) {
  const date = ballot.election_date
    && (day ? `Election Day: ${formatDate(ballot.election_date, ELECTION_DAY)}` : formatDate(ballot.election_date));
  return [date, ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · ");
}

const MONTHS = /\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/gi;

// "Nov 3 · General Election", the election line on a phone, on one line: the date without its
// year, and each election's name without the year and month the date already gives.
export function shortElectionLine(ballot) {
  const names = ballot.elections.map((e) => e.name.replace(/\b\d{4}\b/g, "").replace(MONTHS, "").replace(/\s+/g, " ").trim() || e.name);
  return [ballot.election_date && formatDate(ballot.election_date, SHORT_DAY), names.join(" + ")].filter(Boolean).join(" · ");
}
