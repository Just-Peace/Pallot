# Massachusetts's list of candidates, saved by hand

The Secretary of the Commonwealth lists the state election's candidates on one web page (https://www.sec.state.ma.us/divisions/elections/research-and-statistics/2026-state-election-candidates.htm). Its site turns programs away, so the page is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

It's the November state election's list, made after the September primaries, so primary losers are off it. The import refuses a race with two candidates of one party, which would mean a primary's list.

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the page

1. Open the page in your browser, and wait for the candidates to show.
2. Save it ("Save page as", the web page's HTML only) into this folder. Its title, "2026 State Election Candidates", names the election's year.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list ma "manual/state_ma/<the file>.html"
```

The import reads the candidates and writes `bundles/data/state_ma.json`, which holds only their offices, names and parties, never their addresses. It refuses a file it can't read (the site's bot check, an office or district it doesn't know, fewer than nine U.S. House, 35 State Senate or 140 State House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

The page prints a few candidates without a party, and Pallot shows them so. The Governor's race is one ticket with the Lieutenant Governor, named by their surnames as the ballot prints them ("Healey and Driscoll").

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
