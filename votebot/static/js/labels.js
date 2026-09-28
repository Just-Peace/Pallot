import { h } from "./dom.js";

export const GROUP_ORDER = ["federal", "state", "legislature", "judicial", "county", "precinct", "local"];

export const GROUP_LABELS = {
  federal: "Federal",
  state: "Statewide",
  legislature: "Legislature & State Board of Education",
  judicial: "Courts & district offices",
  county: "County",
  precinct: "Your precinct",
  local: "City & school district",
};

// Details that differ by state, keyed by the address's postal code. Only Texas is covered so far.
export const STATES = {
  TX: {
    site: { label: "VoteTexas.gov", url: "https://www.votetexas.gov/" },
    printTips: [
      "Phones can't be used at the voting station in Texas, so bring this sheet.",
      "Texas has no straight-ticket option: vote each race.",
    ],
  },
};

const PARTY_NAMES = { R: "Republican", D: "Democratic", L: "Libertarian", G: "Green", I: "Independent", W: "Write-in" };

export function partyName(candidate) {
  return candidate.party_name || PARTY_NAMES[candidate.party] || "";
}

export function partyPill(candidate) {
  const name = partyName(candidate);
  return name ? h("span", { class: `party party-${candidate.party || "none"}` }, name) : null;
}
