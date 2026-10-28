// The Issues tab in Details, and the race's Compare issues: one card, "Ask Duck.ai" (the engine chosen in Settings), with the
// hot-button issues to choose, grouped, the race's other candidates to compare with an AI assistant,
// and the question (issue-prompt.js), which the voter can edit. The terms are neutral: where an issue
// has two sides, they name both.

import { closeOnBackdrop, dialogHead, h, safeUrl } from "./dom.js";
import { icon } from "./icons.js";
import { issuePrompt } from "./issue-prompt.js";
import { partyName } from "./labels.js";
import { currentEngine, searchHref, searchWord } from "./search.js";
import { showToast } from "./toast.js";

const STANCES = [
  { group: "Economy", topics: [
    { label: "Energy", terms: "energy policy oil gas renewables" },
    { label: "Environment & climate", terms: "environment climate change" },
    { label: "Housing", terms: "housing affordability" },
    { label: "Inflation & cost of living", terms: "inflation cost of living prices" },
    { label: "Jobs & labor", terms: "workers unions minimum wage" },
    { label: "Taxes", terms: "taxes" },
    { label: "Technology & AI", terms: "technology policy artificial intelligence privacy" },
    { label: "Trade & tariffs", terms: "trade tariffs" },
  ] },
  { group: "Foreign policy & defense", topics: [
    { label: "Defense & military spending", terms: "national defense military budget" },
    { label: "Foreign policy", terms: "foreign policy" },
    { label: "Israel & Palestine", terms: "Israel Palestine Gaza" },
    { label: "War & military action", terms: "war military intervention" },
  ] },
  { group: "Government", topics: [
    { label: "Campaign finance", terms: "campaign finance Citizens United super PAC money" },
    { label: "Regulation", terms: "government regulation" },
    { label: "Spending & debt", terms: "government spending budget deficit national debt" },
  ] },
  { group: "Public services", topics: [
    { label: "Crime & public safety", terms: "crime public safety policing criminal justice reform" },
    { label: "Education", terms: "education schools" },
    { label: "Health care", terms: "health care reform" },
    { label: "Infrastructure", terms: "infrastructure roads transit" },
    { label: "Social Security", terms: "Social Security" },
  ] },
  { group: "Rights & society", topics: [
    { label: "Abortion", terms: "abortion" },
    { label: "Free speech", terms: "free speech First Amendment" },
    { label: "Gun laws", terms: "gun rights gun control" },
    { label: "Human rights", terms: "human rights" },
    { label: "Immigration", terms: "immigration border" },
    { label: "Religious freedom", terms: "religious freedom" },
    { label: "Women's rights", terms: "women's rights" },
  ] },
];

const TOPICS = STANCES.flatMap(({ topics }) => topics);

// What the voter chose in this race, kept while ‹ and › step through its candidates: the issues, by
// label, and the candidates they unchecked from the comparison, by key.
let held = { race: null, chosen: new Set(), left: new Set() };

// Details or Compare issues closed: the next one opened starts with nothing chosen.
export function resetIssues() {
  held = { race: null, chosen: new Set(), left: new Set() };
}

// ``where`` is the race's office, place and year (raceWhere); ``empty`` says no source has details on the candidate.
export function stancesPanel(race, candidate, where, empty) {
  return h("div", { class: "card-panel stances" },
    empty ? h("p", { class: "muted" }, "No source has details on this candidate yet.") : null,
    askCard(race, candidate, where, "d"));
}

// The race's head's Compare issues: the Ask card for the whole race, every candidate checked and
// none singled out. A search engine can't compare, so then it points to Settings.
export function openIssueCompare(dialog, race, where) {
  if (!dialog.dataset.ready) {
    closeOnBackdrop(dialog);
    dialog.addEventListener("close", resetIssues);
    dialog.dataset.ready = "1";
  }
  const { ai } = currentEngine();
  const { head, close } = dialogHead(dialog,
    h("div", { class: "details-title" }, h("h2", { id: "issues-compare-title" }, "Compare on the issues"), h("p", { class: "muted" }, race.name)));
  const body = ai ? askCard(race, null, where, "c") : h("p", { class: "notice" },
    "Comparing needs an AI assistant: a search engine can't put the candidates side by side. ",
    h("a", { href: "settings.html#search-engine" }, "Choose one in Settings"), ".");
  dialog.replaceChildren(head, h("div", { class: "details-tabs" }, h("div", { class: "tab-panel stances" }, body)));
  if (!dialog.open) dialog.showModal();
  close.focus();
}

// The Ask card: the issues, the candidates to compare (with an AI assistant), the question, which
// the voter can edit, and Ask. ``candidate`` is the one Details shows, or null for the whole race;
// ``prefix`` keeps the ids apart, since Details and Compare issues can both hold a card.
function askCard(race, candidate, where, prefix) {
  if (held.race !== race.key) held = { race: race.key, chosen: new Set(), left: new Set() };
  const { ai, label } = currentEngine();
  const id = (name) => `${prefix}-issue-${name}`;
  const others = ai ? race.candidates.filter((other) => other !== candidate) : [];

  const question = h("textarea", { id: id("question"), class: "issue-question", rows: ai ? 8 : 3 });
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
    const compared = [candidate, ...others.filter((other) => !held.left.has(other.key))].filter(Boolean);
    question.value = compared.length
      ? issuePrompt(race, where, compared, TOPICS.filter((topic) => held.chosen.has(topic.label)), ai) : "";
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

  // The Issues heading says how many are chosen; none asks about the main issues.
  const countText = () => (held.chosen.size ? `· ${held.chosen.size} chosen` : "· none chosen, so the main ones");
  const count = h("span", { class: "issue-count" }, countText());
  const chip = (topic) => h("li", {}, h("button", {
    type: "button", class: "rule-chip issue-chip", "aria-pressed": String(held.chosen.has(topic.label)),
    on: { click: (event) => {
      const on = !held.chosen.has(topic.label);
      if (on) held.chosen.add(topic.label);
      else held.chosen.delete(topic.label);
      event.currentTarget.setAttribute("aria-pressed", String(on));
      count.textContent = countText();
      rebuild();
    } },
  }, topic.label));
  const groupId = (name) => id(`group-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`);
  const issues = h("div", { class: "issue-step", role: "group", "aria-labelledby": id("issues-title") },
    h("h4", { id: id("issues-title") }, "Issues ", count),
    STANCES.map(({ group, topics }) => [
      h("p", { class: "issue-group", id: groupId(group) }, group),
      h("ul", { class: "rule-chips issue-chips", "aria-labelledby": groupId(group) }, topics.map(chip)),
    ]));
  const compare = others.length ? h("fieldset", { class: "issue-compare" }, h("legend", {}, candidate ? "Compare with" : "Candidates"),
    others.map((other) => h("label", { class: "check" },
      h("input", { type: "checkbox", checked: !held.left.has(other.key), on: { change: (event) => {
        if (event.target.checked) held.left.delete(other.key);
        else held.left.add(other.key);
        rebuild();
      } } }),
      h("span", {}, other.name, partyName(other) ? h("span", { class: "muted" }, ` · ${partyName(other)}`) : null)))) : null;
  rebuild();

  let intro = `For ${candidate?.name}'s stance. Tap the issues to add.`;
  if (ai) {
    intro = candidate
      ? `Where ${candidate.name} stands, side by side with the others you check. Tap the issues to add.`
      : "Where the candidates you check stand, side by side. Tap the issues to add.";
  }
  return h("section", { class: "issue-box", "aria-labelledby": id("box-title") },
    h("h3", { id: id("box-title") }, `${searchWord()} ${label}`),
    h("p", { class: "issue-intro" }, intro),
    issues,
    compare,
    h("label", { for: id("question"), class: "issue-step-title" }, ai ? "The question" : "The search",
      h("span", { class: "issue-count" }, " · you can edit it")),
    question,
    edited,
    h("p", { class: "notice notice-warn issue-warn" },
      h("strong", {}, `This goes to ${label}, an outside ${ai ? "AI assistant" : "search engine"}.`), " ",
      ai ? "Its answers aren't Pallot's, and we haven't checked them." : "Its results aren't Pallot's, and we haven't checked them."),
    h("div", { class: "button-row" }, ask, copy));
}
