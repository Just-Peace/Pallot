// The print-only sheet: the voter's picks in ballot order, to take to the polls.

import { formatDate, h } from "./dom.js";
import { GROUP_LABELS, GROUP_ORDER, STATES, partyName } from "./labels.js";

function pickText(race, keys) {
  return keys
    .map((key) => race.candidates.find((c) => c.key === key))
    .filter(Boolean)
    .map((c) => {
      const party = partyName(c);
      return party && party !== "Nonpartisan" ? `${c.name} (${party})` : c.name;
    });
}

function sections(ballot) {
  const out = [];
  for (const group of GROUP_ORDER) {
    const races = ballot.races.filter((r) => r.group === group);
    if (races.length) out.push({ title: GROUP_LABELS[group], races });
  }
  for (const section of ballot.maybe) out.push({ title: `${section.title} (may not be on your ballot)`, races: section.races, maybe: true });
  return out;
}

export function buildPrintSheet(ballot, picks, { includeNotes, includeBlank }) {
  const sheet = document.getElementById("print-sheet");
  const headers = ["Race", "My pick", ...(includeNotes ? ["Note"] : [])];
  let rows = 0;

  const tables = sections(ballot).map(({ title, races, maybe }) => {
    const body = races
      .map((race) => {
        const keys = picks.picked(race.key);
        if (!keys.length && (maybe || !includeBlank)) return null;
        rows += 1;
        const notes = includeNotes ? keys.map((k) => picks.note(k)).filter(Boolean).join(" / ") : "";
        return h(
          "tr",
          {},
          h("td", {}, race.name, race.unexpired ? " (unexpired term)" : ""),
          h("td", { class: keys.length ? "" : "blank" }, keys.length ? pickText(race, keys).join("; ") : ""),
          includeNotes ? h("td", {}, notes) : null,
        );
      })
      .filter(Boolean);
    if (!body.length) return null;
    return h(
      "section",
      {},
      h("h2", {}, title),
      h("table", { class: includeNotes ? "with-notes" : null },
        h("thead", {}, h("tr", {}, headers.map((t) => h("th", {}, t)))), h("tbody", {}, body)),
    );
  });

  const measures = ballot.measures
    .map((m) => ({ m, vote: picks.picked(`measure:${m.key}`)[0] }))
    .filter(({ vote }) => vote || includeBlank)
    .map(({ m, vote }) => h("tr", {}, h("td", {}, m.title), h("td", { class: vote ? "" : "blank" }, vote ? (vote === "for" ? "For" : "Against") : "")));
  if (measures.length) {
    rows += measures.length;
    tables.push(h("section", {}, h("h2", {}, "Propositions"), h("table", { class: "measures" }, h("tbody", {}, measures))));
  }

  const state = STATES[ballot.location.state];
  const tips = state?.printTips ?? ["Bring this sheet with you: many polling places don't allow phones in the voting booth."];
  const d = ballot.districts;
  const districtLine = [
    d.cd && `U.S. House ${d.cd}`, d.sd && `State Senate ${d.sd}`, d.hd && `State House ${d.hd}`, d.sboe && `SBOE ${d.sboe}`,
    d.commissioner && `Commissioner Pct ${d.commissioner}`, d.jp && `JP Pct ${d.jp}`, d.constable && `Constable Pct ${d.constable}`,
  ].filter(Boolean).join(" · ");

  sheet.replaceChildren(
    h("header", {},
      h("h1", {}, "My ballot picks"),
      h("p", {}, [formatDate(ballot.election_date), ballot.elections.map((e) => e.name).join(" + ")].filter(Boolean).join(" · ")),
      h("p", {}, ballot.location.matched_address || ballot.location.input_address),
      districtLine ? h("p", { class: "small" }, districtLine) : null),
    ...(rows ? tables.filter(Boolean) : [h("p", {}, "No picks yet. Pick candidates on the ballot page, then print again.")]),
    h("footer", {},
      h("p", {}, tips.join(" ")),
      h("p", { class: "small" }, `Made with VoteBot on ${formatDate(new Date().toISOString())}. Unofficial: check your county's `
        + `official sample ballot${state ? ` or ${state.site.label}` : ""}.`)),
  );
}
