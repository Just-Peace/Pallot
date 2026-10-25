# Iowa's list of candidates, saved by hand

sos.iowa.gov answers scripts with Cloudflare's challenge, and Pallot never gets around one. So the Secretary of State's candidate list is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the Secretary of State posts a revised list (withdrawals, vacancies filled).

## 1. Save the list

1. Open https://sos.iowa.gov/general-election in your browser, and let the page finish loading (a **"Just a moment..."** page means Cloudflare's check hasn't passed yet).
2. Download the **2026 General – Candidate List** PDF and save it into this folder.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list ia "manual/state_ia/<the file>.pdf"
```

The import reads the candidates and writes `bundles/data/state_ia.json`, which holds only their offices, names and parties, never the list's addresses, phones or emails. It refuses a file it can't read (Cloudflare's check, a list whose layout changed, one missing most of its races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
