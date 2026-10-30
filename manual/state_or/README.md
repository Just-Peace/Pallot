# Oregon's list of candidates, saved by hand

The Secretary of State's candidate search, ORESTAR (https://secure.sos.state.or.us/orestar/CFSearchPage.do), is a form with no file to download for a program, so its results are exported in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Search the general election, not the primary: its rows say "2026 General Election". It lists the nominees only (each party's primary winners, the minor parties' nominees, write-in winners and the nonpartisan races still open), so primary losers are off it. The import refuses another election, or a race with two candidates of one party, which would mean a primary's list.

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the list

1. Open the candidate search in your browser. Choose the year's general election, with every office and party.
2. Search, then export the results to Excel, and save the file (`XcelCFSearch.xlsx`) into this folder.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list or "manual/state_or/XcelCFSearch.xlsx"
```

The import reads the candidates and writes `bundles/data/state_or.json`, which holds only their offices, names and parties, never their addresses, phones or emails. It refuses a file it can't read (columns changed, another election, an office it doesn't know, fewer than six U.S. House or 60 State House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

A candidate nominated by several parties is shown once, with each party ("Democrat / Working Families"), as the ballot prints them.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
