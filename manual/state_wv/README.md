# West Virginia's list of candidates, saved by hand

The Secretary of State's candidate listing (https://candidates.wvsos.gov/) turns programs away, so its table is exported in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Choose the year's general election ("2026 General Candidate Listing"). It lists the nominees only: each party's primary winners, the minor parties' nominees and independents, and anyone named later to a place no one won, so primary losers are off it. The import refuses a race with two Democrats or two Republicans, which would mean a primary's list. Before importing, you can check the Democrats and Republicans against the primary's results (https://sos.wv.gov/elections, "Election Results").

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the list

1. Open https://candidates.wvsos.gov/ in your browser, and choose the general election, with every office and party.
2. Export the table to CSV (its columns start Name, Legal Name, Party, County, Race), and save it into this folder.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list wv "manual/state_wv/<the file>.csv"
```

The import reads the candidates and writes `bundles/data/state_wv.json`, which holds only their offices, names and parties, never their addresses, phones or emails. It refuses a file it can't read (columns changed, an office it doesn't know, fewer than 2 U.S. House, 17 State Senate or 100 House of Delegates races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
