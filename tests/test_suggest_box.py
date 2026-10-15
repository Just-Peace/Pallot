"""The address box's suggestions (suggest.js): a touch screen keeps the browser's own address
autofill, and a street autofilled into the box opens the list even if the box wasn't focused. Run in
Node, which loads the module as the browser does, with stand-ins for the page and the server."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "suggest.js").as_uri()
PAGE = """
class Node {}
class Element extends Node {
  constructor(tag) {
    super();
    Object.assign(this, { tag, attrs: {}, listeners: {}, children: [], hidden: false, value: "" });
  }
  setAttribute(key, value) { this.attrs[key] = String(value); if (key === "id") this.id = String(value); }
  getAttribute(key) { return key in this.attrs ? this.attrs[key] : null; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  fire(type) { for (const listener of this.listeners[type] || []) listener({ preventDefault() {} }); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  after(node) { this.next = node; }
  focus() { if (document.activeElement !== this) { document.activeElement = this; this.fire("focus"); } }
  blur() { if (document.activeElement === this) { document.activeElement = null; this.fire("blur"); } }
  closest() { return null; }
  scrollIntoView() {}
  setSelectionRange() {}
}
globalThis.Node = Node;
globalThis.document = {
  activeElement: null,
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => text,
  documentElement: { classList: { add() {}, remove() {} } },
};
globalThis.fetch = async (url) => ({
  ok: true,
  json: async () => url.endsWith("q=") ? { enabled: true }
    : { suggestions: [{ label: "1100 Congress Ave, Austin, TX 78701" }] },
});
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const addressBox = () => {
  const input = new Element("input");
  input.id = "address";
  input.setAttribute("autocomplete", "street-address");
  return input;
};
"""


def _run(script: str, coarse: bool):
    source = (f"{PAGE}\nglobalThis.matchMedia = () => ({{ matches: {json.dumps(coarse)} }});\n"
              f'const {{ attachSuggestions }} = await import("{MODULE}");\n'
              f"console.log(JSON.stringify(await (async () => {{ {script} }})()));")
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize(("coarse", "autocomplete"), [(True, "street-address"), (False, "off")])
def test_only_a_touch_screen_keeps_the_browsers_address_autofill(coarse, autocomplete):
    assert _run("""
const input = addressBox();
await attachSuggestions(input);
return input.getAttribute("autocomplete");
""", coarse) == autocomplete


@pytest.mark.parametrize("coarse", [True, False])
def test_a_street_autofilled_into_an_unfocused_box_opens_the_list(coarse):
    assert _run("""
const input = addressBox();
await attachSuggestions(input);
input.value = "1100 Congress Ave";
input.fire("input");
await wait(400);
return [document.activeElement === input, input.next.hidden, input.getAttribute("aria-expanded")];
""", coarse) == [True, False, "true"]
