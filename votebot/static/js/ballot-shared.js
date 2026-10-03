// What the ballot page and the print sheet both work out from a ballot: its sections in order,
// a proposition's pick key, the labels of a race's picks, and the election line.

import { formatDate } from "./format.js";
import { GROUP_LABELS, GROUP_ORDER, partyName } from "./labels.js";
import { WRITE_IN } from "./picks.js";

const ELECTION_DAY = { weekday: "long", month: "long", day: "numeric", year: "numeric" };
const PARTY_LETTERS = new Set(["R", "D", "L", "G"]); // the wallet card's "(D)"; other parties spelled out

// The race sections in ballot order: the groups ("group-federal"), then the sections whose races
// may not be on the ballot ("maybe-precinct", with ``maybe`` and the section's own explanation).
// Propositions aren't among them.
export function ballotSections(ballot) {
  const sections = [];
  for (const group of GROUP_ORDER) {
    const races = ballot.races.filter((r) => r.group === group);
    if (races.length) sections.push({ id: `group-${group}`, title: GROUP_LABELS[group], races, maybe: false });
  }
  for (const section of ballot.maybe) {
    sections.push({ ...section, id: `maybe-${section.id}`, kind: section.id, maybe: true });
  }
  return sections;
}

export const measureKey = (measure) => `measure:${measure.key}`;

// A label per pick in a race: "Jane Doe (write-in)" for a declared write-in, and the voter's own
// write-in by its typed name, or ``unnamed``. ``party``: "name" adds the candidate's party
// ("John Roe (Democratic)"), "letter" its letter where there's one, for the wallet card.
export function pickLabels(race, keys, picks, { unnamed, party = null }) {
  return keys
    .map((key) => {
      if (key === WRITE_IN) return picks.writeInLabel(race.key, unnamed);
      const candidate = race.candidates.find((c) => c.key === key);
      if (!candidate) return null;
      if (candidate.write_in) return `${candidate.name} (write-in)`;
      const named = party === "letter" && PARTY_LETTERS.has(candidate.party) ? candidate.party : partyName(candidate);
      return party && named && named !== "Nonpartisan" ? `${candidate.name} (${named})` : candidate.name;
    })
    .filter(Boolean);
}

// "November 3, 2026 · 2026 November General Election", under the ballot's heading and on the
// address card; with ``day``, "Election day: Tuesday, November 3, 2026 · …", on the print sheet.
export function electionLine(ballot, { day = false } = {}) {
  const date = ballot.election_date
    && (day ? `Election day: ${formatDate(ballot.election_date, ELECTION_DAY)}` : formatDate(ballot.election_date));
  return [date, ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · ");
}
