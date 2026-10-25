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
// office (``site``), Texas's, Michigan's, California's, Arizona's, Nevada's, Georgia's, Wisconsin's,
// Ohio's, Iowa's, New Jersey's, New York's and Colorado's registration, mail voting and poll hours, and Texas's print tips.
export const STATES = {
  ...Object.fromEntries(Object.entries(SITES).map(([state, url]) => [state, { site: { label: siteLabel(url), url } }])),
  TX: {
    site: { label: "VoteTexas.gov", url: "https://www.votetexas.gov/" },
    noPhones: true, // phones can't be used at the voting station
    // My Voter Portal: a login with name and date of birth, which also shows the voter's polling place
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://goelect.txelections.civixapps.com/ivis-mvp-ui/#/login",
      hint: "My Voter Portal (Texas SOS): your registration, and your polling place once you log in",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://www.votetexas.gov/voting/where.html",
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
  MI: {
    site: { label: siteLabel(SITES.MI), url: SITES.MI },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://mvic.sos.state.mi.us/Voter/Index",
      hint: "Michigan Voter Information Center: your registration and your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://mvic.sos.state.mi.us/Voter/Index#yourclerk",
      hint: "Your city or township clerk (Michigan Voter Information Center), who publishes where and when you can vote early",
    },
    localOffice: "Your city or township clerk",
    mailApply: { label: "How to apply", url: "https://www.michigan.gov/sos/elections/voting/absentee-voting" },
    mailEligibility: "Any registered voter can vote absentee, no reason needed. You can also apply in person at your "
      + "clerk's office until 4 p.m. the day before Election Day.",
    mailDeadline: "Online and mailed applications must reach your clerk by 5 p.m. on ",
    pollHours: "7 a.m. – 8 p.m.",
  },
  CA: {
    site: { label: siteLabel(SITES.CA), url: SITES.CA },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://voterstatus.sos.ca.gov/",
      hint: "My Voter Status (California SOS): your registration, and where your mail ballot is",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://www.sos.ca.gov/elections/voting-resources/county-elections-offices",
      hint: "Every county's elections office (California SOS); yours lists its vote centers, polling places and drop boxes",
    },
    mailApply: { label: "Voting by mail", url: "https://www.sos.ca.gov/elections/voter-registration/vote-mail" },
    mailEligibility: "Every active voter is mailed a ballot. Mail it back postmarked by Election Day (it must reach "
      + "your county within 7 days), or drop it off by 8 p.m. on Election Day.",
    mailDeadline: "If yours is lost or damaged, the Secretary of State recommends asking your county for a new one by ",
    pollHours: "7 a.m. – 8 p.m.",
  },
  AZ: {
    site: { label: siteLabel(SITES.AZ), url: SITES.AZ },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://my.arizona.vote/",
      hint: "Arizona.Vote (Arizona Secretary of State): your registration, your polling place and your ballot's status",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://my.arizona.vote/",
      hint: "Arizona.Vote: your polling place; Maricopa and Pima counties also have their own lookups",
    },
    localOffice: "Your county recorder",
    mailApply: { label: "How to ask", url: "https://my.arizona.vote/" },
    mailEligibility: "Any registered voter can vote early by mail, no reason needed. Early ballots go out from "
      + "October 7; ask your county recorder for yours, or join the Active Early Voting List.",
    pollHours: "6 a.m. – 7 p.m.",
  },
  NV: {
    site: { label: siteLabel(SITES.NV), url: SITES.NV },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://www.nvsos.gov/votersearch/",
      hint: "Nevada Secretary of State's voter search: your registration and your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: SITES.NV,
      hint: "Nevada Secretary of State's elections page; your county clerk publishes where and when you can vote",
    },
    localOffice: "Your county clerk",
    mailApply: { label: "More on voting by mail", url: SITES.NV },
    mailEligibility: "Every active voter is mailed a ballot. Mail it back postmarked by Election Day (it must arrive "
      + "by 5 p.m. on the fourth day after), or drop it off at any polling place or drop box by 7 p.m. on Election Day.",
    mailDeadline: "To still be mailed one, register or update your registration by ",
    pollHours: "7 a.m. – 7 p.m.",
  },
  GA: {
    site: { label: siteLabel(SITES.GA), url: SITES.GA },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://mvp.sos.ga.gov/s/",
      hint: "My Voter Page (Georgia Secretary of State): your registration, your polling place and your sample ballot",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://mvp.sos.ga.gov/s/",
      hint: "My Voter Page: your polling place and your county's early voting places",
    },
    localOffice: "Your county's board of registrars",
    mailApply: { label: "How to apply", url: "https://securemyabsenteeballot.sos.ga.gov/s/" },
    mailEligibility: "Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
      + "county by 7 p.m. on Election Day.",
    pollHours: "7 a.m. – 7 p.m.",
  },
  OH: {
    site: { label: siteLabel(SITES.OH), url: SITES.OH },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://voterlookup.ohiosos.gov/voterlookup.aspx",
      hint: "Ohio Secretary of State's voter lookup: your registration and your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://www.ohiosos.gov/elections/county-boards-of-elections-directory",
      hint: "Every county board of elections (Ohio Secretary of State); yours publishes where and when you can vote early",
    },
    localOffice: "Your county board of elections",
    mailApply: { label: "How to apply", url: "https://www.ohiosos.gov/elections/request-an-absentee-ballot" },
    mailEligibility: "Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
      + "county board by 7:30 p.m. on Election Day: one mailed in time but arriving later isn't counted.",
    mailDeadline: "Your application must reach your county board by the close of business on ",
    pollHours: "6:30 a.m. – 7:30 p.m.",
  },
  NJ: {
    site: { label: siteLabel(SITES.NJ), url: SITES.NJ },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://voter.svrs.nj.gov/registration-check",
      hint: "New Jersey's voter registration check (Division of Elections)",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://voter.svrs.nj.gov/polling-place-search",
      hint: "New Jersey's polling place search; your county lists its early voting places",
    },
    localOffice: "Your county clerk",
    mailApply: { label: "How to apply", url: "https://www.nj.gov/state/elections/vote-by-mail.shtml" },
    mailEligibility: "Any registered voter can vote by mail, no reason needed. Your ballot must be postmarked by "
      + "Election Day and reach your county within six days, or be dropped in a drop box by 8 p.m. on Election Day.",
    mailDeadline: "An application sent by mail must reach your county clerk by ",
    pollHours: "6 a.m. – 8 p.m.",
  },
  WI: {
    site: { label: siteLabel(SITES.WI), url: SITES.WI },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://myvote.wi.gov/",
      hint: "MyVote Wisconsin (Wisconsin Elections Commission): your registration, your polling place and your ballot",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://myvote.wi.gov/",
      hint: "MyVote Wisconsin: your polling place, and your municipal clerk's office for voting early",
    },
    localOffice: "Your municipal clerk",
    mailApply: { label: "How to apply", url: "https://myvote.wi.gov/" },
    mailEligibility: "Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
      + "polling place or clerk by 8 p.m. on Election Day.",
    mailDeadline: "Mailed or online requests must reach your clerk by 5 p.m. on ",
    pollHours: "7 a.m. – 8 p.m.",
  },
  NY: {
    site: { label: siteLabel(SITES.NY), url: SITES.NY },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://voterlookup.elections.ny.gov/",
      hint: "New York State Board of Elections' voter lookup: your registration and your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://voterlookup.elections.ny.gov/",
      hint: "The voter lookup: your polling place; your county board of elections publishes its early voting places",
    },
    localOffice: "Your county board of elections",
    mailApply: { label: "How to apply", url: "https://absenteeballot.elections.ny.gov/" },
    mailEligibility: "Any registered voter can vote early by mail, no reason needed. Your ballot must be postmarked "
      + "by Election Day and reach your county board within 7 days after.",
    mailDeadline: "Online or mailed applications must reach your county board by ",
    pollHours: "6 a.m. – 9 p.m.",
  },
  IA: {
    site: { label: siteLabel(SITES.IA), url: SITES.IA },
    registration: {
      label: "Am I registered?", short: "Registered?", url: SITES.IA,
      hint: "Iowa Secretary of State: check your registration and find your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: SITES.IA,
      hint: "Iowa Secretary of State: your polling place, and your county auditor's office for voting early",
    },
    localOffice: "Your county auditor",
    mailApply: { label: "How to ask", url: SITES.IA },
    mailEligibility: "Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
      + "county auditor before the polls close at 8 p.m. on Election Day.",
    mailDeadline: "Your request must reach your county auditor by 5 p.m. on ",
    pollHours: "7 a.m. – 8 p.m.",
  },
  AK: {
    site: { label: siteLabel(SITES.AK), url: SITES.AK },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://myvoterinformation.alaska.gov/",
      hint: "Alaska Division of Elections' My Voter Information: your registration and your polling place",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://www.elections.alaska.gov/voter-information/absentee-and-early-voting/",
      hint: "Alaska Division of Elections: early and in-person absentee voting places",
    },
    localOffice: "The Division of Elections' regional office",
    mailApply: { label: "How to apply", url: "https://absenteeballotapplication.alaska.gov/" },
    mailEligibility: "Any registered voter can vote absentee by mail, no reason needed. Your ballot must be postmarked "
      + "by Election Day and reach the Division of Elections within 10 days after.",
    mailDeadline: "Your application must reach the Division of Elections by ",
    pollHours: "7 a.m. – 8 p.m.",
  },
  CO: {
    site: { label: siteLabel(SITES.CO), url: SITES.CO },
    registration: {
      label: "Am I registered?", short: "Registered?", url: "https://www.govotecolorado.gov/",
      hint: "GoVoteColorado (Colorado Secretary of State): your registration, your ballot's status and where to vote",
    },
    countyOffices: {
      label: "Where to vote", short: "Where", url: "https://www.govotecolorado.gov/",
      hint: "GoVoteColorado: your county's voter service and polling centers and drop boxes",
    },
    localOffice: "Your county clerk",
    mailApply: { label: "Track your ballot", url: "https://www.govotecolorado.gov/" },
    mailEligibility: "Every active voter is mailed a ballot, from 22 days before Election Day. It must reach your "
      + "county clerk by 7 p.m. on Election Day, by mail, in a drop box or at a voter service and polling center; "
      + "a postmark doesn't count.",
    pollHours: "7 a.m. – 7 p.m.",
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
