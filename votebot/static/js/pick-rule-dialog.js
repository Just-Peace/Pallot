// The Pick by rule dialog: the voter sets a rule (pick-rules.js), sees race by race what it
// would change, then applies it (with Undo) or marks who matches on the ballot. Opened from the
// strip for every race, or from a race's funnel for that race. ballot.js hands over ``page``.

import { pickLabels } from "./ballot-shared.js";
import { $, closeOnBackdrop, dialogHead, h } from "./dom.js";
import { COUNT, plural } from "./format.js";
import { icon } from "./icons.js";
import {
  MONEY, WRITE_INS, allRaces, available, ballotParties, loadRule, parseAmount, plan, saveRule, scopes, verdicts,
} from "./pick-rules.js";
import { showToast } from "./toast.js";

let page = null; // { ballot, picks, marks, renderRaces }
const dialog = $("#rules");

export function initRules(context) {
  page = context;
  closeOnBackdrop(dialog);
}

function setMarking(on) {
  const rule = loadRule();
  rule.mark = on;
  saveRule(rule);
  page.renderRaces();
}

export const markingNote = h("p", { class: "notice", hidden: true },
  "Candidates your rule would pick are marked ✓, and those it skips ✕. ",
  h("button", { type: "button", class: "link-btn", on: { click: () => openRules() } }, "Change the rule"),
  " · ",
  h("button", { type: "button", class: "link-btn", on: { click: () => setMarking(false) } }, "Stop marking"));

// The marks on the candidates (``page.marks``) from the saved rule, and the note above the races.
export function syncMarks() {
  const rule = loadRule();
  page.marks = rule.mark && page.ballot ? verdicts(page.ballot, rule) : null;
  markingNote.hidden = !page.marks;
}

// ---- the controls ---------------------------------------------------------------------

const NO_DATA = "no data on your ballot";

// A checkbox and its label, then ``extra`` (the amount boxes it goes with).
// ``stacked``: the boxes on a line of their own, under the label.
function checkRow(label, checked, onChange, { disabled = false, extra = null, stacked = false } = {}) {
  const box = h("input", { type: "checkbox", checked, disabled, on: { change: (event) => onChange(event.target.checked) } });
  return h("div", { class: ["rule-row", disabled && "disabled", stacked && "stacked"] },
    h("label", { class: "check" }, box, h("span", {}, label, disabled ? h("span", { class: "muted" }, ` (${NO_DATA})`) : null)),
    extra ? h("div", { class: "rule-inputs" }, extra) : null);
}

// A box for an amount ("1M", "250,000"): its number goes to ``set``, or NaN while it isn't one.
function amountBox(value, set, { label, prefix = "$", suffix = "", disabled = false }) {
  const box = h("input", {
    type: "text", inputmode: "decimal", class: "rule-amount", value: Number.isFinite(value) ? COUNT.format(value) : "", disabled, "aria-label": label,
    on: {
      input: (event) => {
        const amount = parseAmount(event.target.value);
        event.target.setAttribute("aria-invalid", String(amount === null));
        set(amount === null ? NaN : amount);
      },
    },
  });
  return h("span", { class: "rule-amount-wrap" }, prefix ? h("span", { "aria-hidden": "true" }, prefix) : null, box,
    suffix ? h("span", { "aria-hidden": "true" }, suffix) : null);
}

function select(label, options, value, onChange, { disabled = false } = {}) {
  return h("select", { "aria-label": label, disabled, on: { change: (event) => onChange(event.target.value) } },
    options.map(([id, text, off]) => h("option", { value: id, selected: id === value, disabled: Boolean(off) }, text)));
}

// ---- the preview ----------------------------------------------------------------------

function summary(result, active) {
  const parts = [
    result.picked ? `Picks ${plural(result.picked, "race")}` : null,
    result.takenBack ? `takes back ${plural(result.takenBack, "pick")}` : null,
    result.many ? `${COUNT.format(result.many)} left for you (more matches than seats)` : null,
    result.kept ? `${COUNT.format(result.kept)} already picked, kept` : null,
    result.same ? `${COUNT.format(result.same)} already picked that way` : null,
    result.none ? `${COUNT.format(result.none)} with no match` : null,
  ].filter(Boolean);
  if (parts.length) return `${parts.join(" · ")}.`;
  return active ? "Nothing to change in these races." : "Choose a party or a condition above.";
}

function raceLine(row) {
  const { race, outcome } = row;
  const names = (keys) => pickLabels(race, keys, page.picks, { unnamed: "Write-in" }).join(", ");
  const what = {
    pick: `✓ ${names(row.after)}`,
    same: `already ✓ ${names(row.after)}`,
    kept: `keeps your pick, ${names(row.after)}`,
    many: `${row.matches.length} match (${row.matches.map((c) => c.name).join(", ")}): left for you`,
    none: "no match",
  }[outcome];
  const back = row.takenBack.map(({ key, reasons }) => `takes back ${names([key])} (${reasons.join(", ")})`);
  return h("li", { class: ["rule-race", `rule-${outcome || "back"}`] },
    h("span", { class: "rule-race-name" }, race.name), " ", [what, ...back].filter(Boolean).join(" · "));
}

// ---- the dialog -----------------------------------------------------------------------

// ``raceKey``: the race whose funnel opened it, which is then where the rule applies.
export function openRules(raceKey = null) {
  if (!page.ballot) return;
  const rule = loadRule();
  const options = scopes(page.ballot, raceKey);
  let scope = options[0];
  const everything = allRaces(page.ballot);
  const parties = ballotParties(everything);
  rule.parties = rule.parties.filter((code) => parties.some((p) => p.code === code)); // no chip to clear the others
  const has = available(everything);
  let result = null;

  const summaryLine = h("p", { class: "rule-summary", "aria-live": "polite" });
  const raceList = h("ul", { class: "rule-races" });
  const raceDetails = h("details", { class: "rule-details" }, h("summary", {}, "Race by race"), raceList);
  const applyButton = h("button", { type: "button", class: "btn primary", on: { click: apply } });

  const chips = parties.map((party) => {
    const chip = h("button", {
      type: "button", class: "rule-party", "data-party": party.code === WRITE_INS ? null : party.code,
      "aria-pressed": String(rule.parties.includes(party.code)),
      on: {
        click: () => {
          const on = !rule.parties.includes(party.code);
          rule.parties = on ? [...rule.parties, party.code] : rule.parties.filter((code) => code !== party.code);
          chip.setAttribute("aria-pressed", String(on));
          update();
        },
      },
    }, h("span", { class: "rule-swatch", "aria-hidden": "true" }), party.label, h("span", { class: "rule-count" }));
    return { party, chip };
  });

  function update() {
    const races = scope.races;
    for (const { party, chip } of chips) {
      const count = races.filter((r) => r.candidates.some((c) => (c.write_in ? WRITE_INS : c.party) === party.code)).length;
      chip.lastChild.textContent = String(count);
      chip.title = `${party.label}: in ${plural(count, "race")} here`;
    }
    result = plan(races, rule, page.picks);
    const active = result.rows.some((row) => row.outcome);
    summaryLine.textContent = summary(result, active);
    raceList.replaceChildren(...result.rows.map(raceLine));
    raceDetails.hidden = !result.rows.length;
    raceDetails.open = races.length === 1;
    applyButton.disabled = !result.changed;
    applyButton.textContent = result.changed ? `Apply to ${plural(result.changed, "race")}` : "Nothing to change";
  }

  function apply() {
    const changes = Object.fromEntries(result.rows.filter((row) => row.changed).map((row) => [row.race.key, row.after]));
    const { picked, takenBack } = result;
    saveRule(rule);
    const before = page.picks.setMany(changes);
    dialog.close();
    page.renderRaces();
    const did = [picked ? `picked ${plural(picked, "race")}` : null, takenBack ? `took back ${plural(takenBack, "pick")}` : null];
    showToast(`Your rule ${did.filter(Boolean).join(" and ")}.`, {
      label: "Undo",
      run: () => {
        page.picks.setMany(before);
        page.renderRaces();
      },
    });
  }

  function mark() {
    rule.mark = true;
    saveRule(rule);
    dialog.close();
    page.renderRaces();
    showToast("Candidates who match your rule are marked on your ballot.");
  }

  const scopeSelect = h("select", { id: "rule-scope", on: { change: (event) => {
    scope = options.find((o) => o.id === event.target.value);
    update();
  } } }, options.map((o) => h("option", { value: o.id, selected: o === scope }, o.label)));

  const moneyOff = !Object.values(has.money).some(Boolean);
  const moneyInputs = [
    select("Which money", MONEY.map(([id, label]) => [id, label, !has.money[id]]), rule.money.metric,
      (value) => { rule.money.metric = value; update(); }, { disabled: moneyOff }),
    select("Under or over", [["under", "under"], ["over", "over"]], rule.money.compare,
      (value) => { rule.money.compare = value; update(); }, { disabled: moneyOff }),
    amountBox(rule.money.amount, (amount) => { rule.money.amount = amount; update(); }, { label: "Amount in dollars", disabled: moneyOff }),
  ];

  const pickSet = h("fieldset", { class: "rule-set" },
    h("legend", {}, "Pick"),
    chips.length
      ? h("div", { class: "rule-parties", role: "group", "aria-label": "Parties" }, chips.map((c) => c.chip))
      : h("p", { class: "muted" }, "No candidate on your ballot has a party."),
    h("p", { class: "fine" }, "Any of the parties you choose, or anyone without one chosen. Then, only if all these hold:"),
    h("div", { class: "rule-row" },
      h("label", { class: "rule-label", for: "rule-incumbent" }, "Incumbent"),
      h("div", { class: "rule-inputs" },
        h("select", { id: "rule-incumbent", on: { change: (event) => { rule.incumbent = event.target.value; update(); } } },
          [["any", "Incumbent or not"], ["yes", "Only incumbents"], ["no", "Only challengers"]].map(([value, text]) =>
            h("option", { value, selected: value === rule.incumbent }, text))))),
    checkRow("TrackAIPAC endorses them", rule.endorsed, (on) => { rule.endorsed = on; update(); }, { disabled: !has.trackaipac }),
    checkRow("Their money is", rule.money.on, (on) => { rule.money.on = on; update(); }, { disabled: moneyOff, extra: moneyInputs, stacked: true }),
    checkRow("They lead the polls", rule.leads, (on) => { rule.leads = on; update(); }, { disabled: !has.polls }));

  const skipSet = h("fieldset", { class: "rule-set" },
    h("legend", {}, "Don't pick, and take back"),
    checkRow("On TrackAIPAC's watchlist", rule.watchlist, (on) => { rule.watchlist = on; update(); }, { disabled: !has.trackaipac }),
    checkRow("Israel lobby money over", rule.lobby.on, (on) => { rule.lobby.on = on; update(); }, {
      disabled: !has.lobby,
      extra: amountBox(rule.lobby.amount, (amount) => { rule.lobby.amount = amount; update(); },
        { label: "Israel lobby money, in dollars", disabled: !has.lobby }),
    }),
    checkRow("Polling under", rule.polling.on, (on) => { rule.polling.on = on; update(); }, {
      disabled: !has.polls,
      extra: amountBox(rule.polling.amount, (amount) => { rule.polling.amount = amount; update(); },
        { label: "Poll share, in percent", prefix: "", suffix: "%", disabled: !has.polls }),
    }));

  const { head } = dialogHead(dialog, h("div", { class: "details-title" },
    h("h2", { id: "rules-title" }, "Pick by rule"),
    h("p", { class: "muted" }, "Pick by party, TrackAIPAC, money and polls. Nothing changes until you press Apply.")));
  dialog.replaceChildren(
    head,
    h("div", { class: "rule-body" },
      h("div", { class: "rule-row" }, h("label", { class: "rule-label", for: "rule-scope" }, "Apply to"),
        h("div", { class: "rule-inputs" }, scopeSelect)),
      pickSet,
      skipSet,
      checkRow("Don't replace picks I've already made", rule.keepMine, (on) => { rule.keepMine = on; update(); }),
      h("p", { class: "fine" },
        "A condition counts only in races its source covers: money in congressional and state races, TrackAIPAC in "
        + "congressional races, polls in U.S. Senate, U.S. House and Governor races. Without the Write-ins chip, a rule "
        + "picks only the names printed on the ballot. If more candidates match than a race has seats, it's left for you."),
      h("div", { class: "rule-preview" }, summaryLine, raceDetails)),
    h("div", { class: "details-foot" },
      h("button", { type: "button", class: "btn ghost", on: { click: () => dialog.close() } }, "Cancel"),
      h("button", { type: "button", class: "btn with-icon", on: { click: mark } }, icon("filter"), "Mark who matches"),
      applyButton),
  );
  update();
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
  scopeSelect.focus();
}
