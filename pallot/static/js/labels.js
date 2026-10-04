import { h } from "./dom.js";

export const GROUP_ORDER = ["federal", "state", "legislature", "judicial", "county", "precinct", "local"];

export const GROUP_LABELS = {
  federal: "Federal",
  state: "Statewide",
  legislature: "Legislature & State Board of Education",
  judicial: "Courts & district offices",
  county: "County",
  precinct: "Your commissioner & JP precincts",
  local: "City & school district",
};

// Details that differ by state, keyed by the address's postal code. Only Texas is covered so far.
export const STATES = {
  TX: {
    site: { label: "VoteTexas.gov", url: "https://www.votetexas.gov/" },
    // My Voter Portal: a login with name and date of birth, which also shows the voter's polling place
    registration: {
      label: "Am I registered?", url: "https://goelect.txelections.civixapps.com/ivis-mvp-ui/#/login",
      hint: "My Voter Portal (Texas SOS): your registration, and your polling place once you log in",
    },
    countyOffices: {
      label: "Where to vote", url: "https://www.votetexas.gov/voting/where.html",
      hint: "Every county's elections office (Texas SOS); yours publishes where and when you can vote",
    },
    mailApply: { label: "How to apply", url: "https://www.sos.state.tx.us/elections/voter/reqabbm.shtml" },
    mailEligibility: "Only if you're 65 or older, sick or disabled, away from your county for all of early voting and "
      + "Election Day, expecting to give birth around Election Day, or in jail but still eligible to vote.",
    pollHours: "7 a.m. – 7 p.m.",
    districtCounts: { cd: 38, sd: 31, hd: 150, sboe: 15, commissioner: 4, jp: 99 }, // the highest number of each
    writeInNote: "In Texas, a write-in vote only counts for someone who filed as a write-in candidate.",
    printTips: [
      "Phones can't be used at the voting station in Texas, so bring this sheet.",
      "Texas has no straight-ticket option: vote each race.",
    ],
  },
};

// The districts and precincts the voter can see and change, in the voter registration
// certificate's order: ``short`` on the card, the map's buttons and the print sheet, ``long``
// spelled out ("State Board of Education District 5"), and whether it's a district or a precinct.
export const DISTRICTS = {
  cd: { short: "U.S. House", long: "U.S. House", unit: "district" },
  sd: { short: "State Senate", long: "State Senate", unit: "district" },
  hd: { short: "State House", long: "State House", unit: "district" },
  sboe: { short: "SBOE", long: "State Board of Education", unit: "district" },
  commissioner: { short: "Commissioner", long: "Commissioner", unit: "precinct" },
  jp: { short: "JP", long: "Justice of the Peace", unit: "precinct" },
};
export const PRECINCT_KINDS = Object.keys(DISTRICTS).filter((kind) => DISTRICTS[kind].unit === "precinct");

// The voter's districts in one line: "U.S. House 10 · State Senate 14 · … · Pct 300 · JP 5", in
// the voter registration certificate's order (the print sheet passes precinct: " Pct" for "JP Pct 5").
export function districtLine(d, { precinct = "" } = {}) {
  const named = (kind) => d[kind] && `${DISTRICTS[kind].short}${DISTRICTS[kind].unit === "precinct" ? precinct : ""} ${d[kind]}`;
  return [
    named("cd"), named("sd"), named("hd"), named("sboe"),
    d.election_precinct && `Pct ${d.election_precinct.name}`,
    named("commissioner"), named("jp"), d.constable && `Constable${precinct} ${d.constable}`,
  ].filter(Boolean).join(" · ");
}

const PARTY_NAMES = { R: "Republican", D: "Democratic", L: "Libertarian", G: "Green", I: "Independent" };

export function partyName(candidate) {
  return candidate.party_name || PARTY_NAMES[candidate.party] || "";
}

// The pills under a candidate's name: their party, Incumbent, Write-in.
export function candidatePills(candidate) {
  const party = partyName(candidate);
  return [
    party ? h("span", { class: ["party", `party-${candidate.party || "none"}`] }, party) : null,
    candidate.incumbent ? h("span", { class: "pill" }, "Incumbent") : null,
    candidate.write_in ? h("span", { class: "pill" }, "Write-in") : null,
  ];
}
