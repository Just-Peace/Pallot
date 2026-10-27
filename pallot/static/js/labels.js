import { banMatches } from "./ban-list.js";
import { h } from "./dom.js";
import { noteButton } from "./help.js";
import { icon } from "./icons.js";

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

// The state's election office, where its registration, key dates and polling places are: every
// state's site, and Texas's details besides.
const SITES = {
  AL: "https://www.sos.alabama.gov/alabama-votes", AK: "https://www.elections.alaska.gov/",
  AZ: "https://azsos.gov/elections", AR: "https://www.sos.arkansas.gov/elections",
  CA: "https://www.sos.ca.gov/elections", CO: "https://www.coloradosos.gov/pubs/elections/main.html",
  CT: "https://portal.ct.gov/sots", DE: "https://elections.delaware.gov/", DC: "https://www.dcboe.org/",
  FL: "https://dos.fl.gov/elections/", GA: "https://sos.ga.gov/elections", HI: "https://elections.hawaii.gov/",
  ID: "https://voteidaho.gov/", IL: "https://www.elections.il.gov/", IN: "https://www.in.gov/sos/elections/",
  IA: "https://sos.iowa.gov/elections-voting", KS: "https://www.sos.ks.gov/elections/elections.html",
  KY: "https://elect.ky.gov/", LA: "https://www.sos.la.gov/elections-voting", ME: "https://www.maine.gov/sos/elections-voting",
  MD: "https://elections.maryland.gov/", MA: "https://www.sec.state.ma.us/divisions/elections/",
  MI: "https://www.michigan.gov/sos/elections", MN: "https://www.sos.mn.gov/elections-voting/",
  MS: "https://www.sos.ms.gov/elections-voting", MO: "https://www.sos.mo.gov/elections", MT: "https://sosmt.gov/elections/",
  NE: "https://sos.nebraska.gov/elections", NV: "https://www.nvsos.gov/sos/elections", NH: "https://www.sos.nh.gov/elections",
  NJ: "https://www.nj.gov/state/elections/", NM: "https://www.sos.nm.gov/voting-and-elections/",
  NY: "https://elections.ny.gov/", NC: "https://www.ncsbe.gov/", ND: "https://www.sos.nd.gov/elections",
  OH: "https://www.ohiosos.gov/elections/", OK: "https://oklahoma.gov/elections.html",
  OR: "https://sos.oregon.gov/elections/", PA: "https://www.pa.gov/agencies/vote", RI: "https://vote.sos.ri.gov/",
  SC: "https://scvotes.gov/", SD: "https://sdsos.gov/elections-voting/", TN: "https://sos.tn.gov/elections",
  UT: "https://vote.utah.gov/", VT: "https://sos.vermont.gov/elections/", VA: "https://www.elections.virginia.gov/",
  WA: "https://www.sos.wa.gov/elections", WV: "https://sos.wv.gov/elections", WI: "https://elections.wi.gov/",
  WY: "https://sos.wyo.gov/Elections/",
};
const siteLabel = (url) => new URL(url).hostname.replace(/^www\./, "");

// Details that differ by state, keyed by the address's postal code: every state's election
// office (``site``), and Texas's phones, district counts, write-ins and print tips. Registration,
// where to vote, mail voting and poll hours come with the ballot (stateInfo).
export const STATES = {
  ...Object.fromEntries(Object.entries(SITES).map(([state, url]) => [state, { site: { label: siteLabel(url), url } }])),
  TX: {
    site: { label: "VoteTexas.gov", url: "https://www.votetexas.gov/" },
    noPhones: true, // phones can't be used at the voting station
    districtCounts: { cd: 38, sd: 31, hd: 150, sboe: 15, commissioner: 4, jp: 99 }, // the highest number of each
    writeInNote: "In Texas, a write-in vote only counts for someone who filed as a write-in candidate.",
    printTips: [
      "Phones can't be used at the voting station in Texas, so bring this sheet.",
      "Texas has no straight-ticket option: vote each race.",
    ],
  },
};

// The voter's state's details: STATES' own, with how to register, where to vote, mail voting and
// poll hours as the ballot gives them (``voter_info``, for the states Pallot knows them for).
export function stateInfo(ballot) {
  const base = STATES[ballot.location.state];
  const info = ballot.voter_info;
  if (!info) return base;
  return {
    ...base,
    registration: info.registration,
    countyOffices: info.county_offices,
    localOffice: info.local_office,
    mailApply: info.mail_apply,
    mailEligibility: info.mail_eligibility,
    mailDeadline: info.mail_deadline,
    pollHours: info.poll_hours,
    lateRegistration: info.late_registration,
  };
}

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

// How much of the voter's state's ballot Pallot has, as the server says (coverage.py): which
// districts it shows, whether there are precincts and a map, and whether the races come from the
// state's own list ("state") or the FEC's filers ("fec"). A ballot from before it said is Texas's.
const FULL_COVERAGE = { ballot: "state", districts: ["cd", "sd", "hd", "sboe"], precincts: true, outlines: true };
export function coverageOf(ballot) {
  return ballot?.coverage || FULL_COVERAGE;
}

// A U.S. House district's number as said: "10", or "at large" for a state's one seat (0), DC's delegate's too.
export function houseText(number, state) {
  if (number == null) return null;
  if (number !== 0) return String(number);
  return state === "DC" ? "Delegate (at large)" : "At large";
}

// A district kind's name: the state's own for its chamber where the coverage gives one
// (``labels``: California's "State Assembly"), else DISTRICTS' ``size`` ("short" or "long").
export function districtName(kind, labels = null, size = "short") {
  return labels?.[kind] || DISTRICTS[kind][size];
}

// The voter's districts in one line: "U.S. House 10 · State Senate 14 · … · Pct 300 · JP 5", in
// the voter registration certificate's order (the print sheet passes precinct: " Pct" for "JP Pct 5").
export function districtLine(d, { precinct = "", state = null, labels = null } = {}) {
  const value = (kind) => (kind === "cd" ? houseText(d.cd, state) : d[kind]);
  const named = (kind) => value(kind) != null && value(kind) !== ""
    && `${districtName(kind, labels)}${DISTRICTS[kind].unit === "precinct" ? precinct : ""} ${value(kind)}`;
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

// A pill whose words need a reason: a click or a tap shows ``why`` in a note (help.js), and a screen
// reader hears it with the pill's words.
const reasonPill = (className, label, why) => noteButton({ class: ["pill pill-btn", className], title: why }, [
  label, h("span", { class: "sr-only" }, ` (${why})`)], () => why);

// The red Avoiding pill of a candidate on the voter's own Avoid list; its note says what matched.
function bannedPill(candidate) {
  const matched = banMatches(candidate.name);
  if (!matched.length) return null;
  return reasonPill("pill-banned", [icon("ban"), "Avoiding"], `On your Avoid list: matches ${matched.map((entry) => `“${entry.text}”`).join(", ")}`);
}

const UNVERIFIED = "Filed with the FEC to run for this seat. Pallot can't confirm they're on your November ballot: "
  + "they may have lost their primary or dropped out.";

// The pills under a candidate's name: Avoiding (bannedPill), their party, Party holds seat (its note
// names the race's holder), Incumbent, Write-in, Unverified (from the FEC's filers, not an official list).
export function candidatePills(candidate, race = null) {
  const party = partyName(candidate);
  const holder = candidate.party_holds_seat ? race?.holder : null;
  return [
    bannedPill(candidate),
    party ? h("span", { class: ["party", `party-${candidate.party || "none"}`] }, party) : null,
    holder ? reasonPill(null, "Party holds seat", holder.hint) : null,
    candidate.incumbent ? h("span", { class: "pill" }, "Incumbent") : null,
    candidate.write_in ? h("span", { class: "pill" }, "Write-in") : null,
    candidate.unverified ? reasonPill(null, "Unverified", UNVERIFIED) : null,
  ];
}
