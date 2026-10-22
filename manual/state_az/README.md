# Arizona's list of candidates, saved by hand

Arizona's election sites answer scripts with a bot check, and Pallot never gets around one. So the Secretary of State's list of candidates is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the office revises the list (withdrawals, replacements).

## 1. Save the list

1. Open https://apps.arizona.vote/electioninfo/Election/69 (the November 3, 2026 General Election) and wait until the candidates show. A page titled **"Just a moment..."** is the bot check, not the list: don't save that one.
2. Then either:
   - **Save the page:** Ctrl+S, "Webpage, HTML only", into this folder; or
   - **Copy the data request:** press F12, open the Network tab, reload, find the request that returns the candidates (filter by Fetch/XHR or Doc), right-click it, Copy as cURL (bash), run that command in a terminal, and send its output to a file in this folder (add `> manual/state_az/candidates.json` to the end).

The saved file stays on your machine: this folder's files aren't committed, since the page carries candidates' addresses and phone numbers.

## 2. Import it

```bash
uv run pallot-bundle import-list az manual/state_az/<the file>
```

The import reads the candidates and writes `bundles/data/state_az.json`, which holds only their offices, names and parties. It refuses a file it can't read (the bot check, a page whose layout changed), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
