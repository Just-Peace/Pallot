# New York's certification of candidates, saved by hand

elections.ny.gov answers scripts with Cloudflare's challenge, and Pallot never gets around one. So the State Board of Elections' certification of the candidates for the general election is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the State Board amends its certification (substitutions, declinations, corrections from the county boards).

## 1. Save the certification

1. Open https://elections.ny.gov/ballot-certifications-elections in your browser, and let the page finish loading.
2. Download the certification for the November 3, 2026 General Election (the accessible PDF) and save it into this folder. If what you get is a small page saying **"Just a moment..."**, that's Cloudflare's check, not the certification: wait for the page to load in the browser and download it again.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list ny "manual/state_ny/<the file>.pdf"
```

The import reads the candidates and writes `bundles/data/state_ny.json`, which holds only their offices, names and party lines. It refuses a file it can't read (Cloudflare's check, a certification missing any of the Congress or Assembly races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
