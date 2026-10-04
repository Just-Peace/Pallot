// Address suggestions under the address box as the voter types. They come from Ballotpedia's
// address search (Esri data) through the Pallot server, which caches them. A WAI-ARIA combobox:
// ↑/↓ move through the list, Enter or a click picks, Esc closes. Picking only fills the
// box; the voter still presses "Show my ballot". With suggestions off in Settings the box is
// left as it was, with the browser's own address autofill.

import { api } from "./api.js";
import { h } from "./dom.js";

const MIN_LENGTH = 5; // the server doesn't ask Ballotpedia about less
const WAIT_MS = 300; // after the last keystroke

export async function attachSuggestions(input) {
  try {
    if (!(await api.get("/api/suggest?q=")).enabled) return;
  } catch {
    return; // the lookup reports real problems
  }

  const list = h("ul", { id: `${input.id}-suggestions`, role: "listbox", "aria-label": "Suggested addresses" });
  const box = h("div", { class: "suggestions", hidden: true },
    list, h("p", { class: "suggestions-credit" }, "Suggestions from Ballotpedia · Esri data"));
  input.after(box);
  // Our list replaces the browser's autofill, which would open on top of it.
  input.setAttribute("autocomplete", "off");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");

  let options = []; // [{ element, label }]
  let active = -1;
  let timer = null;
  let pending = null; // the AbortController of the call in flight

  function setActive(index) {
    active = index;
    options.forEach((option, i) => option.element.setAttribute("aria-selected", String(i === index)));
    if (index >= 0) input.setAttribute("aria-activedescendant", options[index].element.id);
    else input.removeAttribute("aria-activedescendant");
  }

  function close() {
    box.hidden = true;
    list.replaceChildren();
    options = [];
    setActive(-1);
    input.setAttribute("aria-expanded", "false");
  }

  function pick(index) {
    input.value = options[index].label;
    close();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  function show(suggestions) {
    if (!suggestions.length || document.activeElement !== input) {
      close();
      return;
    }
    options = suggestions.map((suggestion, i) => {
      const element = h("li", { id: `${list.id}-${i}`, class: "suggestion", role: "option", "aria-selected": "false" },
        suggestion.label);
      // pointerdown, not click: the box keeps its focus, so blur doesn't close the list first.
      element.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        pick(i);
      });
      return { element, label: suggestion.label };
    });
    list.replaceChildren(...options.map((option) => option.element));
    setActive(-1);
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  async function ask(text) {
    pending?.abort();
    pending = new AbortController();
    try {
      const { suggestions } = await api.get(`/api/suggest?q=${encodeURIComponent(text)}`, { signal: pending.signal });
      if (input.value.trim() === text) show(suggestions); // the voter may have typed on meanwhile
    } catch (error) {
      if (error.name !== "AbortError") close();
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const text = input.value.trim();
    if (text.length < MIN_LENGTH) {
      pending?.abort();
      close();
      return;
    }
    timer = setTimeout(() => ask(text), WAIT_MS);
  });

  input.addEventListener("keydown", (event) => {
    if (box.hidden) {
      if (event.key === "ArrowDown" && input.value.trim().length >= MIN_LENGTH) {
        event.preventDefault();
        ask(input.value.trim());
      }
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      // -1 is back in the box, with nothing highlighted.
      const next = active + (event.key === "ArrowDown" ? 1 : -1);
      setActive(next >= options.length ? -1 : next < -1 ? options.length - 1 : next);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault(); // pick, don't look the ballot up yet
      pick(active);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Tab") {
      close();
    }
  });

  input.addEventListener("blur", close);
  input.form?.addEventListener("submit", () => {
    clearTimeout(timer);
    pending?.abort();
    close();
  });
}
