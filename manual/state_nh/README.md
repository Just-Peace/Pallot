# New Hampshire's list of candidates, saved by hand

The Secretary of State publishes the general election's candidate list as a PDF (https://mm.nh.gov/files/uploads/sos/docs/2026-ge-candidate-list.pdf, linked from https://www.sos.nh.gov/elections). Its site answers "Access Denied" to programs, so the PDF is downloaded in your own browser, its table is turned into a CSV, and Pallot imports that. Pallot never fetches it.

In 2026 the CSV was transcribed from the PDF by an AI tool, not exported by the Secretary of State. Transcriptions slip: before importing, look for names that are a column's name ("Domicile"), garbled letters, a candidate under the wrong district, or a race with more of one party's candidates than its seats. The import refuses a row whose name is a column's name, and an office or district it doesn't know.

It's the general election's list, so primary losers are off it. A candidate nominated by two parties is on it twice, once for each, and Pallot shows them once with both parties.

Do this again whenever the list changes (a withdrawal, a replacement).

## 1. Save the list

1. Download the PDF in your browser.
2. Turn its table into a CSV with the columns Office / Section, District / County, Candidate Name, Domicile, Candidate Address, City/State/Zip and Party (only Office / Section, District / County, Candidate Name and Party are read), a row per candidate, and save it into this folder. A State Representative's district is its county and number ("HILLSBOROUGH District 12"); every other district is "District 2".

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list nh "manual/state_nh/<the file>.csv"
```

The import reads the candidates and writes `bundles/data/state_nh.json`, which holds only their offices, names and parties. It refuses a file it can't read (columns changed, an office or district it doesn't know, fewer than 24 State Senate or 190 State House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

The list doesn't name its election: its candidates are put in the 2026 general election. For another year's list, change the year in the reader first.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
