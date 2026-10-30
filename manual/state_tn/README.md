# Tennessee's list of candidates, saved by hand

The Secretary of State publishes the general election's candidates as one spreadsheet per office on https://sos.tn.gov/elections/2026-candidate-lists. Its site answers 403 to programs, so the spreadsheets are downloaded in your own browser, and Pallot imports the folder. Pallot never fetches them.

They're the general election's lists, so primary losers are off them. The import refuses a race with two candidates of one party, which would mean a primary's list.

Do this again whenever the lists change (a withdrawal, a replacement).

## 1. Save the lists

1. Open https://sos.tn.gov/elections/2026-candidate-lists in your browser.
2. Download the Excel files of the November election for Governor, U.S. Senate, U.S. House, Tennessee Senate and Tennessee House (`Governor_Nov2026.xlsx`, `USSenate_Nov2026.xlsx`, `USHouse_Nov2026.xlsx`, `TNSenate_Nov2026.xlsx`, `TNHouse_Nov2026.xlsx`), and save them into this folder under those names: the year in them is the election's.

The saved files stay on your machine: this folder's files aren't committed.

## 2. Import them

```bash
uv run pallot-bundle import-list tn manual/state_tn
```

The import reads the five spreadsheets and writes `bundles/data/state_tn.json`, which holds only the candidates' offices, names and parties (not their cities). It refuses a folder it can't read (columns changed, an office it doesn't know, one of the five lists missing, fewer than nine U.S. House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
