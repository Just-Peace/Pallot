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
    // My Voter Portal: a login with name and date of birth, which also shows the voter's polling place
    registration: { label: "Am I registered?", url: "https://goelect.txelections.civixapps.com/ivis-mvp-ui/#/login" },
    countyOffices: { label: "county elections offices", url: "https://www.sos.state.tx.us/elections/voter/county.shtml" },
    mailApply: { label: "How to apply", url: "https://www.sos.state.tx.us/elections/voter/reqabbm.shtml" },
    mailEligibility: "Only if you're 65 or older, sick or disabled, away from your county for all of early voting and "
      + "Election Day, expecting to give birth around Election Day, or in jail but still eligible to vote.",
    pollHours: "7 a.m. – 7 p.m.",
    writeInNote: "In Texas, a write-in vote only counts for someone who filed as a write-in candidate.",
    printTips: [
      "Phones can't be used at the voting station in Texas, so bring this sheet.",
      "Texas has no straight-ticket option: vote each race.",
    ],
  },
};

// The voter's districts in one line: "U.S. House 10 · State Senate 14 · … · JP 5" (the
// print sheet passes precinct: " Pct" for "JP Pct 5").
export function districtLine(d, { precinct = "" } = {}) {
  return [
    d.cd && `U.S. House ${d.cd}`, d.sd && `State Senate ${d.sd}`, d.hd && `State House ${d.hd}`, d.sboe && `SBOE ${d.sboe}`,
    d.commissioner && `Commissioner${precinct} ${d.commissioner}`, d.jp && `JP${precinct} ${d.jp}`,
    d.constable && `Constable${precinct} ${d.constable}`,
  ].filter(Boolean).join(" · ");
}

const PARTY_NAMES = { R: "Republican", D: "Democratic", L: "Libertarian", G: "Green", I: "Independent", W: "Write-in" };

export function partyName(candidate) {
  return candidate.party_name || PARTY_NAMES[candidate.party] || "";
}

export function partyPill(candidate) {
  const name = partyName(candidate);
  return name ? h("span", { class: `party party-${candidate.party || "none"}` }, name) : null;
}
