# Arkansas's list of candidates, saved by hand

The Secretary of State's candidate search (https://candidates.arkansas.gov/) has no file to download, so its table is exported in your own browser, and Pallot imports the saved file. Pallot never fetches it.

The search is labelled the year's preferential primary, but it lists only the candidates still in a race: primary losers and the withdrawn are off it, and later nominees (Libertarians, independents, replacements) are on it. Before importing, check it against the general election's ballot on the Secretary of State's results site (https://arkansas.tally-enr.com/, the "General Election"): every race for Congress, statewide office and the Legislature should have the same candidates.

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the list

1. Open https://candidates.arkansas.gov/ in your browser, with every party and office shown.
2. Export the table to CSV (its columns: Candidate Name, Position/Office, Party Affiliation, Filing Date), and save it into this folder.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list ar "manual/state_ar/<the file>.csv"
```

The import reads the candidates and writes `bundles/data/state_ar.json`, which holds only their offices, names and parties. It refuses a file it can't read (columns changed, an office it doesn't know, fewer than four U.S. House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

In 2026 the House's District 8 has a special election for the rest of the present term beside its full-term race, under the same office name: the candidates who filed for it from August 1, 2026 are put in the special.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
