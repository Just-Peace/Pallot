// A Pallot file (.pallot): a whole session, everything Pallot keeps in this browser, to keep or move
// to another device. Or a link, to send to someone: the picks and write-ins on the ballot shown (with
// the names and parties they belong to, the election's cycle and the districts, never the address),
// the notes and the Avoid list if the voter ticks them in. A link travels after "#picks=" in the
// address, which the browser never sends to the server, so Pallot keeps none of it. A file and a link
// are the same bytes: a header, then the compressed contents, a file always locked, a link only with
// the voter's own phrase. Opened on a ballot, its races and candidates are found by their keys, then by
// their names alone where one name fits (a friend's ballot, or another lookup), and the rest left out.

import { ANSWERS, WRITE_IN, cycleOf } from "./picks.js";
import { LAST_DISTRICTS, LAST_LOOKUP, PICKS, SETTINGS_CHANGED } from "./storage.js";

export const VERSION = 1;
export const LINK_KEY = "picks";
export const EXTENSION = ".pallot";
const KIND = "pallot";
const MAGIC = [0x50, 0x41, 0x4c, 0x4c, 0x4f, 0x54]; // "PALLOT"
const HEAD = MAGIC.length + 2; // the mark, then the version and how it's locked
const OPEN = 0;
const LOCKED = 1; // with the built-in key
const PHRASED = 2; // with the voter's phrase
const MAX_BYTES = 1_000_000; // a file or unpacked link larger than this isn't a Pallot file
const MAX_ENTRIES = 500;
const MAX_TEXT = 5000;
const MAX_KEYS = 50; // a session's stored keys
const DATED = /^\d{4}-\d{2}-\d{2}$/;
const DISTRICT_KINDS = ["state", "county", "cd", "sd", "hd", "sboe", "precinct", "commissioner", "jp", "constable"];

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = (value, max = 300) => (typeof value === "string" ? value.slice(0, max) : "");
const plain = (value) => String(value ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export const allRaces = (ballot) => [...ballot.races, ...ballot.maybe.flatMap((section) => section.races)];

function pickName(race, key, picks, people) {
  if (race.retention) return ANSWERS.find(([answer]) => answer === key)?.[1] ?? null;
  if (key === WRITE_IN) return picks.writeIn(race.key).trim() || "Write-in";
  return people.get(key)?.name ?? null;
}

const partyOf = (candidate) => (candidate?.party ? { party: candidate.party } : {});

// What a link sends from ``ballot``: its picks and write-ins (unless ``withPicks`` is false), the
// voter's ``notes`` if true, ``avoid`` (the Avoid list's entries) if given, and ``districts``
// (districtsRecord's), to tell the person who opens it which ballot the picks are for. ``title``: the
// election line, for them. The address is never in it.
export function buildSlate(ballot, picks, { request = {}, title = "", withPicks = true, notes = false, avoid = null, districts = null } = {}) {
  const races = [];
  const kept = [];
  for (const race of allRaces(ballot)) {
    const people = new Map(race.candidates.map((c) => [c.key, c]));
    const chosen = picks.picked(race.key)
      .map((key) => ({ key, name: pickName(race, key, picks, people), ...partyOf(people.get(key)) }))
      .filter((pick) => pick.name !== null);
    const writeIn = picks.writeIn(race.key).trim();
    if (withPicks && (chosen.length || writeIn)) races.push({ key: race.key, name: race.name, picks: chosen, ...(writeIn ? { write_in: writeIn } : {}) });
    if (!notes) continue;
    for (const candidate of race.candidates) {
      const note = picks.note(candidate.key);
      if (note.trim()) kept.push({ key: candidate.key, name: candidate.name, race: race.key, ...partyOf(candidate), text: note });
    }
  }
  const party = request?.party;
  return {
    kind: KIND,
    version: VERSION,
    election: { date: ballot.election_date, title, ...(party ? { party } : {}), cycle: cycleOf(ballot) },
    ...(districts ? { districts } : {}),
    races,
    notes: kept,
    ...(avoid?.length ? { avoid: avoid.map(({ text: entry, plain: literal }) => ({ text: entry, plain: Boolean(literal) })) } : {}),
  };
}

const parsed = (raw) => {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

// A whole session: ``store``, every key Pallot keeps in this browser as stored, and ``race``, the race
// on screen, to go back to. Its address, election and districts are read from the store, to show.
export function buildSession(store, { race = "" } = {}) {
  const lookup = parsed(store[LAST_LOOKUP]);
  const place = readPlace(lookup);
  const districts = place && readDistricts(parsed(store[LAST_DISTRICTS]));
  return {
    kind: KIND,
    version: VERSION,
    election: { date: DATED.test(lookup?.election_date) ? lookup.election_date : null, title: "" },
    ...(place ? { ballot: place, ...(districts ? { districts } : {}) } : {}),
    races: [],
    notes: [],
    session: { store, ...(race ? { race } : {}) },
  };
}

// How many races have a pick, how many notes there are, and how many Avoid list entries; a session's
// picks and notes across every election it keeps.
export function slateCounts(slate) {
  if (!slate.session) {
    return { races: slate.races.filter((race) => race.picks.length).length, notes: slate.notes.length, avoid: slate.avoid?.length || 0 };
  }
  const buckets = Object.values(parsed(slate.session.store[PICKS]) || {}).filter(isObject);
  const count = (part) => buckets.reduce((n, bucket) => n + Object.keys(isObject(bucket[part]) ? bucket[part] : {}).length, 0);
  return { races: count("races"), notes: count("notes"), avoid: 0 };
}

// The districts ``ballot`` was found in, as a file keeps them, to show where its ballot is and to
// tell whether it's the same as another's: each number or name, and ``line``, as the voter reads them.
export function districtsRecord(ballot, line = "") {
  const d = ballot.districts || {};
  const where = ballot.location || {};
  return readDistricts({
    state: where.state, county: where.county_name || where.county, cd: d.cd, sd: d.sd, hd: d.hd, sboe: d.sboe,
    precinct: d.election_precinct?.name, commissioner: d.commissioner, jp: d.jp, constable: d.constable, line,
  });
}

function readDistricts(value) {
  if (!isObject(value)) return null;
  const record = {};
  for (const kind of DISTRICT_KINDS) {
    const found = value[kind];
    if (Number.isInteger(found) && found >= 0 && found < 10000) record[kind] = found;
    else if (text(found, 40).trim()) record[kind] = text(found, 40).trim();
  }
  if (text(value.line).trim()) record.line = text(value.line).trim();
  return DISTRICT_KINDS.slice(2).some((kind) => kind in record) ? record : null;
}

// Whether two records (districtsRecord's) are the same districts, so the same ballot.
export function sameDistricts(a, b) {
  if (!a || !b) return false;
  return DISTRICT_KINDS.every((kind) => String(a[kind] ?? "") === String(b[kind] ?? ""));
}

// Whether two lookups (a file's ``ballot``, a request) are for the same address, or the same voter
// card's state, county and precinct.
export function samePlace(a, b) {
  if (!a || !b) return false;
  if (a.address || b.address) return Boolean(a.address && b.address) && plain(a.address) === plain(b.address);
  const county = (value) => plain(value).replace(/ (county|parish|borough)$/, "");
  return (a.state || "TX") === (b.state || "TX") && county(a.county) === county(b.county)
    && plain(a.precinct).replace(/^0+(?=.)/, "") === plain(b.precinct).replace(/^0+(?=.)/, "");
}

const smallNumbers = (value) => (isObject(value)
  ? Object.fromEntries(Object.entries(value).filter(([, n]) => Number.isInteger(n) && n > 0 && n < 1000).slice(0, 10))
  : {});

// Where the file says its ballot is: only the parts a lookup takes, as text and small numbers.
function readPlace(value) {
  if (!isObject(value)) return null;
  const place = {};
  for (const field of ["address", "state", "county", "precinct"]) if (text(value[field])) place[field] = text(value[field]);
  for (const field of ["districts", "precincts"]) if (Object.keys(smallNumbers(value[field])).length) place[field] = smallNumbers(value[field]);
  return place.address || place.county ? place : null;
}

// A Pallot file's contents read from JSON (a file's or a link's unpacked text): checked, with anything it
// shouldn't hold dropped. Throws an Error that says what's wrong, for the voter.
export function readSlate(json) {
  let data;
  try {
    data = typeof json === "string" ? JSON.parse(json) : json;
  } catch {
    throw new Error("This isn't a Pallot file.");
  }
  if (!isObject(data) || data.kind !== KIND) throw new Error("This isn't a Pallot file.");
  if (!(Number(data.version) <= VERSION)) throw new Error("This file was made by a newer Pallot.");
  const election = isObject(data.election) ? data.election : {};
  const party = (value) => (text(value, 20) ? { party: text(value, 20) } : {});
  const races = (Array.isArray(data.races) ? data.races : []).filter(isObject).slice(0, MAX_ENTRIES).map((race) => ({
    key: text(race.key),
    name: text(race.name),
    picks: (Array.isArray(race.picks) ? race.picks : []).filter(isObject).slice(0, 50)
      .map((pick) => ({ key: text(pick.key), name: text(pick.name), ...party(pick.party) })).filter((pick) => pick.key || pick.name),
    ...(text(race.write_in).trim() ? { write_in: text(race.write_in) } : {}),
  })).filter((race) => (race.key || race.name) && (race.picks.length || race.write_in));
  const notes = (Array.isArray(data.notes) ? data.notes : []).filter(isObject).slice(0, MAX_ENTRIES).map((note) => ({
    key: text(note.key), name: text(note.name), race: text(note.race), ...party(note.party), text: text(note.text, MAX_TEXT),
  })).filter((note) => (note.key || note.name) && note.text.trim());
  const place = readPlace(data.ballot);
  const districts = readDistricts(data.districts);
  const cycle = readCycle(election.cycle);
  const session = readSession(data.session);
  const avoid = readAvoid(data.avoid);
  return {
    kind: KIND,
    version: VERSION,
    election: {
      date: DATED.test(election.date) ? election.date : null,
      title: text(election.title),
      ...party(election.party),
      ...(cycle ? { cycle } : {}),
    },
    ...(place ? { ballot: place } : {}),
    ...(districts ? { districts } : {}),
    races,
    notes,
    ...(avoid.length ? { avoid } : {}),
    ...(session ? { session } : {}),
  };
}

// Someone else's Avoid list entries (ban-list.js's { text, plain }). A pattern that repeats a group,
// which can take a browser minutes to try on a name, is kept as plain text.
function readAvoid(value) {
  const seen = new Set();
  return (Array.isArray(value) ? value : []).filter(isObject).slice(0, MAX_ENTRIES)
    .map((entry) => ({ text: text(entry.text, 200).trim(), plain: entry.plain === true || /\)\s*[*+{]|\\\d/.test(text(entry.text, 200)) }))
    .filter((entry) => entry.text && !seen.has(entry.text.toLowerCase()) && seen.add(entry.text.toLowerCase()));
}

// An election's cycle (picks.js's cycleOf): its date, state and the elections on the ballot.
function readCycle(value) {
  if (!isObject(value)) return null;
  const elections = (Array.isArray(value.elections) ? value.elections : []).filter(isObject).slice(0, 5)
    .map((e) => Object.fromEntries(Object.entries({ name: text(e.name), type: text(e.type, 40), party: text(e.party, 20) }).filter(([, v]) => v)))
    .filter((e) => e.name);
  const cycle = {
    ...(DATED.test(value.date) ? { date: value.date } : {}),
    ...(/^[A-Z]{2}$/.test(value.state) ? { state: value.state } : {}),
    ...(elections.length ? { elections } : {}),
  };
  return Object.keys(cycle).length ? cycle : null;
}

// A session's store: Pallot's own keys only, each holding JSON, and the race to go back to.
function readSession(value) {
  if (!isObject(value) || !isObject(value.store)) return null;
  const store = {};
  for (const [key, raw] of Object.entries(value.store).slice(0, MAX_KEYS)) {
    if (!key.startsWith("pallot.") || key === SETTINGS_CHANGED || typeof raw !== "string" || raw.length > MAX_BYTES) continue;
    if (parsed(raw) !== null) store[key] = raw;
  }
  if (!Object.keys(store).length) return null;
  return { store, ...(text(value.race) ? { race: text(value.race) } : {}) };
}

// ---- links ------------------------------------------------------------------------------

function toBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(value) {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

// ``bytes`` through a (de)compression stream, stopping once it's larger than MAX_BYTES.
async function through(bytes, stream) {
  const reader = new Blob([bytes]).stream().pipeThrough(stream).getReader();
  const parts = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > MAX_BYTES) {
      reader.cancel();
      throw new Error("too large");
    }
    parts.push(value);
  }
  return new Uint8Array(await new Blob(parts).arrayBuffer());
}

function compresses() {
  try {
    return Boolean(new CompressionStream("deflate-raw") && new DecompressionStream("deflate-raw"));
  } catch {
    return false;
  }
}

// ---- packing and locking ----------------------------------------------------------------

// A slate as a mark and bytes: "z" and the deflated JSON, or "j" and the JSON where the browser can't deflate.
async function pack(slate) {
  const bytes = new TextEncoder().encode(JSON.stringify(slate));
  return compresses() ? ["z", await through(bytes, new CompressionStream("deflate-raw"))] : ["j", bytes];
}

// A link or file that's damaged, and one the phrase given doesn't open (or a file not locked by Pallot).
class Unreadable extends Error {}
class WrongPhrase extends Error {}

async function unpack(mark, bytes) {
  let text = null;
  try {
    if (mark === "z" && compresses()) text = new TextDecoder().decode(await through(bytes, new DecompressionStream("deflate-raw")));
    else if (mark === "j" && bytes.length <= MAX_BYTES) text = new TextDecoder().decode(bytes);
  } catch {
    text = null;
  }
  if (text === null) throw new Unreadable();
  return readSlate(text);
}

// Not a secret: Pallot's code is public. It keeps a Pallot file from reading as text to whatever
// indexes or scans it (a mail or cloud drive) and protects nothing from anyone who opens it in
// Pallot, so the voter is never told it protects anything. Only the voter's own phrase does. Never
// change it, or files locked with it no longer open.
const BUILT_IN = "pallot-file-v1";
const ROUNDS = 600_000; // PBKDF2-SHA-256 rounds for the voter's phrase, as OWASP advises
const SALT = 16;
const IV = 12;

export const canLock = () => Boolean(globalThis.crypto?.subtle);

async function builtInKey() {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(BUILT_IN));
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt", "decrypt"]);
}

async function phraseKey(phrase, salt) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(phrase.normalize("NFC")), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: ROUNDS, hash: "SHA-256" }, base,
    { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

// ``mark`` and ``bytes`` (pack's) locked with AES-GCM: the salt (a phrase's only), the IV, then the
// sealed mark and bytes.
async function lock(mark, bytes, phrase) {
  const salt = phrase ? crypto.getRandomValues(new Uint8Array(SALT)) : new Uint8Array(0);
  const iv = crypto.getRandomValues(new Uint8Array(IV));
  const key = phrase ? await phraseKey(phrase, salt) : await builtInKey();
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, joined([mark.charCodeAt(0)], bytes)));
  return joined(salt, iv, sealed);
}

// What lock() sealed, as [mark, bytes]; throws a WrongPhrase where the phrase doesn't fit.
async function unlock(locked, phrase) {
  const salt = phrase ? locked.slice(0, SALT) : new Uint8Array(0);
  const iv = locked.slice(salt.length, salt.length + IV);
  const key = phrase ? await phraseKey(phrase, salt) : await builtInKey();
  let opened;
  try {
    opened = new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, locked.slice(salt.length + IV)));
  } catch {
    throw new WrongPhrase();
  }
  return [String.fromCharCode(opened[0]), opened.slice(1)];
}

// What the voter's phrase must have, each ``met`` or not: ``text`` in words, ``short`` for the line
// under the phrase box that names only what's missing.
export function phraseRules(phrase) {
  const left = 10 - [...phrase].length;
  const more = `${left} more character${left === 1 ? "" : "s"}`;
  return [
    { id: "length", text: more, short: more, met: left <= 0 },
    { id: "upper", text: "a capital letter", short: "A–Z", met: /\p{Lu}/u.test(phrase) },
    { id: "lower", text: "a small letter", short: "a–z", met: /\p{Ll}/u.test(phrase) },
    { id: "number", text: "a number", short: "0–9", met: /\p{Nd}/u.test(phrase) },
  ];
}

export const phraseReady = (phrase) => phraseRules(phrase).every((rule) => rule.met);

const joined = (...parts) => {
  const out = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
};

// ``slate`` as a file's or a link's bytes: "PALLOT", the version and how it's locked (OPEN, LOCKED
// with the built-in key for a file, ``hide``, or PHRASED with the voter's ``phrase``), then the mark
// and bytes, sealed if locked. Where the browser can't lock (plain HTTP, not localhost), it's left open.
async function encode(slate, { phrase = null, hide = false } = {}) {
  const [mark, bytes] = await pack(slate);
  let how = OPEN;
  let body = joined([mark.charCodeAt(0)], bytes);
  if (phrase) {
    how = PHRASED;
    body = await lock(mark, bytes, phrase);
  } else if (hide && canLock()) {
    how = LOCKED;
    body = await lock(mark, bytes, null);
  }
  return joined(MAGIC, [VERSION, how], body);
}

// The slate ``bytes`` (encode's) hold, or null if the voter cancelled the phrase. ``askPhrase(open)``
// asks the voter for a phrase: ``open(phrase)`` resolves to the slate, or to null when the phrase
// doesn't fit; askPhrase resolves to the slate, or to null when the voter gives up. Throws an
// Error for the voter: ``notOurs`` when it isn't a Pallot file, ``damaged`` when it can't be read.
async function decode(bytes, askPhrase, { notOurs, damaged }) {
  if (bytes.length < HEAD || bytes.length > MAX_BYTES || MAGIC.some((byte, i) => bytes[i] !== byte)) throw new Error(notOurs);
  if (bytes[MAGIC.length] > VERSION) throw new Error("This file was made by a newer Pallot.");
  const how = bytes[MAGIC.length + 1];
  const body = bytes.slice(HEAD);
  if (how !== OPEN && !canLock()) throw new Error("This browser can only open a locked Pallot file over HTTPS, or on the computer Pallot runs on.");
  try {
    if (how === OPEN) return await unpack(String.fromCharCode(body[0] ?? 0), body.slice(1));
    if (how === LOCKED) return await unpack(...await unlock(body, null));
  } catch (error) {
    throw error instanceof WrongPhrase || error instanceof Unreadable ? new Error(damaged) : error;
  }
  if (how !== PHRASED) throw new Error(damaged);
  return askPhrase(async (phrase) => {
    try {
      return await unpack(...await unlock(body, phrase));
    } catch (error) {
      if (error instanceof WrongPhrase) return null;
      throw error instanceof Unreadable ? new Error(damaged) : error;
    }
  });
}

// The link to ``page`` (the ballot page's address) that carries ``slate``, locked with ``phrase`` if given.
export async function slateLink(slate, page, phrase = null) {
  const url = new URL(page);
  url.hash = `${LINK_KEY}=${toBase64Url(await encode(slate, { phrase }))}`;
  return url.href;
}

export async function slateFromLink(value, askPhrase) {
  const unreadable = "This link's picks couldn't be read. Ask for the link again.";
  let bytes;
  try {
    if (typeof value !== "string" || value.length > MAX_BYTES * 2) throw new Error(unreadable);
    bytes = fromBase64Url(value);
  } catch {
    throw new Error(unreadable);
  }
  return decode(bytes, askPhrase, { notOurs: unreadable, damaged: unreadable });
}

// A Pallot file's bytes: always locked, with the voter's ``phrase`` or else the built-in key.
export const pallotFile = (slate, phrase = null) => encode(slate, { phrase, hide: true });

// The slate a Pallot file's ``bytes`` hold, or null if the voter cancelled the phrase.
export const readPallotFile = (bytes, askPhrase) => decode(bytes, askPhrase,
  { notOurs: "This isn't a Pallot file.", damaged: "This Pallot file couldn't be read." });

// ---- opening one on a ballot ------------------------------------------------------------

// The items whose ``name`` fits only one of them, by their plain name.
function byName(items) {
  const found = new Map();
  for (const item of items) {
    const name = plain(item.name);
    if (name) found.set(name, found.has(name) ? null : item);
  }
  return found;
}

function candidateKey(race, pick, names) {
  if (race.retention) return ANSWERS.find(([key, label]) => key === pick.key || plain(label) === plain(pick.name))?.[0] ?? null;
  if (pick.key === WRITE_IN) return WRITE_IN;
  return race.candidates.find((c) => c.key === pick.key)?.key ?? names.get(plain(pick.name))?.key ?? null;
}

const sameKeys = (a, b) => a.length === b.length && a.every((key, i) => key === b[i]);

// What opening ``slate`` on ``ballot`` would change: ``changes`` for Picks.merge (each race's picks,
// write-ins and notes), how many races it ``picks`` in and how many of those already had other picks
// (``replaced``), how many ``notes`` it adds, and the names of its races ``missing`` from this
// ballot. A note joins one the voter already has, under it, unless it says the same.
export function planImport(slate, ballot, picks) {
  const races = allRaces(ballot);
  const raceByKey = new Map(races.map((race) => [race.key, race]));
  const raceByName = byName(races);
  const changes = { races: {}, writeIns: {}, notes: {} };
  const found = new Map(); // the file's race key → this ballot's race
  const missing = [];
  let replaced = 0;
  let picked = 0;
  for (const entry of slate.races) {
    const race = raceByKey.get(entry.key) ?? raceByName.get(plain(entry.name));
    const names = race && byName(race.candidates);
    const keys = race ? [...new Set(entry.picks.map((pick) => candidateKey(race, pick, names)).filter(Boolean))] : [];
    if (!race || (!keys.length && !entry.write_in)) {
      missing.push(entry.name || entry.key);
      continue;
    }
    found.set(entry.key, race);
    const kept = race.ranked_choice ? keys : keys.slice(0, race.seats || 1);
    if (entry.write_in && entry.write_in !== picks.writeIn(race.key)) changes.writeIns[race.key] = entry.write_in;
    if (!kept.length) continue;
    picked += 1;
    const before = picks.picked(race.key);
    if (sameKeys(kept, before)) continue;
    changes.races[race.key] = kept;
    if (before.length) replaced += 1;
  }
  const everyone = races.flatMap((race) => race.candidates);
  let notes = 0;
  for (const note of slate.notes) {
    const race = found.get(note.race) ?? raceByKey.get(note.race) ?? raceByName.get(plain(note.race));
    const candidate = (race && (race.candidates.find((c) => c.key === note.key) ?? byName(race.candidates).get(plain(note.name))))
      ?? everyone.find((c) => c.key === note.key);
    if (!candidate) continue;
    const mine = changes.notes[candidate.key] ?? picks.note(candidate.key);
    if (mine.includes(note.text.trim())) continue;
    changes.notes[candidate.key] = mine.trim() ? `${mine.trimEnd()}\n\n${note.text.trim()}` : note.text.trim();
    notes += 1;
  }
  const changed = [changes.races, changes.writeIns, changes.notes].some((part) => Object.keys(part).length > 0);
  return { changes, picks: picked, replaced, notes, missing, changed };
}
