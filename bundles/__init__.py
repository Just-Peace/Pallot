"""Cached sources' answers, bundled with Pallot.

``data/<name>.json`` holds the answers a ballot lookup asks a source for (usually one bundle per
source, named after it; Texas SOS's ballot orders are a bundle of their own), and ``data/meta.json``
when each bundle's were last checked. Pallot puts them in its cache at startup (registry.seed), so
a lookup asks a source only for what's missing or older than its bundle lifetime.
``uv run pallot-bundle refresh`` rebuilds them (refresh.py), running each source's builder in the
registry (registry.BUNDLES). store.py imports nothing from Pallot.
"""
