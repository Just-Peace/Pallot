# Louisiana's list of candidates, saved by hand

The Secretary of State's candidate inquiry (https://voterportal.sos.la.gov/candidateinquiry) is a page that runs in the browser, with no file to download, so its table is exported in your own browser, and Pallot imports the saved file. Pallot never fetches it.

It lists everyone who qualified for one election day, with how each stands ("Unopposed", "Withdrew"). In November 2026 that day holds the U.S. Senate's general election, after the parties' closed primaries in the spring, and the open primary for the U.S. House and for state and local offices, where candidates of every party run together. Unopposed, withdrawn and disqualified candidates aren't on the ballot, and the import leaves them out.

Do this again whenever the list changes (a withdrawal, a disqualification).

## 1. Save the list

1. Open https://voterportal.sos.la.gov/candidateinquiry in your browser, choose the November election's date, and open the "Statewide/Multi-Parish" tab.
2. Click "Export to CSV", and save the file into this folder. Its columns start with Election, OfficeTitle, OfficeTitleDescription and NumberToBeElected.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list la "manual/state_la/<the file>.csv"
```

The import reads the candidates and writes `bundles/data/state_la.json`, which holds only their offices, names and parties, never their addresses, phones or emails. It refuses a file it can't read (columns changed, an office or a candidate's standing it doesn't know, two U.S. Senate candidates of one party, fewer than six U.S. House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
