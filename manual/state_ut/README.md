# Utah's list of candidates, saved by hand

The Lieutenant Governor's Office publishes the general election's candidates as its General Election Certification, a scanned PDF with no text a program can read (vote.utah.gov, "2026 General Election Certification"). Its text is copied by hand into a text file, and Pallot imports that. Pallot never fetches it.

The certification is the general election's ballot: each party's nominee once, the unaffiliated candidates, and the judges standing for retention, in the ballot's order. The import refuses a race with two candidates of one party, which would mean a primary's list.

Do this again whenever the certification is amended (a withdrawal, a replacement).

## 1. Save the list

1. Download the latest certification from https://vote.utah.gov/ (in 2026, "2026-General-Election-Certification-Amended-09-21.pdf").
2. Copy the text of every page into a text file in this folder (`certification.txt`), with a PDF reader's text recognition. Keep the cover page's title ("2026 GENERAL ELECTION CERTIFICATION"): it says which election the list is for.

The saved file stays on your machine: this folder's files aren't committed.

## 2. Import it

```bash
uv run pallot-bundle import-list ut manual/state_ut/certification.txt
```

The import reads the candidates and writes `bundles/data/state_ut.json`, which holds only their races, names and parties. It refuses a file it can't read (no year in its title, a candidate's line without a party, fewer than four U.S. House or 75 State House races), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Text recognition misreads some names ("CHRJS REID"). The import puts right the ones found in the 2026 certification; after importing a new one, compare the names in the bundle with the PDF, and add any other misreading to `READ_AS` in `pallot/states/ut.py`. A party name it can't read stops the import, with the line.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list.
