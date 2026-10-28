// The Issues tab in Details, and the race's Compare issues: one card, "Ask Duck.ai" (the engine chosen in Settings), with the
// issues to choose (issues.js), the voter's saved ones chosen at first, the race's other candidates to compare
// with an AI assistant, and the question (issue-prompt.js), which the voter can edit.

import { closeOnBackdrop, dialogHead, h, safeUrl } from "./dom.js";
import { icon } from "./icons.js";
import { issuePrompt } from "./issue-prompt.js";
import { TOPICS, issueGroups, savedIssues } from "./issues.js";
import { partyName } from "./labels.js";
import { currentEngine, searchHref, searchWord } from "./search.js";
import { showToast } from "./toast.js";

// What the voter chose in this race, kept while ‹ and › step through its candidates: the issues, by
// label, starting from their saved ones, and the candidates they unchecked from the comparison, by key.
// Choosing here never changes the saved issues.
let held = { race: null, chosen: new Set(), left: new Set() };

// Details or Compare issues closed: the next one opened starts again from the saved issues.
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
  if (held.race !== race.key) held = { race: race.key, chosen: new Set(savedIssues()), left: new Set() };
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
  const issues = h("div", { class: "issue-step", role: "group", "aria-labelledby": id("issues-title") },
    h("h4", { id: id("issues-title") }, "Issues ", count),
    issueGroups((label) => held.chosen.has(label), (label, on) => {
      if (on) held.chosen.add(label);
      else held.chosen.delete(label);
      count.textContent = countText();
      rebuild();
    }, id));
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
