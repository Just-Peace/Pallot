// The web search behind each candidate's "Search" (or "Ask") and Issues links. The engine is a per-browser
// choice on the Settings page; Google AI Mode unless changed. An AI assistant gets the same query as a prompt.

import { setUiPref, uiPref } from "./storage.js";

export const ENGINES = [
  { id: "google", label: "Google", url: "https://www.google.com/search?q=" },
  { id: "bing", label: "Bing", url: "https://www.bing.com/search?q=" },
  { id: "duckduckgo", label: "DuckDuckGo", url: "https://duckduckgo.com/?q=" },
  { id: "brave", label: "Brave Search", url: "https://search.brave.com/search?q=" },
  { id: "yahoo", label: "Yahoo", url: "https://search.yahoo.com/search?p=" },
  { id: "startpage", label: "Startpage", url: "https://www.startpage.com/sp/search?query=" },
  { id: "ecosia", label: "Ecosia", url: "https://www.ecosia.org/search?q=" },
  { id: "kagi", label: "Kagi", url: "https://kagi.com/search?q=" },
  { id: "perplexity", label: "Perplexity", url: "https://www.perplexity.ai/search?q=", ai: true },
  { id: "chatgpt", label: "ChatGPT", url: "https://chatgpt.com/?hints=search&q=", ai: true },
  { id: "claude", label: "Claude", url: "https://claude.ai/new?q=", ai: true },
  { id: "copilot", label: "Microsoft Copilot", url: "https://copilot.microsoft.com/?q=", ai: true },
  { id: "google-ai", label: "Google AI Mode", url: "https://www.google.com/search?udm=50&q=", ai: true },
  { id: "grok", label: "Grok", url: "https://grok.com/?q=", ai: true },
];

const DEFAULT_ENGINE = "google-ai";

export function currentEngine() {
  const id = uiPref("searchEngine");
  return ENGINES.find((e) => e.id === id) || ENGINES.find((e) => e.id === DEFAULT_ENGINE);
}

export function setEngine(id) {
  setUiPref("searchEngine", id);
}

export function searchHref(query) {
  return currentEngine().url + encodeURIComponent(query);
}

// The one word on a search button: "Ask" an AI assistant, "Search" an engine.
export function searchWord() {
  return currentEngine().ai ? "Ask" : "Search";
}

export function searchTitle(name) {
  const engine = currentEngine();
  return engine.ai ? `Ask ${engine.label} about ${name}` : `Search ${engine.label} for ${name}`;
}

export function stanceTitle(name, topic) {
  const engine = currentEngine();
  return engine.ai ? `Ask ${engine.label} where ${name} stands on ${topic}` : `Search ${engine.label} for ${name} on ${topic}`;
}
