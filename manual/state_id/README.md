# Idaho's list of candidates, saved by hand

The Secretary of State's candidate search (https://run.voteidaho.gov/search) sits behind a bot check that turns programs away, so its results are exported in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Choose the year's general election ("November 03, 2026 - 2026 General"). It lists the nominees only: each party's primary winners, the minor parties' nominees, independents and declared write-ins, so primary losers are off it. Leave withdrawn candidates out (or keep them: a row with a withdrawal date is dropped). The import refuses another election, or a race with two Democrats or two Republicans, which would mean a primary's list.

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the list

1. Open https://run.voteidaho.gov/search in your browser, and choose the general election, with every office and party.
2. Export the results to Excel, and save the file (`Idaho Search Candidate Export.xlsx`) into this folder.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list id "manual/state_id/Idaho Search Candidate Export.xlsx"
```

The import reads the candidates and writes `bundles/data/state_id.json`, which holds only their offices, names and parties, never their addresses. It refuses a file it can't read (columns changed, another election, an office it doesn't know, fewer than 2 U.S. House, 35 State Senate or 35 State House districts), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
