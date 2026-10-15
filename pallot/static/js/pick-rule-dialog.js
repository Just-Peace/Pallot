// The More conditions dialog: the voter sets conditions (the rule, pick-rules.js), sees in words and
// race by race what they would change, then applies them (with Undo, and a banner above the races),
// filling in only the races without a pick or replacing the voter's picks too. Its endorser chips and
// its TrackAIPAC and Vote for Peace rows are Help me pick's Trust and Avoid choices, saved with the
// rule. Opened from Help me pick's More conditions…; Apply to chooses every race, a section or one
// race. ballot.js hands over ``page``.

import { pickLabels } from "./ballot-shared.js";
import { $, closeOnBackdrop, dialogHead, h } from "./dom.js";
import { COUNT, plural } from "./format.js";
import { helpLink } from "./help.js";
import { icon } from "./icons.js";
import {
  DEFAULT_RULE, MONEY, UNBACKED, WRITE_INS, allRaces, available, ballotParties, describeRule, loadRule, parseAmount, plan, saveRule, scopes,
} from "./pick-rules.js";
import { hideToast, showToast } from "./toast.js";
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

// A chip that toggles (a party, an endorser). ``party``: its code, for its colour and a swatch (""
// for a swatch with no colour); ``count``: the number after the label ("" to fill in later).
function chip(label, pressed, onToggle, { party = null, count = null, title = null } = {}) {
  const button = h("button", {
    type: "button", class: "rule-chip", "data-party": party || null, "aria-pressed": String(pressed), title,
    on: {
      click: () => {
        const on = button.getAttribute("aria-pressed") !== "true";
        button.setAttribute("aria-pressed", String(on));
        onToggle(on);
      },
    },
  }, party !== null ? h("span", { class: "rule-swatch", "aria-hidden": "true" }) : null, label,
  count !== null ? h("span", { class: "rule-count" }, String(count)) : null);
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

// What the rule would do: a count from plan(), its words (given the count and plan()'s result), and its colour.
const TALLIES = [
  ["picked", (n) => `${n === 1 ? "race" : "races"} to pick`, "good"],
  ["takenBack", (n, result) => `${n === 1 ? "pick" : "picks"} taken back${result.unbacked === n ? ` (${UNBACKED})` : ""}`, "warn"],
  ["many", () => "left for you, with more matches than seats", ""],
  ["kept", () => "already picked, kept", ""],
  ["same", () => "already picked that way", ""],
  ["none", () => "with no match", "muted"],
];

function tallies(result, active) {
  const items = TALLIES.filter(([id]) => result[id]).map(([id, words, tone]) =>
    h("li", { class: ["rule-tally", tone && `tone-${tone}`] }, h("strong", {}, COUNT.format(result[id])), " ", words(result[id], result)));
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

// ---- the banner -----------------------------------------------------------------------

// After Fill in the rest or Replace my picks, one line above the races says the rule in words, with
// Edit and Undo (the toast's Undo, kept). It goes once the picks are cleared, the rule changes (here,
// in Help me pick or in another tab) or the ballot is drawn again; Undo and ✕ take it away too.
const banner = $("#rule-banner");
let shownRule = null; // the rule the banner shows, as saved
const ruleKey = (rule) => JSON.stringify({ ...rule, onlyMatches: null }); // Only races with a match is a view, not the rule

function showBanner(words, undo) {
  shownRule = ruleKey(loadRule());
  banner.replaceChildren(
    h("p", {}, h("strong", {}, "Picked by your conditions: "), [words.pick, words.skip].filter(Boolean).join(" ")),
    h("p", { class: "rule-banner-actions" },
      h("button", { type: "button", class: "link-btn", on: { click: () => openRules() } }, "Edit"),
      h("button", { type: "button", class: "link-btn", on: { click: () => {
        hideToast();
        undo();
      } } }, "Undo")),
    h("button", { type: "button", class: "icon-btn close", "aria-label": "Close this line", on: { click: hideBanner } }, "✕"));
  banner.hidden = false;
}

export function hideBanner() {
  shownRule = null;
  banner.hidden = true;
  banner.replaceChildren();
}

// After the picks change as a whole: the banner goes once the saved rule isn't its own (ballot.js
// takes it away when the picks are cleared).
export function syncRuleBanner() {
  if (shownRule && ruleKey(loadRule()) !== shownRule) hideBanner();
}

// "Vote for Peace is off. Turn it on in Settings.", each name linking to its switch there.
function offLine(sources) {
  if (!sources.length) return [];
  const one = sources.length === 1;
  const toggle = (id) => `settings.html#toggle-${encodeURIComponent(id)}`;
  const names = sources.flatMap((s, i) => [
    i ? (i === sources.length - 1 ? " and " : ", ") : "", h("a", { href: toggle(s.id) }, s.label)]);
  return [...names, one ? " is off. Turn it on in " : " are off. Turn them on in ",
    h("a", { href: one ? toggle(sources[0].id) : "settings.html#sources-title" }, "Settings"), "."];
}

// ---- the dialog -----------------------------------------------------------------------

const WIDE = matchMedia("(min-width: 800px)"); // the preview beside the rule, with room to list the races

export function openRules() {
  if (!page.ballot || page.loadingCards) return; // its conditions are about the cards
  const options = scopes(page.ballot);
  draw(loadRule(), options, options[0]);
  if (!dialog.open) dialog.showModal();
  $("#rule-scope").focus();
}

// Draws the dialog for ``rule``, which is saved only by Fill in the rest, Replace my picks or Save
// choices. Reset draws it again with the default rule (Only races with a match kept), in the same scope.
function draw(rule, options, startScope) {
  let scope = startScope;
  const everything = allRaces(page.ballot);
  const parties = ballotParties(everything);
  const onBallot = (code) => parties.some((p) => p.code === code); // no chip to clear the others
  rule.parties = rule.parties.filter(onBallot);
  const saved = loadRule();
  saved.parties = saved.parties.filter(onBallot);
  const sameSet = (r) => JSON.stringify({ ...r, parties: [...r.parties].sort(), endorsedBy: [...r.endorsedBy].sort() });
  const unsaved = () => sameSet(rule) !== sameSet(saved);
  const has = available(everything);
  let fill = null;
  let replace = null;

  const noWords = h("p", { class: "rule-words muted" }, "No conditions yet: choose a party or a condition.");
  const pickWords = h("p", { class: "rule-words tone-good" });
  const skipWords = h("p", { class: "rule-words tone-warn" });
  const tallyList = h("ul", { class: "rule-tallies", "aria-live": "polite" });
  const raceList = h("ul", { class: "rule-races" });
  const raceCount = h("span", { class: "rule-count" });
  const raceDetails = h("details", { class: "rule-details" }, h("summary", {}, "Race by race ", raceCount), raceList);
  const replaceNote = h("p", { class: "fine" });
  const fillButton = h("button", { type: "button", class: "btn primary",
    title: "Picks only in the races where you haven't picked", on: { click: () => apply(fill) } });
  const replaceButton = h("button", { type: "button", class: "btn",
    title: "Picks in every race it matches, replacing your own picks there too", on: { click: () => apply(replace) } });
  // An onChange that changes the rule, then the preview.
  const set = (change) => (value) => {
    change(value);
    update();
  };

  const partyChips = parties.map((party) => ({
    party,
    chip: chip(party.label, rule.parties.includes(party.code), set((on) => {
      rule.parties = on ? [...rule.parties, party.code] : rule.parties.filter((code) => code !== party.code);
    }), { party: party.code === WRITE_INS ? "" : party.code, count: "" }),
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
    fill = plan(races, rule, page.picks);
    replace = plan(races, rule, page.picks, { replace: true });
    tallyList.replaceChildren(...tallies(fill, fill.rows.some((row) => row.outcome)));
    raceList.replaceChildren(...fill.rows.map(raceLine));
    raceCount.textContent = String(fill.rows.length);
    raceDetails.hidden = !fill.rows.length;
    replaceNote.textContent = replace.changed > fill.changed
      ? `Replace my picks would change ${plural(replace.changed, "race")}, your own picks included.` : "";
    replaceNote.hidden = !replaceNote.textContent;
    const saveOnly = !fill.changed && unsaved();
    fillButton.disabled = !fill.changed && !saveOnly;
    fillButton.textContent = saveOnly ? "Save choices" : `Fill in the rest · ${COUNT.format(fill.changed)}`;
    replaceButton.disabled = !replace.changed;
    replaceButton.textContent = `Replace my picks · ${COUNT.format(replace.changed)}`;
  }

  // Saves the rule and makes ``result``'s changes (plan()'s, filling in or replacing). With "Collapse a
  // race when I pick" on, the races it fills fold, as a pick by hand does; Undo opens them again.
  function apply(result) {
    const changed = result.rows.filter((row) => row.changed);
    const previous = loadRule();
    saveRule(rule);
    dialog.close();
    if (!changed.length) {
      page.renderRaces();
      showToast("Saved your choices.", { label: "Undo", run: () => {
        saveRule(previous);
        page.renderRaces();
      } });
      return;
    }
    const changes = Object.fromEntries(changed.map((row) => [row.race.key, row.after]));
    const auto = Object.fromEntries(changed.map((row) => [row.race.key, row.auto]));
    const folded = viewPref("collapseOnPick")
      ? changed.filter((row) => row.outcome === "pick" && row.after.length >= row.race.seats && !page.picks.isCollapsed(row.race.key))
        .map((row) => row.race.key)
      : [];
    const { picked, takenBack } = result;
    const before = page.picks.setMany(changes, auto);
    if (folded.length) page.picks.setCollapsed(folded, true);
    const undo = () => {
      hideBanner();
      saveRule(previous);
      page.picks.setMany(before.picks, before.auto);
      if (folded.length) page.picks.setCollapsed(folded, false);
      page.renderRaces();
    };
    showBanner(describeRule(rule, parties, has), undo);
    page.renderRaces();
    const did = [picked ? `picked ${plural(picked, "race")}` : null, takenBack ? `took back ${plural(takenBack, "pick")}` : null];
    showToast(`Your conditions ${did.filter(Boolean).join(" and ")}.`, { label: "Undo", run: undo });
  }

  function reset() {
    draw({ ...structuredClone(DEFAULT_RULE), onlyMatches: rule.onlyMatches }, options, scope);
    $("#rule-reset").focus();
  }

  const openList = () => {
    raceDetails.open = scope.races.length === 1 || WIDE.matches;
  };
  const scopeOption = (o) => h("option", { value: o.id, selected: o === scope }, o.label);
  const scopeSelect = h("select", { id: "rule-scope", on: { change: (event) => {
    scope = options.find((o) => o.id === event.target.value);
    openList();
    update();
  } } }, options.filter((o) => !o.single).map(scopeOption),
  options.some((o) => o.single) ? h("optgroup", { label: "This race only" }, options.filter((o) => o.single).map(scopeOption)) : null);

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
        h("div", { class: "rule-chips" }, has.endorsers.map(({ source, label, count }) =>
          chip(label, rule.endorsedBy.includes(source), set((on) => {
            rule.endorsedBy = [...rule.endorsedBy.filter((id) => id !== source), ...(on ? [source] : [])];
          }), { count, title: `${label} endorses ${plural(count, "candidate")} on this ballot` }))),
        h("p", { class: "fine" }, "Endorsed by any one you choose. These are who you Trust in Help me pick too.",
          has.endorsers.some((e) => e.source === "voteforpeace") ? " Vote for Peace counts the candidates it marks Ally." : ""),
      ]),
    group("Money",
      moneyOn && checkRow("Their money is", rule.money.on, set((on) => { rule.money.on = on; }), { extra: moneyInputs, stacked: true }),
      has.small && checkRow("Small donations make up at least", rule.small.on, set((on) => { rule.small.on = on; }),
        { extra: percentBox("small", "Small donations' share of what they raised, in percent") }),
      has.texas && checkRow("Texas donors make up at least", rule.texas.on, set((on) => { rule.texas.on = on; }),
        { extra: percentBox("texas", "Texas donors' share of itemized donations, in percent") })),
    group("Polls", has.polls && checkRow("They lead the polls", rule.leads, set((on) => { rule.leads = on; }))));

  const skipRows = [
    has.banned && checkRow("On your Avoid list", rule.banned, set((on) => { rule.banned = on; })),
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

  const sourcesOff = page.ballot.sources_off || [];
  const offNote = h("p", { class: "fine", hidden: !sourcesOff.length }, offLine(sourcesOff));

  const { head } = dialogHead(dialog, h("div", { class: "details-title" },
    h("h2", { id: "rules-title" }, "More conditions"),
    h("p", { class: "muted" }, "Choose who to pick and who to skip. Nothing changes until you press a button below.")),
  helpLink("pick-by-rule", "More conditions"));
  dialog.replaceChildren(
    head,
    h("div", { class: "rule-bar" },
      h("label", { class: "rule-label", for: "rule-scope" }, "Apply to"), scopeSelect,
      h("button", { type: "button", id: "rule-reset", class: "link-btn rule-reset", on: { click: reset } }, icon("reset"), "Reset")),
    h("div", { class: "rule-layout" },
      h("div", { class: "rule-form" },
        pickSet,
        skipSet,
        offNote,
        h("details", { class: "rule-how" }, h("summary", {}, "How conditions work"),
          h("ul", {},
            h("li", {}, "Pick: candidates who meet every condition you turn on, from any party and any endorser you choose."),
            h("li", {}, "Don't pick: anyone who meets any one, even your own picks."),
            h("li", {}, "Each condition counts only where its source has data (money: congressional and state races; "
              + "polls: U.S. Senate, U.S. House, Governor)."),
            h("li", {}, "Write-ins are picked only with the Write-ins chip."),
            h("li", {}, "More matches than seats, or a tie: left for you."),
            h("li", {}, "Fill in the rest picks only in races with no pick; Replace my picks replaces picks too. Both take back the picks "
              + "your endorsers made, here or in Help me pick, that no endorser you choose still endorses.")))),
      h("aside", { class: "rule-preview", "aria-label": "What your conditions would do" },
        h("h3", {}, "Your conditions"),
        noWords, pickWords, skipWords,
        h("h3", {}, "What Fill in the rest would do"),
        tallyList,
        replaceNote,
        raceDetails)),
    h("div", { class: "details-foot" },
      h("button", { type: "button", class: "btn ghost", on: { click: () => dialog.close() } }, "Cancel"),
      replaceButton,
      fillButton),
  );
  openList();
  update();
}
