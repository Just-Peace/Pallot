// The FAQ: page.js draws the left pane, the sections' chips and opens a linked answer; the search
// box filters the questions as the voter types, opening the ones that match; Expand all and
// Collapse all open or close every answer shown, each disabled while it would change nothing.

import "./page.js";
import { $ } from "./dom.js";
import { plural } from "./format.js";

const answers = [...document.querySelectorAll("details.faq")];
const groups = [...document.querySelectorAll(".faq-group")];
const expand = $("#expand-all");
const collapse = $("#collapse-all");
const query = $("#faq-query");
const status = $("#faq-search-status");
const opened = new Set(); // the answers a search opened, closed again when it's cleared

// Lower case, without accents, and with curly quotes made straight, so "dont" finds "don't".
const fold = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[‘’]/g, "'")
  .replace(/[“”]/g, '"').toLowerCase();
const texts = new Map(answers.map((answer) => [answer, fold(answer.textContent).replace(/'/g, "")]));

const shown = () => answers.filter((answer) => !answer.hidden);

function update() {
  expand.disabled = shown().every((answer) => answer.open);
  collapse.disabled = !shown().some((answer) => answer.open);
}

function setAll(open) {
  for (const answer of shown()) answer.open = open;
  update();
}

// Every word typed must appear in the question or its answer.
function search() {
  const words = fold(query.value).replace(/'/g, "").split(/\s+/).filter(Boolean);
  for (const answer of opened) answer.open = false;
  opened.clear();
  for (const answer of answers) {
    const match = words.every((word) => texts.get(answer).includes(word));
    answer.hidden = !match;
    if (match && words.length && !answer.open) {
      answer.open = true;
      opened.add(answer);
    }
  }
  for (const group of groups) {
    group.hidden = !group.querySelector("details.faq:not([hidden])");
    const links = document.querySelectorAll(`a[href="#${group.getAttribute("aria-labelledby")}"]`);
    for (const link of links) link.closest(".section-chips li, .page-sections li")?.toggleAttribute("hidden", group.hidden);
  }
  const count = shown().length;
  status.textContent = !words.length ? "" : count ? `${plural(count, "question")} match.` : "No question matches. Try fewer or other words.";
  update();
}

query.addEventListener("input", search);
query.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && query.value) {
    query.value = "";
    search();
  }
});
expand.addEventListener("click", () => setAll(true));
collapse.addEventListener("click", () => setAll(false));
for (const answer of answers) {
  answer.addEventListener("toggle", () => {
    if (!answer.open) opened.delete(answer); // closed by the voter: theirs again
    update();
  });
}
update();
