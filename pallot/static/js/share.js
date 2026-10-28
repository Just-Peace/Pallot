// A picks file: the picks, write-ins and notes on the ballot shown, with the names they belong to, to
// keep a copy, move them to another device or send them to someone. As a link it travels after
// "#picks=" in the address, which the browser never sends to the server, so Pallot keeps none of it.
// Both are compressed; a file is always locked, a link only with the voter's own phrase.
// Opened on a ballot, its races and candidates are found by their keys, then by their names alone
// where one name fits (a friend's ballot, or another lookup), and the rest left out.

import { ANSWERS, WRITE_IN } from "./picks.js";

export const VERSION = 1;
export const LINK_KEY = "picks";
const KIND = "pallot-picks";
const MAX_BYTES = 1_000_000; // a file or unpacked link larger than this isn't a picks file
const MAX_ENTRIES = 500;
const MAX_TEXT = 5000;
const DATED = /^\d{4}-\d{2}-\d{2}$/;

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = (value, max = 300) => (typeof value === "string" ? value.slice(0, max) : "");
const plain = (value) => String(value ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export const allRaces = (ballot) => [...ballot.races, ...ballot.maybe.flatMap((section) => section.races)];

function pickName(race, key, picks, names) {
  if (race.retention) return ANSWERS.find(([answer]) => answer === key)?.[1] ?? null;
  if (key === WRITE_IN) return picks.writeIn(race.key).trim() || "Write-in";
  return names.get(key) ?? null;
}

// The picks file of ``ballot``. ``notes``: with the voter's notes; ``address``: with the lookup's
// address or voter card, so the file or link opens the same ballot elsewhere. ``title``: the
// election line, for the person who opens it.
export function buildSlate(ballot, picks, { request = {}, title = "", notes = true, address = false } = {}) {
  const races = [];
  const kept = [];
  for (const race of allRaces(ballot)) {
    const names = new Map(race.candidates.map((c) => [c.key, c.name]));
    const chosen = picks.picked(race.key)
      .map((key) => ({ key, name: pickName(race, key, picks, names) }))
      .filter((pick) => pick.name !== null);
    const writeIn = picks.writeIn(race.key).trim();
    if (chosen.length || writeIn) races.push({ key: race.key, name: race.name, picks: chosen, ...(writeIn ? { write_in: writeIn } : {}) });
    if (!notes) continue;
    for (const candidate of race.candidates) {
      const note = picks.note(candidate.key);
      if (note.trim()) kept.push({ key: candidate.key, name: candidate.name, race: race.key, text: note });
    }
  }
  const { election_date: _date, party, all_races: _all, ...place } = request || {};
  return {
    kind: KIND,
    version: VERSION,
    election: { date: ballot.election_date, title, ...(party ? { party } : {}) },
    ...(address ? { ballot: place } : {}),
    races,
    notes: kept,
  };
}

// How many races have a pick, and how many notes there are.
export const slateCounts = (slate) => ({ races: slate.races.filter((race) => race.picks.length).length, notes: slate.notes.length });

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

// A picks file read from JSON (a file, or a link's unpacked text): checked, with anything it
// shouldn't hold dropped. Throws an Error that says what's wrong, for the voter.
export function readSlate(json) {
  let data;
  try {
    data = typeof json === "string" ? JSON.parse(json) : json;
  } catch {
    throw new Error("This isn't a Pallot picks file.");
  }
  if (!isObject(data) || data.kind !== KIND) throw new Error("This isn't a Pallot picks file.");
  if (!(Number(data.version) <= VERSION)) throw new Error("This picks file was made by a newer Pallot.");
  const election = isObject(data.election) ? data.election : {};
  const races = (Array.isArray(data.races) ? data.races : []).filter(isObject).slice(0, MAX_ENTRIES).map((race) => ({
    key: text(race.key),
    name: text(race.name),
    picks: (Array.isArray(race.picks) ? race.picks : []).filter(isObject).slice(0, 50)
      .map((pick) => ({ key: text(pick.key), name: text(pick.name) })).filter((pick) => pick.key || pick.name),
    ...(text(race.write_in).trim() ? { write_in: text(race.write_in) } : {}),
  })).filter((race) => (race.key || race.name) && (race.picks.length || race.write_in));
  const notes = (Array.isArray(data.notes) ? data.notes : []).filter(isObject).slice(0, MAX_ENTRIES).map((note) => ({
    key: text(note.key), name: text(note.name), race: text(note.race), text: text(note.text, MAX_TEXT),
  })).filter((note) => (note.key || note.name) && note.text.trim());
  const place = readPlace(data.ballot);
  return {
    kind: KIND,
    version: VERSION,
    election: {
      date: DATED.test(election.date) ? election.date : null,
      title: text(election.title),
      ...(text(election.party, 20) ? { party: text(election.party, 20) } : {}),
    },
    ...(place ? { ballot: place } : {}),
    races,
    notes,
  };
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

// Not a secret: Pallot's code is public. It keeps a picks file from reading as text to whatever
// indexes or scans it (a mail or cloud drive) and protects nothing from anyone who opens it in
// Pallot, so the voter is never told it protects anything. Only the voter's own phrase does. Never
// change it, or files locked with it no longer open.
const BUILT_IN = "pallot-picks-file-v1";
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
  const plainBytes = new Uint8Array([mark.charCodeAt(0), ...bytes]);
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plainBytes));
  return new Uint8Array([...salt, ...iv, ...sealed]);
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

// The voter's phrase: what it must have (``required``) and what's recommended, each ``met`` or not.
export function phraseRules(phrase) {
  return [
    { id: "length", text: "10 or more characters", met: [...phrase].length >= 10, required: true },
    { id: "upper", text: "A capital letter", met: /\p{Lu}/u.test(phrase), required: true },
    { id: "lower", text: "A small letter", met: /\p{Ll}/u.test(phrase), required: true },
    { id: "number", text: "A number", met: /\p{Nd}/u.test(phrase), required: true },
    { id: "special", text: "A special character, such as ! or # (recommended)", met: /[^\p{L}\p{N}\s]/u.test(phrase), required: false },
  ];
}

export const phraseReady = (phrase) => phraseRules(phrase).every((rule) => rule.met || !rule.required);

// ``slate`` as text for a link or a file, a mark then base64url: "z" or "j" as is, "b" locked with
// the built-in phrase (``hide``, for files), or "p" locked with the voter's ``phrase``. Where the
// browser can't lock (plain HTTP, not localhost), it's left as is.
async function encode(slate, { phrase = null, hide = false } = {}) {
  const [mark, bytes] = await pack(slate);
  if (phrase) return `p${toBase64Url(await lock(mark, bytes, phrase))}`;
  if (hide && canLock()) return `b${toBase64Url(await lock(mark, bytes, null))}`;
  return `${mark}${toBase64Url(bytes)}`;
}

// The slate ``value`` (encode's) holds, or null if the voter cancelled the phrase. ``askPhrase(open)``
// asks the voter for a phrase: ``open(phrase)`` resolves to the slate, or to null when the phrase
// doesn't fit; askPhrase resolves to the slate, or to null when the voter gives up. Throws an
// Error with ``unreadable`` for the voter.
async function decode(value, askPhrase, unreadable) {
  if (typeof value !== "string" || value.length > MAX_BYTES * 2) throw new Error(unreadable);
  let bytes;
  try {
    bytes = fromBase64Url(value.slice(1));
  } catch {
    throw new Error(unreadable);
  }
  const kind = value[0];
  if ((kind === "b" || kind === "p") && !canLock()) {
    throw new Error("This browser can only open these picks over HTTPS, or on the computer Pallot runs on.");
  }
  try {
    if (kind === "b") return await unpack(...await unlock(bytes, null));
    if (kind !== "p") return await unpack(kind, bytes);
  } catch (error) {
    throw error instanceof WrongPhrase || error instanceof Unreadable ? new Error(unreadable) : error;
  }
  return askPhrase(async (phrase) => {
    try {
      return await unpack(...await unlock(bytes, phrase));
    } catch (error) {
      if (error instanceof WrongPhrase) return null;
      throw error instanceof Unreadable ? new Error(unreadable) : error;
    }
  });
}

// The link to ``page`` (the ballot page's address) that carries ``slate``, locked with ``phrase`` if given.
export async function slateLink(slate, page, phrase = null) {
  const url = new URL(page);
  url.hash = `${LINK_KEY}=${await encode(slate, { phrase })}`;
  return url.href;
}

export const slateFromLink = (value, askPhrase) => decode(value, askPhrase, "This link's picks couldn't be read. Ask for the link again.");

// A picks file's text: always locked, with the voter's ``phrase`` or else the built-in one.
export async function picksFile(slate, phrase = null) {
  return JSON.stringify({ kind: KIND, version: VERSION, data: await encode(slate, { phrase, hide: true }) }, null, 2);
}

// The slate a picks file holds, or null if the voter cancelled the phrase. A file written out by
// hand as a slate is read as one.
export async function readPicksFile(text, askPhrase) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("This isn't a Pallot picks file.");
  }
  if (!isObject(data) || data.kind !== KIND) throw new Error("This isn't a Pallot picks file.");
  if (!(Number(data.version) <= VERSION)) throw new Error("This picks file was made by a newer Pallot.");
  return typeof data.data === "string" ? decode(data.data, askPhrase, "This picks file couldn't be read.") : readSlate(data);
}

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
