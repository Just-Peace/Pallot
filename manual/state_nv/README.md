# Nevada's list of candidates, saved by hand

nvsos.gov answers scripts with a bot check, and Pallot never gets around one. So the Secretary of State's certified list of candidates is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the Secretary of State posts a revised list (withdrawals, replacements).

## 1. Save the list

1. Open https://www.nvsos.gov/sos/elections in your browser, and find the **Statewide Certified List of Candidates** for the November 3, 2026 General Election (the 2026 list was at https://www.nvsos.gov/home/showpublisheddocument/20105/639232733439300000).
2. Save the PDF into this folder. If what you get is a small page saying **"Request unsuccessful"**, that's the bot check, not the list: open the link again in the browser and save the PDF it shows.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list nv "manual/state_nv/<the file>.pdf"
```

The import reads the candidates and writes `bundles/data/state_nv.json`, which holds only their offices, names and parties. It refuses a file it can't read (the bot check, a list whose columns changed), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
