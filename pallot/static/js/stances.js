// The Issues tab in Details: hot-button issues, each a web search for where the candidate stands,
// with the engine chosen in Settings, a folding section per group. The terms are neutral: where an
// issue has two sides, they name both.

import { extLink, h } from "./dom.js";
import { currentEngine, searchHref, stanceTitle } from "./search.js";
import { foldSection } from "./source-cards.js";

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

// A search engine gets keywords; an AI assistant gets a question that asks for sources and more than one view.
function stanceQuery(base, name, topic) {
  return currentEngine().ai
    ? `What is ${name}'s position on ${topic.terms}? (${base}) Cite sources, and show more than one view.`
    : `${base} position on ${topic.terms}`;
}

// ``base`` is the candidate's web search (name, office, place, year); ``empty`` says no source has details on them.
export function stancesPanel(candidate, base, empty) {
  const link = (topic) => {
    const title = stanceTitle(candidate.name, topic.label);
    return h("li", {}, extLink(searchHref(stanceQuery(base, candidate.name, topic)), [topic.label, h("span", { class: "badge-arrow" }, " ↗")],
      { class: "badge badge-link", title, "aria-label": `${title} (opens in a new tab)` }));
  };
  return h("div", { class: "card-panel stances" },
    empty ? h("p", { class: "muted" }, "No source has details on this candidate yet.") : null,
    h("p", { class: "notice notice-warn" }, `Pick an issue to search for ${candidate.name}'s stance. These are live search results, not Pallot's own, and we haven't checked them.`),
    STANCES.map(({ group, topics }) => foldSection(group, null,
      h("ul", { class: "badges", "aria-label": group }, topics.map(link)))));
}
