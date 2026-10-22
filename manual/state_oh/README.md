# Ohio's statewide races, transcribed by hand

Ohio has no statewide list of candidates: its 88 county boards of elections certify them. And ohiosos.gov answers scripts with Cloudflare's check, which Pallot never gets around. So Ohio's statewide races are typed by hand into `ohio.json`, in this folder, and Pallot imports that file. Pallot never fetches anything from ohiosos.gov.

## Where the data comes from

The candidates were transcribed from the Secretary of State's **Official Sample Ballot for the November 3, 2026 General Election** (Directive 2026-45):

- the sample ballot: https://www.ohiosos.gov/assets/dir2026-45-official-sample-ballot-november-3-2026.pdf
- the Secretary of State's directives, where it was published: https://www.ohiosos.gov/elections/elections-administration/directives

The file covers only the races on every Ohio voter's ballot: Governor and Lieutenant Governor (as a ticket), Attorney General, Auditor of State, Secretary of State, Treasurer of State, the Ohio Supreme Court, and the U.S. Senate (an unexpired term). Its `scope.type` says so (`statewide_offices_only`), and the import refuses a file that says anything else. Ballots in Ohio get the U.S. House race from the FEC's filers instead, marked unverified; the Legislature's, county and local races aren't shown.

## Updating it

Do this when the Secretary of State issues a new sample ballot, or a candidate withdraws or is replaced.

1. Open the sample ballot in your browser (the site blocks scripts, not people) and edit `ohio.json` to match it: each contest's `office`, `vote_for` and `candidates`, each candidate's `name` and `party` as printed, and for Governor the `running_mate`. Two contests for the same office (two Supreme Court seats) are told apart by the date in their `term` ("Full term commencing 2027-01-01"). A U.S. Senate `term` saying "Unexpired" marks it an unexpired term. Update `source` if the directive changes.
2. Import it:

```bash
uv run pallot-bundle import-list oh manual/state_oh/ohio.json
```

The import writes `bundles/data/state_oh.json`. It refuses a file it can't read (not JSON, another scope, no contests), and then the last good copy keeps serving. Commit both files, and restart Pallot to load the bundle.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
