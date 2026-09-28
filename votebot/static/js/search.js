// The web search behind each candidate's "Web search" link. The engine is a per-browser
// choice from the Settings pane; Google unless changed.

import { loadUi, saveUi } from "./picks.js";

export const ENGINES = [
  { id: "google", label: "Google", url: "https://www.google.com/search?q=" },
  { id: "bing", label: "Bing", url: "https://www.bing.com/search?q=" },
  { id: "duckduckgo", label: "DuckDuckGo", url: "https://duckduckgo.com/?q=" },
  { id: "brave", label: "Brave Search", url: "https://search.brave.com/search?q=" },
  { id: "yahoo", label: "Yahoo", url: "https://search.yahoo.com/search?p=" },
  { id: "startpage", label: "Startpage", url: "https://www.startpage.com/sp/search?query=" },
  { id: "ecosia", label: "Ecosia", url: "https://www.ecosia.org/search?q=" },
  { id: "kagi", label: "Kagi", url: "https://kagi.com/search?q=" },
  { id: "perplexity", label: "Perplexity", url: "https://www.perplexity.ai/search?q=" },
];

export function currentEngine() {
  return ENGINES.find((e) => e.id === loadUi().searchEngine) || ENGINES[0];
}

export function setEngine(id) {
  saveUi({ ...loadUi(), searchEngine: id });
}

export function searchHref(query) {
  return currentEngine().url + encodeURIComponent(query);
}
