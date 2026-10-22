# Wisconsin's list of candidates, saved by hand

elections.wi.gov answers scripts with Cloudflare's challenge, and Pallot never gets around one. So the Elections Commission's list of all contests and candidates is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the Elections Commission updates the list (withdrawals, replacements).

## 1. Save the list

1. Open https://elections.wi.gov/candidates in your browser, and find the **All Contests and Candidates** list for the November 3, 2026 General Election.
2. Download it as a CSV and save it into this folder. If what you get is a small page saying **"Just a moment..."**, that's Cloudflare's check, not the list: wait for the page to load in the browser and download it again.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list wi "manual/state_wi/<the file>.csv"
```

The import reads the candidates and writes `bundles/data/state_wi.json`, which holds only their offices, names and parties. It refuses a file it can't read (Cloudflare's check, a list whose columns changed), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
