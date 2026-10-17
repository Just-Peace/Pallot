// Address suggestions under the address box as the voter types. They come from Google Maps'
// address search through the Pallot server, which caches them. A WAI-ARIA combobox:
// ↑/↓ move through the list, Enter or a click picks, Esc closes. Picking with the keyboard or a
// mouse only fills the box; the voter still presses "Show my ballot". On a touch screen, tapping a
// suggestion looks the ballot up straight away, and the box moves to the top of the screen when
// it's focused, so the list opens above the keyboard. A touch screen keeps the browser's own
// address autofill, which a phone shows above the keyboard, not over the list; the street it fills
// in opens the list like typing does. With suggestions off in Settings, or no Google key on the server, the box is left as it was.

import { api } from "./api.js";
import { h } from "./dom.js";

const MIN_LENGTH = 5; // the server doesn't ask Ballotpedia about less
const WAIT_MS = 300; // after the last keystroke
const KEYBOARD_MS = 350; // a phone's keyboard opening, and the browser's own scroll to the box, before ours

export async function attachSuggestions(input) {
  try {
    if (!(await api.get("/api/suggest?q=")).enabled) return;
  } catch {
    return; // the lookup reports real problems
  }

  const list = h("ul", { id: `${input.id}-suggestions`, role: "listbox", "aria-label": "Suggested addresses" });
  const box = h("div", { class: "suggestions", hidden: true },
    list, h("p", { class: "suggestions-credit" }, "Suggestions from Google Maps"));
  input.after(box);
  const touchScreen = matchMedia("(pointer: coarse)");
  // A desktop browser's autofill opens on top of our list, so there our list replaces it.
  if (!touchScreen.matches) input.setAttribute("autocomplete", "off");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");

  let options = []; // [{ element, label }]
  let active = -1;
  let timer = null;
  let pending = null; // the AbortController of the call in flight
  let tapped = false; // the last press on a suggestion was a finger or a pen

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

  // ``lookUp``: a tap, which sends the form at once, the keyboard closed; otherwise the cursor stays in the box.
  function pick(index, { lookUp = false } = {}) {
    input.value = options[index].label;
    close();
    if (lookUp && input.form) {
      input.blur();
      input.form.requestSubmit();
      return;
    }
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
      // A mouse picks on pointerdown, not click, and the default is stopped so the box keeps its
      // focus and blur doesn't close the list first. A finger picks on click, so a drag that
      // scrolls the list picks nothing.
      element.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        tapped = event.pointerType !== "mouse";
        if (!tapped) pick(i);
      });
      element.addEventListener("click", () => {
        if (tapped && options[i]?.element === element) pick(i, { lookUp: true });
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
    // Some browsers autofill the box without focusing it, and the list only opens on a focused box.
    if (document.activeElement !== input) input.focus();
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

  // On a touch screen the box's field goes to the top of the screen, so the list under it opens
  // above the keyboard; html.lift-address gives the page room below to scroll that far.
  let lifting = null;
  input.addEventListener("focus", () => {
    if (!touchScreen.matches) return;
    document.documentElement.classList.add("lift-address");
    clearTimeout(lifting);
    lifting = setTimeout(() => {
      if (document.activeElement === input) (input.closest(".field") || input).scrollIntoView({ block: "start" });
    }, KEYBOARD_MS);
  });

  input.addEventListener("blur", () => {
    clearTimeout(lifting);
    document.documentElement.classList.remove("lift-address");
    close();
  });
  input.form?.addEventListener("submit", () => {
    clearTimeout(timer);
    pending?.abort();
    close();
  });
}
