// The hot-button issues a voter can ask about (the Ask card, stances.js), grouped, and the ones the
// voter says matter most to them: kept with the view settings (pallot.ui.v1, "issues", by label),
// never sent to the server, and out of the browser only in a question the voter sends. They start
// chosen in Compare issues and the Issues tab, and are set on the start screen and in Settings. The
// terms are neutral: where an issue has two sides, they name both.

import { h } from "./dom.js";
import { setUiPrefs, uiPref } from "./storage.js";

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
    { label: "Corruption & ethics", terms: "government corruption ethics transparency" },
    { label: "Regulation", terms: "government regulation" },
    { label: "Spending & debt", terms: "government spending budget deficit national debt" },
  ] },
  { group: "Public services", topics: [
    { label: "Crime & public safety", terms: "crime public safety policing criminal justice reform" },
    { label: "Disaster response", terms: "disaster preparedness response relief FEMA" },
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
    { label: "Minority rights", terms: "minority rights civil rights discrimination affirmative action DEI" },
    { label: "Religious freedom", terms: "religious freedom" },
    { label: "Women's rights", terms: "women's rights" },
  ] },
];

export const TOPICS = STANCES.flatMap(({ topics }) => topics);

// How many saved issues make a good question; past it, a word that the answer gets long.
const FEW = 5;

// The voter's saved issues, by label, in TOPICS' order; one no longer offered is left out.
export function savedIssues() {
  const saved = uiPref("issues");
  return Array.isArray(saved) ? TOPICS.map((topic) => topic.label).filter((label) => saved.includes(label)) : [];
}

export function setSavedIssue(label, on) {
  const others = savedIssues().filter((saved) => saved !== label);
  setUiPrefs({ issues: on ? [...others, label] : others });
}

// The issues as chips under their groups' names, a button each, pressed when ``isChosen(label)``;
// ``toggle(label, on)`` runs as one is pressed. ``id`` keeps the groups' ids apart on the page.
export function issueGroups(isChosen, toggle, id) {
  const groupId = (name) => id(`group-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`);
  const chip = (topic) => h("li", {}, h("button", {
    type: "button", class: "rule-chip issue-chip", "data-issue": topic.label, "aria-pressed": String(isChosen(topic.label)),
    on: { click: (event) => {
      const on = event.currentTarget.getAttribute("aria-pressed") !== "true";
      event.currentTarget.setAttribute("aria-pressed", String(on));
      toggle(topic.label, on);
    } },
  }, topic.label));
  return STANCES.map(({ group, topics }) => [
    h("p", { class: "issue-group", id: groupId(group) }, group),
    h("ul", { class: "rule-chips issue-chips", "aria-labelledby": groupId(group) }, topics.map(chip)),
  ]);
}

// The saved issues to choose, on the start screen and in Settings, under the heading ``labelledBy``:
// "Choose 3 to 5" with how many are, the chips, a word past five, and where they're kept. sync()
// shows them again from storage, after another tab or Clear data changed them.
export function savedIssuesPicker(prefix, labelledBy) {
  const id = (name) => `${prefix}-issue-${name}`;
  const count = h("span", { class: "issue-count", "aria-live": "polite" });
  const many = h("p", { class: "fine issue-many", hidden: true }, `More than ${FEW} makes for a long answer.`);
  const showCount = () => {
    const n = savedIssues().length;
    count.textContent = n ? ` · ${n} chosen` : " · none chosen";
    many.hidden = n <= FEW;
  };
  const element = h("div", { class: "saved-issues", role: "group", "aria-labelledby": labelledBy },
    h("p", { class: "issue-hint" }, `Choose 3 to ${FEW}`, count),
    issueGroups((label) => savedIssues().includes(label), (label, on) => {
      setSavedIssue(label, on);
      showCount();
    }, id),
    many,
    h("p", { class: "fine" }, "Kept in this browser. They go out only in a question you send."));
  const sync = () => {
    const saved = savedIssues();
    for (const chip of element.querySelectorAll(".issue-chip")) chip.setAttribute("aria-pressed", String(saved.includes(chip.dataset.issue)));
    showCount();
  };
  showCount();
  return { element, sync };
}
