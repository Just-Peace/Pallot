// The Issues tab in Details: hot-button issues the voter chooses, a folding section per group, and
// under them the question (issue-prompt.js) for the engine chosen in Settings, which the voter can
// edit, with an AI assistant comparing the race's other candidates too. The terms are neutral: where
// an issue has two sides, they name both.

import { h, safeUrl } from "./dom.js";
import { icon } from "./icons.js";
import { issuePrompt } from "./issue-prompt.js";
import { partyName } from "./labels.js";
import { currentEngine, searchHref, searchWord } from "./search.js";
import { foldSection } from "./source-cards.js";
import { showToast } from "./toast.js";

const STANCES = [
  { group: "Rights & society", topics: [
    { label: "Abortion", terms: "abortion" },
    { label: "Gun laws", terms: "gun rights gun control" },
    { label: "Human rights", terms: "human rights" },
    { label: "Women's rights", terms: "women's rights" },
    { label: "Religious freedom", terms: "religious freedom" },
    { label: "Free speech", terms: "free speech First Amendment" },
    { label: "Immigration", terms: "immigration border" },
  ] },
  { group: "Economy", topics: [
    { label: "The economy", terms: "economic policy" },
    { label: "Taxes", terms: "taxes" },
    { label: "Trade & tariffs", terms: "trade tariffs" },
    { label: "Jobs & labor", terms: "workers unions minimum wage" },
    { label: "Housing", terms: "housing affordability" },
    { label: "Cost of living", terms: "cost of living inflation prices" },
    { label: "Energy", terms: "energy policy oil gas renewables" },
    { label: "Environment & climate", terms: "environment climate change" },
  ] },
  { group: "Government", topics: [
    { label: "Government spending", terms: "government spending" },
    { label: "Deficit & debt", terms: "budget deficit national debt" },
    { label: "Size of government", terms: "role and size of government" },
    { label: "Regulation", terms: "government regulation" },
    { label: "Campaign finance", terms: "campaign finance Citizens United super PAC money" },
    { label: "Technology & AI", terms: "technology policy artificial intelligence privacy" },
  ] },
  { group: "Foreign policy & defense", topics: [
    { label: "Foreign policy", terms: "foreign policy" },
    { label: "War & military action", terms: "war military intervention" },
    { label: "National defense", terms: "national defense" },
    { label: "Military spending", terms: "military defense budget" },
    { label: "Israel & Palestine", terms: "Israel Palestine Gaza" },
  ] },
  { group: "Public services", topics: [
    { label: "Education", terms: "education schools" },
    { label: "Health care", terms: "health care reform" },
    { label: "Social Security", terms: "Social Security" },
    { label: "Infrastructure", terms: "infrastructure roads transit" },
  ] },
];

const TOPICS = STANCES.flatMap(({ topics }) => topics);

// What the voter chose in this race, kept while ‹ and › step through its candidates: the issues, by
// label, and the candidates they unchecked from the comparison, by key.
let held = { race: null, chosen: new Set(), left: new Set() };

// Details closed: the next candidate opened starts with nothing chosen.
export function resetIssues() {
  held = { race: null, chosen: new Set(), left: new Set() };
}

// ``where`` is the race's office, place and year (raceWhere); ``empty`` says no source has details on the candidate.
export function stancesPanel(race, candidate, where, empty) {
  if (held.race !== race.key) held = { race: race.key, chosen: new Set(), left: new Set() };
  const { ai, label } = currentEngine();
  const others = ai ? race.candidates.filter((other) => other !== candidate) : [];

  const question = h("textarea", { id: "issue-question", class: "issue-question", rows: ai ? 8 : 3 });
  const askName = `${ai ? `Ask ${label}` : `Search ${label}`} (opens in a new tab)`;
  const ask = h("a", { class: "btn primary with-icon issue-ask", target: "_blank", rel: "noopener noreferrer",
    title: askName, "aria-label": askName }, icon("search"), `${searchWord()} ${label} ↗`);
  const syncAsk = () => {
    const href = question.value.trim() ? safeUrl(searchHref(question.value.trim())) : null;
    if (href) ask.href = href;
    else ask.removeAttribute("href");
  };
  const edited = h("p", { class: "fine issue-edited", hidden: true }, "You changed the question. Choosing again starts it over. ",
    h("button", { type: "button", class: "link-btn", on: { click: () => rebuild() } }, "Reset"));
  const rebuild = () => {
    const compared = [candidate, ...others.filter((other) => !held.left.has(other.key))];
    question.value = issuePrompt(race, where, compared, TOPICS.filter((topic) => held.chosen.has(topic.label)), ai);
    edited.hidden = true;
    syncAsk();
  };
  question.addEventListener("input", () => {
    edited.hidden = false;
    syncAsk();
  });
  const copy = h("button", { type: "button", class: "btn ghost", on: { click: async () => {
    try {
      await navigator.clipboard.writeText(question.value);
      showToast("Question copied.");
    } catch {
      question.select();
    }
  } } }, "Copy");

  const chip = (topic) => h("li", {}, h("button", {
    type: "button", class: "rule-chip", "aria-pressed": String(held.chosen.has(topic.label)),
    on: { click: (event) => {
      const on = !held.chosen.has(topic.label);
      if (on) held.chosen.add(topic.label);
      else held.chosen.delete(topic.label);
      event.currentTarget.setAttribute("aria-pressed", String(on));
      rebuild();
    } },
  }, topic.label));
  const compare = others.length ? h("fieldset", { class: "issue-compare" }, h("legend", {}, "Compare with"),
    others.map((other) => h("label", { class: "check" },
      h("input", { type: "checkbox", checked: !held.left.has(other.key), on: { change: (event) => {
        if (event.target.checked) held.left.delete(other.key);
        else held.left.add(other.key);
        rebuild();
      } } }),
      h("span", {}, other.name, partyName(other) ? h("span", { class: "muted" }, ` · ${partyName(other)}`) : null)))) : null;
  rebuild();

  return h("div", { class: "card-panel stances" },
    empty ? h("p", { class: "muted" }, "No source has details on this candidate yet.") : null,
    h("p", { class: "notice notice-warn" },
      h("strong", {}, `This goes to ${label}, an outside ${ai ? "AI assistant" : "search engine"}.`), " ",
      ai
        ? `Choose issues, then ask it where ${candidate.name} stands, side by side with the others you check. Its answers aren't Pallot's, and we haven't checked them.`
        : `Choose issues, then search it for ${candidate.name}'s stance. Its results aren't Pallot's, and we haven't checked them.`),
    STANCES.map(({ group, topics }) => foldSection(group, null,
      h("ul", { class: "rule-chips issue-chips", "aria-label": group }, topics.map(chip)))),
    h("section", { class: "issue-box", "aria-labelledby": "issue-box-title" },
      h("h3", { id: "issue-box-title" }, "Your question"),
      compare,
      h("label", { for: "issue-question", class: "fine" }, ai ? `What ${label} is asked. You can edit it.` : `What ${label} searches for. You can edit it.`),
      question,
      edited,
      h("div", { class: "button-row" }, ask, copy)));
}
