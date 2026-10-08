// The Pick by rule dialog: the voter sets a rule (pick-rules.js), sees in words and race by race
// what it would change, then applies it (with Undo). Opened
// from the strip for every race, or from a race's funnel for that race. ballot.js hands over ``page``.

import { pickLabels } from "./ballot-shared.js";
import { $, closeOnBackdrop, dialogHead, h } from "./dom.js";
import { COUNT, listed, plural } from "./format.js";
import { icon } from "./icons.js";
import {
  DEFAULT_RULE, MONEY, WRITE_INS, allRaces, available, ballotParties, describeRule, loadRule, parseAmount, plan, saveRule, scopes,
} from "./pick-rules.js";
import { showToast } from "./toast.js";
import { viewPref } from "./view.js";

let page = null; // { ballot, picks, renderRaces }
const dialog = $("#rules");

export function initRules(context) {
  page = context;
  closeOnBackdrop(dialog);
}

// ---- the controls ---------------------------------------------------------------------

// A checkbox and its label, then ``extra`` (the amount boxes it goes with).
// ``stacked``: the boxes on a line of their own, under the label.
function checkRow(label, checked, onChange, { extra = null, stacked = false } = {}) {
  const box = h("input", { type: "checkbox", checked, on: { change: (event) => onChange(event.target.checked) } });
  return h("div", { class: ["rule-row", stacked && "stacked"] },
    h("label", { class: "check" }, box, h("span", {}, label)),
    extra ? h("div", { class: "rule-inputs" }, extra) : null);
}

// A chip that toggles (a party, an endorsement list). ``party``: its code, for its colour and a
// swatch ("" for a swatch with no colour); ``count``: room for a number after the label.
function chip(label, pressed, onToggle, { party = null, count = false } = {}) {
  const button = h("button", {
    type: "button", class: "rule-chip", "data-party": party || null, "aria-pressed": String(pressed),
    on: {
      click: () => {
        const on = button.getAttribute("aria-pressed") !== "true";
        button.setAttribute("aria-pressed", String(on));
        onToggle(on);
      },
    },
  }, party !== null ? h("span", { class: "rule-swatch", "aria-hidden": "true" }) : null, label,
  count ? h("span", { class: "rule-count" }) : null);
  return button;
}

// A box for an amount ("1M", "250,000"): its number goes to ``set``, or NaN while it isn't one.
function amountBox(value, set, { label, prefix = "$", suffix = "" }) {
  const box = h("input", {
    type: "text", inputmode: "decimal", class: "rule-amount", value: Number.isFinite(value) ? COUNT.format(value) : "", "aria-label": label,
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

function select(label, options, value, onChange) {
  return h("select", { "aria-label": label, on: { change: (event) => onChange(event.target.value) } },
    options.map(([id, text, off]) => h("option", { value: id, selected: id === value, disabled: Boolean(off) }, text)));
}

// A heading's conditions, inside Pick; nothing when none of them has data on this ballot.
function group(title, ...rows) {
  const shown = rows.filter(Boolean);
  return shown.length ? h("fieldset", { class: "rule-sub" }, h("legend", {}, title), shown) : null;
}

// ---- the preview ----------------------------------------------------------------------

// What the rule would do: a count from plan(), its words, and its colour.
const TALLIES = [
  ["picked", (n) => `${n === 1 ? "race" : "races"} to pick`, "good"],
  ["takenBack", (n) => `${n === 1 ? "pick" : "picks"} taken back`, "warn"],
  ["many", () => "left for you, with more matches than seats", ""],
  ["kept", () => "already picked, kept", ""],
  ["same", () => "already picked that way", ""],
  ["none", () => "with no match", "muted"],
];

function tallies(result, active) {
  const items = TALLIES.filter(([id]) => result[id]).map(([id, words, tone]) =>
    h("li", { class: ["rule-tally", tone && `tone-${tone}`] }, h("strong", {}, COUNT.format(result[id])), " ", words(result[id])));
  if (items.length) return items;
  return [h("li", { class: "rule-tally muted" }, active ? "Nothing to change in these races." : "Choose a party or a condition.")];
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
    h("span", { class: "rule-race-name" }, race.name), h("span", {}, [what, ...back].filter(Boolean).join(" · ")));
}

// ---- the dialog -----------------------------------------------------------------------

const WIDE = matchMedia("(min-width: 800px)"); // the preview beside the rule, with room to list the races

// ``raceKey``: the race whose funnel opened it, which is then where the rule applies.
export function openRules(raceKey = null) {
  if (!page.ballot || page.loadingCards) return; // its conditions are about the cards
  const options = scopes(page.ballot, raceKey);
  draw(loadRule(), options, options[0]);
  if (!dialog.open) dialog.showModal();
  $("#rule-scope").focus();
}

// Draws the dialog for ``rule``, which is saved only by Apply. Reset draws
// it again with the default rule, in the same scope.
function draw(rule, options, startScope) {
  let scope = startScope;
  const everything = allRaces(page.ballot);
  const parties = ballotParties(everything);
  rule.parties = rule.parties.filter((code) => parties.some((p) => p.code === code)); // no chip to clear the others
  const has = available(everything);
  let result = null;

  const noWords = h("p", { class: "rule-words muted" }, "No rule yet: choose a party or a condition.");
  const pickWords = h("p", { class: "rule-words tone-good" });
  const skipWords = h("p", { class: "rule-words tone-warn" });
  const tallyList = h("ul", { class: "rule-tallies", "aria-live": "polite" });
  const raceList = h("ul", { class: "rule-races" });
  const raceCount = h("span", { class: "rule-count" });
  const raceDetails = h("details", { class: "rule-details" }, h("summary", {}, "Race by race ", raceCount), raceList);
  const applyButton = h("button", { type: "button", class: "btn primary", on: { click: apply } });
  // An onChange that changes the rule, then the preview.
  const set = (change) => (value) => {
    change(value);
    update();
  };

  const partyChips = parties.map((party) => ({
    party,
    chip: chip(party.label, rule.parties.includes(party.code), set((on) => {
      rule.parties = on ? [...rule.parties, party.code] : rule.parties.filter((code) => code !== party.code);
    }), { party: party.code === WRITE_INS ? "" : party.code, count: true }),
  }));

  function update() {
    const races = scope.races;
    for (const { party, chip: button } of partyChips) {
      const count = races.filter((r) => r.candidates.some((c) => (c.write_in ? WRITE_INS : c.party) === party.code)).length;
      button.lastChild.textContent = String(count);
      button.title = `${party.label}: in ${plural(count, "race")} here`;
    }
    const words = describeRule(rule, parties, has);
    pickWords.textContent = words.pick || "";
    skipWords.textContent = words.skip || "";
    pickWords.hidden = !words.pick;
    skipWords.hidden = !words.skip;
    noWords.hidden = Boolean(words.pick || words.skip);
    result = plan(races, rule, page.picks);
    tallyList.replaceChildren(...tallies(result, result.rows.some((row) => row.outcome)));
    raceList.replaceChildren(...result.rows.map(raceLine));
    raceCount.textContent = String(result.rows.length);
    raceDetails.hidden = !result.rows.length;
    applyButton.disabled = !result.changed;
    applyButton.textContent = result.changed ? `Apply to ${plural(result.changed, "race")}` : "Nothing to change";
  }

  // With "Collapse a race when I pick" on, the races it fills fold, as a pick by hand does; Undo opens them again.
  function apply() {
    const changed = result.rows.filter((row) => row.changed);
    const changes = Object.fromEntries(changed.map((row) => [row.race.key, row.after]));
    const folded = viewPref("collapseOnPick")
      ? changed.filter((row) => row.outcome === "pick" && row.after.length >= row.race.seats && !page.picks.isCollapsed(row.race.key))
        .map((row) => row.race.key)
      : [];
    const { picked, takenBack } = result;
    saveRule(rule);
    const before = page.picks.setMany(changes);
    if (folded.length) page.picks.setCollapsed(folded, true);
    dialog.close();
    page.renderRaces();
    const did = [picked ? `picked ${plural(picked, "race")}` : null, takenBack ? `took back ${plural(takenBack, "pick")}` : null];
    showToast(`Your rule ${did.filter(Boolean).join(" and ")}.`, {
      label: "Undo",
      run: () => {
        page.picks.setMany(before);
        if (folded.length) page.picks.setCollapsed(folded, false);
        page.renderRaces();
      },
    });
  }

  function reset() {
    draw(structuredClone(DEFAULT_RULE), options, scope);
    $("#rule-reset").focus();
  }

  const openList = () => {
    raceDetails.open = scope.races.length === 1 || WIDE.matches;
  };
  const scopeSelect = h("select", { id: "rule-scope", on: { change: (event) => {
    scope = options.find((o) => o.id === event.target.value);
    openList();
    update();
  } } }, options.map((o) => h("option", { value: o.id, selected: o === scope }, o.label)));

  const moneyOn = Object.values(has.money).some(Boolean);
  const moneyAmount = amountBox(rule.money.amount, set((amount) => { rule.money.amount = amount; }), { label: "Amount in dollars" });
  const relative = (compare) => compare === "least" || compare === "most";
  moneyAmount.hidden = relative(rule.money.compare);
  const moneyInputs = [
    select("Which money", MONEY.map(([id, label]) => [id, label, !has.money[id]]), rule.money.metric,
      set((value) => { rule.money.metric = value; })),
    select("Compared with what", [["under", "under"], ["over", "over"], ["least", "the least"], ["most", "the most"]],
      rule.money.compare, set((value) => {
        rule.money.compare = value;
        moneyAmount.hidden = relative(value);
      })),
    moneyAmount,
  ];
  const percentBox = (key, label) =>
    amountBox(rule[key].amount, set((amount) => { rule[key].amount = amount; }), { label, prefix: "", suffix: "%" });
  const sign = (text) => h("span", { class: "rule-sign", "aria-hidden": "true" }, text);

  const pickSet = h("fieldset", { class: "rule-set rule-set-pick" },
    h("legend", {}, sign("✓"), "Pick"),
    h("p", { class: "rule-hint" }, "Candidates who meet every condition you turn on."),
    h("fieldset", { class: "rule-sub" }, h("legend", {}, "Party"),
      partyChips.length
        ? [h("div", { class: "rule-chips" }, partyChips.map((c) => c.chip)),
          h("p", { class: "fine" }, "Any of the parties you choose. With none chosen, every party.")]
        : h("p", { class: "muted" }, "No candidate on your ballot has a party.")),
    h("fieldset", { class: "rule-sub" }, h("legend", {}, "Incumbent or challenger"),
      h("div", { class: "seg" }, [["any", "Either"], ["yes", "Incumbents"], ["no", "Challengers"]].map(([value, text]) =>
        h("label", { class: "seg-option" },
          h("input", { type: "radio", name: "rule-incumbent", value, checked: value === rule.incumbent,
            on: { change: set(() => { rule.incumbent = value; }) } }), text)))),
    group("Endorsements",
      has.endorsers.length && [
        h("div", { class: "rule-chips" }, has.endorsers.map(({ source, label }) =>
          chip(label, rule.endorsedBy.includes(source), set((on) => {
            rule.endorsedBy = [...rule.endorsedBy.filter((id) => id !== source), ...(on ? [source] : [])];
          })))),
        h("p", { class: "fine" }, "Endorsements from any of the ones you choose.",
          has.endorsers.some((e) => e.source === "voteforpeace") ? " Vote for Peace counts the candidates it rates an ally." : ""),
      ]),
    group("Money",
      moneyOn && checkRow("Their money is", rule.money.on, set((on) => { rule.money.on = on; }), { extra: moneyInputs, stacked: true }),
      has.small && checkRow("Small donations make up at least", rule.small.on, set((on) => { rule.small.on = on; }),
        { extra: percentBox("small", "Small donations' share of what they raised, in percent") }),
      has.texas && checkRow("Texas donors make up at least", rule.texas.on, set((on) => { rule.texas.on = on; }),
        { extra: percentBox("texas", "Texas donors' share of itemized donations, in percent") })),
    group("Polls", has.polls && checkRow("They lead the polls", rule.leads, set((on) => { rule.leads = on; }))));

  const skipRows = [
    has.trackaipac && checkRow("On TrackAIPAC's watchlist", rule.watchlist, set((on) => { rule.watchlist = on; })),
    has.voteforpeace && checkRow("Vote for Peace opposes them", rule.peaceOpposed, set((on) => { rule.peaceOpposed = on; })),
    has.lobby && checkRow("Israel lobby money over", rule.lobby.on, set((on) => { rule.lobby.on = on; }),
      { extra: amountBox(rule.lobby.amount, set((amount) => { rule.lobby.amount = amount; }), { label: "Israel lobby money, in dollars" }) }),
    has.selfFunded && checkRow("Their own money makes up over", rule.selfFunded.on, set((on) => { rule.selfFunded.on = on; }),
      { extra: percentBox("selfFunded", "The candidate's own gifts and loans, in percent of what the campaign raised") }),
    has.polls && checkRow("Polling under", rule.polling.on, set((on) => { rule.polling.on = on; }),
      { extra: percentBox("polling", "Poll share, in percent") }),
  ].filter(Boolean);
  const skipSet = h("fieldset", { class: "rule-set rule-set-skip" },
    h("legend", {}, sign("✕"), "Don't pick, and take back"),
    h("p", { class: "rule-hint" }, "Anyone who meets any one of these, even if you picked them yourself."),
    skipRows.length ? skipRows : h("p", { class: "muted" }, "Your ballot has nothing for these to go on."));

  const missing = [
    !has.trackaipac && "TrackAIPAC", !has.voteforpeace && "Vote for Peace", !moneyOn && "money",
    moneyOn && !has.small && "small donations", moneyOn && !has.texas && "Texas donors", moneyOn && !has.selfFunded && "self-funding", !has.lobby && "Israel lobby money",
    !has.polls && "polls",
  ].filter(Boolean);

  const { head } = dialogHead(dialog, h("div", { class: "details-title" },
    h("h2", { id: "rules-title" }, "Pick by rule"),
    h("p", { class: "muted" }, "Choose who to pick and who to skip. Nothing changes until you press Apply.")));
  dialog.replaceChildren(
    head,
    h("div", { class: "rule-bar" },
      h("label", { class: "rule-label", for: "rule-scope" }, "Apply to"), scopeSelect,
      h("button", { type: "button", id: "rule-reset", class: "link-btn rule-reset", on: { click: reset } }, icon("reset"), "Reset")),
    h("div", { class: "rule-layout" },
      h("div", { class: "rule-form" },
        pickSet,
        skipSet,
        missing.length ? h("p", { class: "fine" }, `Not offered, since nothing on your ballot has them: ${listed(missing)}.`) : null,
        h("details", { class: "rule-how" }, h("summary", {}, "How rules work"),
          h("p", {}, "Pick takes the candidates who meet every condition you turn on, from any party you choose, with endorsements "
            + "from any of the endorsers you choose. Don't pick "
            + "takes back anyone who meets any one of its conditions, even a pick you made yourself."),
          h("p", {}, "A condition counts only in races its source covers: money in congressional and state races, TrackAIPAC in "
            + "congressional races, Vote for Peace in the races where it rates someone, an endorsement list in the races where it "
            + "endorses someone, polls in U.S. Senate, U.S. House and Governor races. So “Democrats who spent under $1M” "
            + "still picks a county race's Democrat. “The least” and “the most” compare the candidates in each race. Small "
            + "donations (under $500) and Texas donors (their share of itemized donations with an address) are known in "
            + "congressional races with an FEC key, and in state races from the Texas Ethics Commission. Self-funding is known "
            + "only in congressional races, with an FEC key."),
          h("p", {}, "Without the Write-ins chip, a rule picks only the names printed on the ballot. If more candidates match than "
            + "a race has seats, a tie included, it's left for you."))),
      h("aside", { class: "rule-preview", "aria-label": "What your rule would do" },
        h("h3", {}, "Your rule"),
        noWords, pickWords, skipWords,
        h("h3", {}, "What it would do"),
        tallyList,
        checkRow("Don't replace picks I've already made", rule.keepMine, set((on) => { rule.keepMine = on; })),
        raceDetails)),
    h("div", { class: "details-foot" },
      h("button", { type: "button", class: "btn ghost", on: { click: () => dialog.close() } }, "Cancel"),
      applyButton),
  );
  openList();
  update();
}
