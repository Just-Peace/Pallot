// Pick by rule: the voter's rule, what it would do to the picks, and which candidates it
// matches. pick-rule-dialog.js draws it. The rule stays in this browser, like the picks.
//
// The Pick half is AND across its conditions, OR across the party chips and across the endorsers;
// Don't pick is OR. A condition from a source (TrackAIPAC, Vote for Peace, an endorsement list, money, polls) counts only in races where that source has
// something, so "Democrats who spent under $1M" still picks a county race's Democrat. A race with
// more matches than seats is left for the voter: the rule never guesses, so a tie for "the least"
// money in a one-seat race is left too.

import { ballotSections } from "./ballot-shared.js";
import { COUNT, DOLLARS_SHORT, either, listed as andList } from "./format.js";
import { partyName } from "./labels.js";
import { PICK_RULE, readJson, writeJson } from "./storage.js";

const TRACKAIPAC = "trackaipac";
const VOTEFORPEACE = "voteforpeace";
const ENDORSEMENT = "endorsement"; // the flag on an endorsement list's cards, whose source is the list's id
export const WRITE_INS = "write-in"; // the party chip for the declared write-in candidates
const PARTY_ORDER = ["R", "D", "L", "G", "I"];

// The money measures, by their figure on the FEC's and the TEC's cards.
export const MONEY = [
  ["raised", "Raised"],
  ["spent", "Spent"],
  ["cash", "Cash on hand"],
  ["outside_for", "Outside money for them"],
];

export const DEFAULT_RULE = {
  parties: [],
  incumbent: "any", // "yes": only incumbents, "no": only challengers
  endorsedBy: [], // any of these endorse them: TrackAIPAC, Vote for Peace (an ally) or an endorsement list (its source id)
  money: { on: false, metric: "spent", compare: "under", amount: 1_000_000 }, // compare: "under", "over", "least", "most"
  small: { on: false, amount: 50 }, // small donations are at least this % of what they raised
  texas: { on: false, amount: 50 }, // donors in Texas gave at least this % of their itemized donations
  leads: false,
  watchlist: false,
  peaceOpposed: false, // Vote for Peace marks them Opposed
  lobby: { on: false, amount: 0 },
  selfFunded: { on: false, amount: 50 }, // they gave or lent their campaign over this % of what it raised
  polling: { on: false, amount: 5 },
  keepMine: true,
};

// The saved rule over the defaults, so a rule saved before a condition existed still loads.
export function loadRule() {
  const rule = structuredClone(DEFAULT_RULE);
  const saved = readJson(PICK_RULE, {});
  for (const [key, value] of Object.entries(saved && typeof saved === "object" ? saved : {})) {
    if (!(key in rule) || value == null) continue;
    const nested = typeof rule[key] === "object" && !Array.isArray(rule[key]);
    rule[key] = nested ? { ...rule[key], ...value } : value;
  }
  // A rule saved when TrackAIPAC and Vote for Peace had boxes of their own.
  if (saved?.endorsed) rule.endorsedBy = [...new Set([TRACKAIPAC, ...rule.endorsedBy])];
  if (saved?.peaceAlly) rule.endorsedBy = [...new Set([VOTEFORPEACE, ...rule.endorsedBy])];
  return rule;
}

export const saveRule = (rule) => writeJson(PICK_RULE, rule);

// A source's figure for the candidate (undefined when none has it).
export function figure(candidate, id) {
  const card = candidate.cards.find((c) => c.figures && id in c.figures);
  return card ? card.figures[id] : undefined;
}

const tracked = (candidate, source = TRACKAIPAC) => candidate.cards.some((c) => c.source === source);
const listed = (candidate, list, source = TRACKAIPAC) =>
  candidate.cards.some((c) => c.source === source && c.flags?.includes(list));
const marked = (candidate) => tracked(candidate, VOTEFORPEACE);
const endorses = (candidate, source) => listed(candidate, ENDORSEMENT, source);

// Whether ``source`` (an endorser chip) endorses the candidate: TrackAIPAC's endorsement, Vote for
// Peace's Ally, or an endorsement list's card.
function endorsedBy(candidate, source) {
  if (source === TRACKAIPAC) return listed(candidate, "endorsed");
  if (source === VOTEFORPEACE) return listed(candidate, "ally", VOTEFORPEACE);
  return endorses(candidate, source);
}

// Whether an endorser has anything in a race: TrackAIPAC or Vote for Peace has a candidate, or the list endorses one.
function covers(candidates, source) {
  if (source === TRACKAIPAC) return candidates.some((c) => tracked(c));
  if (source === VOTEFORPEACE) return candidates.some(marked);
  return candidates.some((c) => endorses(c, source));
}
const known = (amount) => typeof amount === "number" && Number.isFinite(amount);

// "1,000,000", "$1M", "250k" -> a number; null when it isn't one.
export function parseAmount(text) {
  const match = String(text).trim().toLowerCase().replace(/[$,\s]/g, "").match(/^(\d+(?:\.\d+)?|\.\d+)([km]?)$/);
  if (!match) return null;
  return Number(match[1]) * ({ k: 1e3, m: 1e6 }[match[2]] || 1);
}

// Every race on the ballot, the ones that may not be on it included, in ballot order.
export const allRaces = (ballot) => ballotSections(ballot).flatMap((section) => section.races);

// Where a rule can apply: every race, a section, or the race it was opened from.
export function scopes(ballot, raceKey = null) {
  const sections = ballotSections(ballot);
  const out = [];
  const race = raceKey && sections.flatMap((s) => s.races).find((r) => r.key === raceKey);
  if (race) out.push({ id: `race:${race.key}`, label: `This race: ${race.name}`, races: [race] });
  out.push({ id: "all", label: "Every race", races: sections.flatMap((s) => s.races) });
  for (const section of sections) out.push({ id: section.id, label: section.title, races: section.races });
  return out;
}

// The parties on these races, Republican, Democratic, Libertarian, Green and Independent first,
// each with how many races it has a candidate in; then the declared write-ins.
export function ballotParties(races) {
  const found = new Map();
  const add = (code, label, race) => {
    if (!found.has(code)) found.set(code, { code, label, races: new Set() });
    found.get(code).races.add(race.key);
  };
  for (const race of races) {
    for (const candidate of race.candidates) {
      if (candidate.write_in) add(WRITE_INS, "Write-ins", race);
      else if (candidate.party) add(candidate.party, partyName(candidate) || candidate.party, race);
    }
  }
  const rank = (code) => (code === WRITE_INS ? 99 : PARTY_ORDER.includes(code) ? PARTY_ORDER.indexOf(code) : 50);
  return [...found.values()]
    .map(({ code, label, races: inRaces }) => ({ code, label, count: inRaces.size }))
    .sort((a, b) => rank(a.code) - rank(b.code) || a.label.localeCompare(b.label));
}

// Who endorses someone among these candidates, as { source, label }: TrackAIPAC, Vote for Peace
// (an ally), then the endorsement lists by label.
function endorsers(candidates) {
  const found = new Map();
  for (const card of candidates.flatMap((c) => c.cards)) {
    if (card.flags?.includes(ENDORSEMENT)) found.set(card.source, { source: card.source, label: card.label });
  }
  return [
    candidates.some((c) => endorsedBy(c, TRACKAIPAC)) ? { source: TRACKAIPAC, label: "TrackAIPAC" } : null,
    candidates.some((c) => endorsedBy(c, VOTEFORPEACE)) ? { source: VOTEFORPEACE, label: "Vote for Peace" } : null,
    ...[...found.values()].sort((a, b) => a.label.localeCompare(b.label)),
  ].filter(Boolean);
}

// Which conditions have anything to go on in these races; the dialog hides the rest, and
// lists only the endorsers that endorse someone here.
export function available(races) {
  const candidates = races.flatMap((race) => race.candidates);
  const has = (id) => candidates.some((c) => figure(c, id) !== undefined);
  return {
    endorsers: endorsers(candidates),
    trackaipac: candidates.some((c) => tracked(c)),
    voteforpeace: candidates.some(marked),
    lobby: has("israel_lobby"),
    money: Object.fromEntries(MONEY.map(([id]) => [id, has(id)])),
    small: has("small_share"),
    texas: has("in_state_share"),
    selfFunded: has("self_share"),
    polls: has("poll"),
  };
}

// How each money measure reads in describeRule: against an amount, then the least or the most.
const MONEY_WORDS = {
  raised: ["raised {cmp} {amount}", "raised the {cmp} in the race"],
  spent: ["spent {cmp} {amount}", "spent the {cmp} in the race"],
  cash: ["have {cmp} {amount} cash on hand", "have the {cmp} cash on hand in the race"],
  outside_for: ["had {cmp} {amount} spent for them from outside", "had the {cmp} spent for them from outside in the race"],
};

const share = (amount) => `${COUNT.format(amount)}%`;

// The rule in words, as { pick, skip } (null for a half with nothing on): "Pick Democratic
// incumbents who have endorsements from JVP Action and spent under $1M." Only the conditions with
// something to go on (``has``, from available()) count, as only they show in the dialog.
// ``parties``: ballotParties(), for the chips' names.
export function describeRule(rule, parties, has) {
  const on = (condition, amount) => condition && known(amount);
  const adjectives = parties.filter((p) => rule.parties.includes(p.code))
    .map((p) => (p.code === WRITE_INS ? "write-in" : p.label));
  const noun = { yes: "incumbents", no: "challengers" }[rule.incumbent] || "candidates";
  const chosen = has.endorsers.filter((e) => rule.endorsedBy.includes(e.source)).map((e) => e.label);
  const { money } = rule;
  const relative = money.compare === "least" || money.compare === "most";
  const [vsAmount, vsRace] = MONEY_WORDS[money.metric] || MONEY_WORDS.spent;
  const moneyWords = money.on && has.money[money.metric] && (relative || known(money.amount))
    ? (relative ? vsRace : vsAmount).replace("{cmp}", money.compare).replace("{amount}", DOLLARS_SHORT.format(money.amount))
    : null;
  const clauses = [
    chosen.length ? `have endorsements from ${either(chosen)}` : null,
    moneyWords,
    on(rule.small.on && has.small, rule.small.amount) ? `get at least ${share(rule.small.amount)} of their money in small donations` : null,
    on(rule.texas.on && has.texas, rule.texas.amount)
      ? `get at least ${share(rule.texas.amount)} of their itemized donations from Texas` : null,
    rule.leads && has.polls ? "lead the polls" : null,
  ].filter(Boolean);
  const pick = adjectives.length || noun !== "candidates" || clauses.length
    ? `Pick ${[either(adjectives), noun].filter(Boolean).join(" ")}${clauses.length ? ` who ${andList(clauses)}` : ""}.`
    : null;

  const lobby = rule.lobby.amount > 0 ? `with over ${DOLLARS_SHORT.format(rule.lobby.amount)} of Israel lobby money` : "with any Israel lobby money";
  const avoid = [
    rule.watchlist && has.trackaipac ? "on TrackAIPAC's watchlist" : null,
    rule.peaceOpposed && has.voteforpeace ? "opposed by Vote for Peace" : null,
    on(rule.lobby.on && has.lobby, rule.lobby.amount) ? lobby : null,
    on(rule.selfFunded.on && has.selfFunded, rule.selfFunded.amount)
      ? `whose own money is over ${share(rule.selfFunded.amount)} of what they raised` : null,
    on(rule.polling.on && has.polls, rule.polling.amount) ? `polling under ${share(rule.polling.amount)}` : null,
  ].filter(Boolean);
  const skip = avoid.length ? `Don't pick anyone ${either(avoid)}, and take back their picks.` : null;
  return { pick, skip };
}

// The rule in one race: whether its Pick half applies there, who it picks (``matches``, never
// anyone Don't pick catches), who it would pick (``picks``) and why Don't pick catches someone.
function judge(race, rule) {
  const { candidates } = race;
  const tests = [];
  const parties = new Set(rule.parties);
  if (parties.size) tests.push((c) => parties.has(c.write_in ? WRITE_INS : c.party));
  if (rule.incumbent === "yes") tests.push((c) => c.incumbent);
  if (rule.incumbent === "no") tests.push((c) => !c.incumbent);
  const endorsing = rule.endorsedBy.filter((source) => covers(candidates, source));
  if (endorsing.length) tests.push((c) => endorsing.some((source) => endorsedBy(c, source)));
  const { money } = rule;
  const relative = money.compare === "least" || money.compare === "most";
  if (money.on && (relative || known(money.amount)) && candidates.some((c) => figure(c, money.metric) !== undefined)) {
    // The least or the most among the names printed on the ballot, and the write-ins with their chip on.
    const amounts = candidates.filter((c) => !c.write_in || parties.has(WRITE_INS))
      .map((c) => figure(c, money.metric)).filter((amount) => amount !== undefined);
    const target = { least: Math.min(...amounts), most: Math.max(...amounts) }[money.compare];
    tests.push((c) => {
      const amount = figure(c, money.metric);
      if (amount === undefined) return false;
      if (relative) return amount === target;
      return money.compare === "over" ? amount > money.amount : amount < money.amount;
    });
  }
  if (rule.small.on && known(rule.small.amount) && candidates.some((c) => figure(c, "small_share") !== undefined)) {
    tests.push((c) => {
      const share = figure(c, "small_share");
      return share !== undefined && share >= rule.small.amount;
    });
  }
  if (rule.texas.on && known(rule.texas.amount) && candidates.some((c) => figure(c, "in_state_share") !== undefined)) {
    tests.push((c) => {
      const share = figure(c, "in_state_share");
      return share !== undefined && share >= rule.texas.amount;
    });
  }
  const polled = candidates.map((c) => figure(c, "poll")).filter((share) => share !== undefined);
  if (rule.leads && polled.length) tests.push((c) => figure(c, "poll") === Math.max(...polled));

  const avoid = new Map();
  for (const c of candidates) {
    const reasons = [];
    if (rule.watchlist && listed(c, "watchlist")) reasons.push("on TrackAIPAC's watchlist");
    if (rule.peaceOpposed && listed(c, "opposed", VOTEFORPEACE)) reasons.push("opposed by Vote for Peace");
    const lobby = figure(c, "israel_lobby");
    if (rule.lobby.on && known(rule.lobby.amount) && lobby !== undefined && lobby > rule.lobby.amount) {
      reasons.push(`Israel lobby money ${DOLLARS_SHORT.format(lobby)}`);
    }
    const own = figure(c, "self_share");
    if (rule.selfFunded.on && known(rule.selfFunded.amount) && own !== undefined && own > rule.selfFunded.amount) {
      reasons.push(`${own}% of their money from themselves`);
    }
    const share = figure(c, "poll");
    if (rule.polling.on && known(rule.polling.amount) && share !== undefined && share < rule.polling.amount) {
      reasons.push(`polling at ${share}%`);
    }
    if (reasons.length) avoid.set(c.key, reasons);
  }

  // Without a party chip, only the names printed on the ballot.
  const base = parties.size ? () => true : (c) => !c.write_in;
  const picks = tests.length ? candidates.filter((c) => base(c) && tests.every((test) => test(c))) : [];
  return { active: tests.length > 0, picks, matches: picks.filter((c) => !avoid.has(c.key)), avoid };
}

const sameKeys = (a, b) => a.length === b.length && a.every((key) => b.includes(key));

// What the rule would do in ``races``: a row per race it touches, with its ``outcome`` ("pick",
// "same": already picked so, "kept": the voter's pick stays, "many": more matches than seats,
// "none": no match, or null when it only takes picks back), the picks ``before`` and ``after``,
// and the picks it takes back with why. ``changed`` counts the races whose picks change.
export function plan(races, rule, picks) {
  const rows = [];
  for (const race of races) {
    const { active, matches, avoid } = judge(race, rule);
    const before = picks.picked(race.key);
    const kept = before.filter((key) => !avoid.has(key));
    const takenBack = before.filter((key) => avoid.has(key)).map((key) => ({ key, reasons: avoid.get(key) }));
    let outcome = null;
    let after = kept;
    if (active) {
      if (rule.keepMine && kept.length) outcome = "kept";
      else if (!matches.length) outcome = "none";
      else if (matches.length > race.seats) outcome = "many";
      else {
        after = matches.map((c) => c.key);
        outcome = sameKeys(before, after) ? "same" : "pick";
      }
    }
    if (!outcome && !takenBack.length) continue;
    rows.push({ race, outcome, before, after, matches, takenBack, changed: !sameKeys(before, after) });
  }
  const count = (outcome) => rows.filter((row) => row.outcome === outcome).length;
  return {
    rows,
    picked: count("pick"),
    same: count("same"),
    kept: count("kept"),
    many: count("many"),
    none: count("none"),
    takenBack: rows.reduce((sum, row) => sum + row.takenBack.length, 0),
    changed: rows.filter((row) => row.changed).length,
  };
}
