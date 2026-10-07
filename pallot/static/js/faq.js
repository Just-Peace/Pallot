// The FAQ: page.js draws the left pane and opens a linked answer; Expand all and Collapse all
// open or close every answer, each disabled while it would change nothing.

import "./page.js";
import { $ } from "./dom.js";

const answers = [...document.querySelectorAll("details.faq")];
const expand = $("#expand-all");
const collapse = $("#collapse-all");

function update() {
  expand.disabled = answers.every((answer) => answer.open);
  collapse.disabled = !answers.some((answer) => answer.open);
}

function setAll(open) {
  for (const answer of answers) answer.open = open;
  update();
}

expand.addEventListener("click", () => setAll(true));
collapse.addEventListener("click", () => setAll(false));
for (const answer of answers) answer.addEventListener("toggle", update);
update();
