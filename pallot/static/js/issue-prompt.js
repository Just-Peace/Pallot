// The question the Issues tab (stances.js) sends: for an AI assistant, a prompt naming the seat, each
// candidate's party and the chosen issues, with a table when it compares; for a search engine, keywords.

import { partyName } from "./labels.js";

const ASK = "Cite sources for every position, say when one is unclear, and show more than one view. "
  + "Where a candidate has no stance of their own on an issue, give their party's and say it's the party's. Keep it neutral.";

// ``where`` is { office, place: [county, state], year }: "for Governor in Texas in the 2026 election".
function seatWords({ office, place, year }) {
  return [`for ${office}`, place.length && `in ${place.join(", ")}`, year && `in the ${year} election`].filter(Boolean).join(" ");
}

// "Jane Doe, the Democratic candidate (incumbent)": "the" when no one else in the race has their
// party, as in a general election, "a" when others do, as in a primary.
function who(candidate, race) {
  const party = partyName(candidate);
  const rivals = party ? race.candidates.filter((other) => partyName(other) === party).length : 0;
  const notes = [candidate.incumbent && "incumbent", candidate.write_in && "write-in"].filter(Boolean);
  return [candidate.name, party && `${rivals > 1 ? "a" : "the"} ${party} candidate`].filter(Boolean).join(", ")
    + (notes.length ? ` (${notes.join(", ")})` : "");
}

// ``candidates`` are the shown one first, then those it's compared with; ``topics`` the chosen
// issues ({ label, terms }), numbered, none meaning the main issues. A search engine gets the first
// candidate only.
export function issuePrompt(race, where, candidates, topics, ai) {
  if (!ai) {
    const terms = topics.length ? ["position on", ...topics.map((topic) => topic.terms)] : ["positions"];
    return [candidates[0].name, where.office, ...where.place, where.year, ...terms].filter(Boolean).join(" ");
  }
  const seat = seatWords(where);
  const on = topics.length ? "on these issues" : "on the main issues in this race";
  const issues = topics.length ? ["", ...topics.map((topic, i) => `${i + 1}. ${topic.label}`)] : [];
  const rows = topics.length ? "one row per issue" : "one row per main issue";
  const lines = candidates.length === 1
    ? [`Where does ${who(candidates[0], race)}, running ${seat}, stand ${on}?`, ...issues, "", ASK]
    : [
      `Compare where these candidates ${seat} stand ${on}.`,
      "",
      "Candidates:",
      ...candidates.map((candidate) => `- ${who(candidate, race)}`),
      ...(topics.length ? ["", "Issues:", ...issues.slice(1)] : []),
      "",
      `Show a table with ${rows} and one column per candidate, then a short summary of each. ${ASK}`,
    ];
  return lines.join("\n");
}
