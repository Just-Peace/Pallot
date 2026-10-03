"""The browser's ES modules link up: every file an entry script reaches is served, and every
name imported from one is exported by it. A wrong import name blanks a page without failing
any other test."""

from __future__ import annotations

import posixpath
import re

import pytest

from votebot.api import STATIC_DIR

PAGES = ["/", "/settings.html", "/faq.html", "/about.html", "/privacy.html"]

ENTRY = re.compile(r'<script type="module" src="([^"]+)"')
CLASSIC = re.compile(r'<script src="([^"]+)"')
IMPORT = re.compile(r'^\s*import\s+(?:\{([^}]*)\}\s*from\s*)?"([^"]+)"', re.M)
DYNAMIC = re.compile(r'\bimport\(\s*"([^"]+)"\s*\)')
DECLARED = re.compile(r"^export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([\w$]+)", re.M)
LISTED = re.compile(r"^export\s*\{([^}]*)\}", re.M)


def _names(listing: str, *, exported: bool) -> set[str]:
    """``a, b as c`` -> the names on the module's side (imported) or the outside (exported)."""
    names = set()
    for part in filter(None, (p.strip() for p in listing.split(","))):
        local, _, alias = part.partition(" as ")
        names.add((alias if exported and alias else local).strip())
    return names


def _exports(source: str) -> set[str]:
    names = set(DECLARED.findall(source))
    for listing in LISTED.findall(source):
        names |= _names(listing, exported=True)
    return names


def _modules(client) -> dict[str, str]:
    """Every module reached from the pages' entry scripts: path -> source."""
    queue = sorted({posixpath.join("/", src) for page in PAGES for src in ENTRY.findall(client.get(page).text)})
    assert {"/js/ballot.js", "/js/page.js", "/js/settings.js"} <= set(queue)
    seen: dict[str, str] = {}
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        response = client.get(path)
        assert response.status_code == 200, path
        seen[path] = response.text
        for spec in [m[1] for m in IMPORT.findall(response.text)] + DYNAMIC.findall(response.text):
            queue.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), spec)))
    return seen


def test_every_imported_name_is_exported(client):
    modules = _modules(client)
    missing = []
    for path, source in modules.items():
        if "/vendor/" in path:
            continue
        for listing, spec in IMPORT.findall(source):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
            missing += [f"{path}: {name} from {spec}" for name in _names(listing, exported=False) - _exports(modules[target])]
    assert not missing


def test_every_module_is_reached(client):
    """A module under js/ that no page reaches, or loads as a classic script, is dead code."""
    on_disk = {f"/js/{p.name}" for p in (STATIC_DIR / "js").glob("*.js")}
    classic = {posixpath.join("/", src) for page in PAGES for src in CLASSIC.findall(client.get(page).text)}
    assert on_disk - set(_modules(client)) - classic == set()


@pytest.mark.parametrize("page", PAGES)
def test_theme_is_set_before_the_stylesheet(client, page):
    """theme.js sets light or dark before the first paint, so the page never flashes the other one."""
    html = client.get(page).text
    assert '<script src="js/theme.js"></script>' in html
    assert html.index("js/theme.js") < html.index("css/app.css") < html.index("</head>")


@pytest.mark.parametrize("source,expected", [
    ('export function a() {}\nexport const b = 1;\nexport async function c() {}\nexport class D {}', {"a", "b", "c", "D"}),
    ("const x = 1;\nexport { x, x as y };", {"x", "y"}),
])
def test_exports_are_read(source, expected):
    assert _exports(source) == expected
