# Georgia's qualified candidates, saved by hand

Georgia's ballot comes from two official sources:

- **The party nominees** (each party's primary winner, or its runoff's): Pallot reads them from the Secretary of State's results site, results.sos.ga.gov, on its own. Nothing to do here.
- **Everyone else** (independents, political bodies, nonpartisan and local offices, special elections): the Secretary of State's list of qualified candidates. Its site, mvp.sos.ga.gov, answers scripts with Cloudflare's check, and Pallot never gets around one. So the list is saved in your own browser, and Pallot imports the saved file. Pallot never fetches it.

Do this again whenever the list changes (a candidate qualifies, withdraws or is disqualified).

## 1. Save the list

1. Open https://mvp.sos.ga.gov/s/qualifying-candidate-information in your browser, and choose the 2026 General Election.
2. Press F12 to open the developer tools, and go to the **Network** tab. Reload the page if the tab is empty.
3. Type `aura` in the Network tab's filter. Of the requests it shows, click each and look at its **Response** until you find the one whose answer has the candidates (it starts `{"actions":[{` and holds names like `Name_on_Ballot__c`).
4. Save that answer into this folder as `georgia.json`: right-click the request, then **Copy** > **Copy response**, paste it into a new file, and save it as UTF-8. If what you copied starts `<!DOCTYPE html>` and says **"Just a moment..."**, that's Cloudflare's check, not the list: wait for the page to show the candidates and copy the answer again.

The saved file stays on your machine: this folder's files aren't committed. It has the candidates' emails, phones and addresses, which Pallot never keeps.

## 2. Import it

```bash
uv run pallot-bundle import-list ga manual/state_ga/georgia.json
```

The import reads the qualified candidates (leaving out the disqualified and withdrawn ones) and writes `bundles/data/state_ga.json`, which holds only their offices, ballot names, parties and whether they hold the seat. It refuses a file it can't read (Cloudflare's check, an answer without the candidates), and then the last good copy keeps serving. Commit the bundle, and restart Pallot to load it.

Settings shows the date of the last import. `pallot-bundle refresh` and `pallot-cache refresh` skip this list; the nominees' bundle, `state_ga_results`, is refreshed with the others.
