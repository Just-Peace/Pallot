// The endorsement lists that came with Pallot (/api/endorsements), named on the pages that list
// the sources, so adding an organization's file needs no HTML. A page marks the spots with
// data-endorsements:
//   "clause", a <span> in a sentence: ", whether A endorses them" or ", which of A and B endorse them";
//   "rows", "credits" or "list", a <template> in a table body or a list, replaced by a row or an
//     item per list;
//   "none", shown only when no list came with Pallot.

import { api } from "./api.js";
import { extLink, h } from "./dom.js";
import { SHORT_DATE, formatDate, listed } from "./format.js";

const captured = (list) => formatDate(list.captured, SHORT_DATE);

function clause(lists) {
  if (!lists.length) return "";
  if (lists.length === 1) return `, whether ${lists[0].label} endorses them`;
  return `, which of ${listed(lists.map((list) => list.label))} endorse them`;
}

const FILL = {
  rows: (list) => h("tr", {}, h("th", { scope: "row" }, list.label),
    h("td", {}, `The candidates ${list.organization} endorses, from its list as captured on ${captured(list)}`)),
  credits: (list) => h("li", {}, h("strong", {}, list.label), `: the candidates ${list.organization} endorses, from its `,
    extLink(list.url, "endorsement list"), `, as captured on ${captured(list)}.`),
  list: (list) => h("li", {}, h("strong", {}, list.label), `: ${list.description} `,
    extLink(list.url, "Its list"), `, as captured on ${captured(list)}.`),
};

export async function showEndorsementLists() {
  const spots = [...document.querySelectorAll("[data-endorsements]")];
  if (!spots.length) return;
  let lists;
  try {
    lists = await api.get("/api/endorsements");
  } catch {
    return;
  }
  for (const spot of spots) {
    const kind = spot.dataset.endorsements;
    if (kind === "none") spot.hidden = lists.length > 0;
    else if (kind === "clause") spot.textContent = clause(lists);
    else if (FILL[kind]) spot.replaceWith(...lists.map(FILL[kind]));
  }
}
