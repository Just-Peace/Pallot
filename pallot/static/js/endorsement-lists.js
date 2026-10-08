// The endorsement lists that came with Pallot and the ones it fetches live (/api/endorsements),
// named on the pages that list the sources, so adding an organization's file or feed needs no HTML.
// A page marks the spots with data-endorsements:
//   "clause", a <span> in a sentence: ", whether A endorses them" or ", which of A and B endorse them";
//   "live", a <span> in a sentence: " (A and B)", the lists fetched live;
//   "rows", a <template> in a table body, replaced by a row per list;
//   "list", a <template> in a list, replaced by an item per list;
//   "none", shown only when there's no list.

import { api } from "./api.js";
import { extLink, h } from "./dom.js";
import { SHORT_DATE, formatDate, listed } from "./format.js";

const captured = (list) => formatDate(list.captured, SHORT_DATE);
const fetched = (list) => (list.captured ? `fetched from its website on ${captured(list)}` : "fetched from its website");

function clause(lists) {
  if (!lists.length) return "";
  if (lists.length === 1) return `, whether ${lists[0].label} endorses them`;
  return `, which of ${listed(lists.map((list) => list.label))} endorse them`;
}

const when = (list) => (list.live ? fetched(list) : `as captured on ${captured(list)}`);

const row = (list) => h("tr", {}, h("th", { scope: "row" }, extLink(list.url, list.label)),
  h("td", {}, `Its endorsements, ${list.live ? (list.captured ? `fetched ${captured(list)}` : "fetched live") : `as of ${captured(list)}`}`));

const item = (list) => h("li", {}, h("strong", {}, list.label), `: ${list.description} `,
  extLink(list.url, "Its list"), `, ${when(list)}.`);

function live(lists) {
  const feeds = lists.filter((list) => list.live).map((list) => list.label);
  return feeds.length ? ` (${listed(feeds)})` : "";
}

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
    else if (kind === "live") spot.textContent = live(lists);
    else if (kind === "rows") spot.replaceWith(...lists.map(row));
    else if (kind === "list") spot.replaceWith(...lists.map(item));
  }
}
