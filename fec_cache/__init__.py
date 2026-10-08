"""A snapshot of the FEC's answers for Texas's federal races, bundled with Pallot.

``data/current.json`` holds the answers a ballot lookup asks the FEC for (each seat's race list,
and the breakdowns of the candidates on the ballot), and ``data/meta.json`` when they were last
checked. Pallot loads them into its cache at startup (pallot/sources/fec.py), so a lookup asks
the FEC only for what's missing or stale. ``uv run fec-cache refresh`` rebuilds it (refresh.py);
store.py reads and writes the files and imports nothing from Pallot, which reads it at startup.
"""
