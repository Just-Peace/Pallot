# Pallot

A voter's personal ballot, currently for Texas addresses. Enter a home address and Pallot shows every race on that voter's ballot, with candidates in ballot order. Each candidate carries information from several sources. You can pick candidates, write notes, and print your picks to take to the polls.

You run it yourself, in Docker or with uv, and use it in your browser.

Pallot is made by [Just-Peace](https://github.com/Just-Peace) for American voters who'd rather see the whole ballot for themselves. We don't back any candidate or party. Your vote is yours.

## Quick start

Get the code, and optionally a settings file:

```bash
git clone https://github.com/Just-Peace/Pallot.git
cd Pallot
cp .env.example .env    # optional: this is where the FEC key goes (see below)
```

Then run it one of two ways.

### With Docker

Needs [Docker](https://docs.docker.com/get-docker/) with Compose 2.24 or later.

```bash
mkdir -p data                   # where Pallot keeps its cache and settings
docker compose up -d --build    # build the image and start Pallot in the background
```

Open http://localhost:8000, or `http://<this machine's address>:8000` from another device. It listens on every network interface, and Pallot has no login, so run it only on a network you trust. To keep it to this machine, see [Docker](#docker).

```bash
docker compose logs -f                     # follow the server log
docker compose down                        # stop it (data/ stays)
git pull && docker compose up -d --build   # update to the latest version
```

### With uv (local)

Needs [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
uv sync           # installs Pallot and its dependencies (and Python, if needed) into .venv, pinned by uv.lock
uv run pallot    # serves http://127.0.0.1:8000 until Ctrl+C (--port picks another port)
```

Open http://127.0.0.1:8000. It only listens on this machine, because Pallot has no login; to use Pallot from other devices, run it with Docker on a network you trust. To update: `git pull && uv sync`, then start it again.

### The FEC key (optional)

Pallot needs no keys to run. To break down congressional candidates' money (where it came from, donation sizes, largest donors, outside spending), it needs a free FEC key:
1. Get one from the [OpenFEC developers page](https://api.open.fec.gov/developers/); api.data.gov emails it to you.
2. Put it in `.env` as `PALLOT_FEC_API_KEY=...`. The FEC lets each key make 60 calls a minute, and Pallot paces itself to stay under that. For more, add up to four more keys as `PALLOT_FEC_API_KEY2` to `PALLOT_FEC_API_KEY5`: Pallot uses them in turn.
3. Restart Pallot: `docker compose up -d`, or Ctrl+C and `uv run pallot` again.

Without a key, Pallot uses the shared `DEMO_KEY`, which only allows race totals and runs out after a few requests. The other settings are under [Configuration](#configuration).

## Using it

- **Left pane**, the same on every page. On a phone or a narrow window it's a **top bar** instead, with your address and the pages each behind a button.
  - at the top, **Your ballot**, with your address under it. After a lookup the address is saved in the browser and shown as a card with its city and county, and the election ("November 3, 2026 · 2026 November General Election"). **Change** opens the form again; on the other pages it takes you to the ballot with the form open.
  - **«** at its top folds the pane into a narrow rail of icons, each named in a tooltip; **»** brings it back. The choice is remembered in the browser. On the ballot, the sections then show as chips in the strip at the top. The pane opens again by itself when the address form or an error needs to be seen.
  - while you type an address, **suggestions** from Ballotpedia's address search appear under the box, once you've typed a house number and a few letters of the street: ↑/↓ and Enter pick one, which only fills the box in. Only Texas addresses are suggested. Turn them off in Settings to get the browser's own address autofill back.
  - on the ballot, the list of sections, with how many races in each you've picked. The section on screen is highlighted as you scroll. On a phone they're a row of chips that stays in view.
  - on Settings, FAQ, About and Privacy, the list of that page's sections, to jump to one. The section on screen is highlighted as you scroll. On a phone they're under **Menu**, which closes when you pick one; in the folded rail they're hidden.
  - at the bottom, links to **Settings**, **FAQ**, **About** and **Privacy**
- **Footer**, on every page, always in view at the bottom of the window: a reminder that Pallot is unofficial, **Sources** (About's list of where the information comes from), and the version you're running with its commit, such as `v1.0.0-g1a2b3c4`. About shows it too.
- **Back to top:** once you've scrolled a screen, a round arrow button at the bottom right goes back to the top.
- **First lookup:** a lookup whose data isn't saved yet can take several seconds. The races show as soon as they're known, and the money, polls and endorsements follow; Pick by rule, Details and Print wait for them. Looking the same address up again is instant. The very first lookup after installing Pallot (or after `pallot-cache rebuild` deleted the precinct map) also downloads the election precinct map, about 45 MB, and waits up to 20 seconds for it. If it isn't done by then, the ballot shows without your election precinct and says to reload the page in a minute. Lookups while it's still downloading don't wait for it.
- **Top of the ballot**, staying in view as you scroll:
  - a progress bar counting races and propositions ("5 of 12 races · 1 of 2 propositions");
  - **Next race to pick** opens the next race you haven't picked and goes to it. `j` and `k` move to the next and previous race.
  - **Minimal** | **Simple** | **Detailed**, how much of the ballot shows (Simple at first): Minimal folds everything, leaving only the races and their candidates. Simple folds the map of your districts and where the dates and districts come from (a **Where these come from** link shows it, and hides it again), and shows the funding, polls and endorsements. Detailed opens everything. With your own mix of switches, neither is selected.
  - **Options** (the gear) opens the rest:
    - **Expand all** and **Collapse all**;
    - **Show**: a switch each for the **Map of your districts**, **Funding** (the races' money boxes and the candidates' Funding lines), **Polls**, **Endorsements**, and **Where dates & districts come from**. Choosing Minimal, Simple or Detailed sets them all again;
    - **Collapse a race when I pick** (on at first), and **Only races I haven't picked**;
    - **Open Settings**, where Ballot view has the same choices.

    A change shows at once, in every open Pallot tab, and is remembered in the browser. A box you opened or folded by hand goes back to the switch when it changes.
  - **Pick by rule** picks by party, endorsement lists, TrackAIPAC, Vote for Peace, money and polls (below).
  - **Clear picks**, in red, clears your picks, notes and write-ins at once, and offers **Undo** for 10 seconds.
  - **Print my picks** (below).
- Under it, two cards, side by side (and as tall as each other) on a wide screen, and one above the other on a phone, then the map of your districts.
- **When to vote:**
  - the election's key dates from the Texas Secretary of State: the last day to register, early voting, and Election Day with the polls' hours. The next date still to come is in bold with how far off it is ("in 6 days"); past ones are in gray.
  - a calendar icon next to each date downloads it as a calendar file (`.ics`), and **Add all to calendar** downloads every date still to come. The events are all-day and have no place, since polling places aren't known. Importing a file again updates its events rather than adding copies.
  - three buttons under the dates: **Am I registered?** opens the state's My Voter Portal, which also shows your polling place once you log in; **Where to vote** opens the list of county elections offices, since each county sets its own polling places; **Add all to calendar** (above). The card's source line links to **VoteTexas.gov**, the state's voter site.
  - **Voting by mail?**, closed at first, says who can vote by mail in Texas and when the application must arrive (received, not postmarked), with its own calendar icon.
- **Your districts**, like your voter registration certificate, in three lines:
  - U.S. House, State Senate, State House and State Board of Education;
  - your county, with your election precinct, your commissioner precinct and your justice of the peace precinct (which is also your constable's);
  - your city, city council district and school district.

  A State Senate or State Board of Education seat that isn't up this time is in a gray chip, with a line saying so ("State Senate 14 isn't up for election this time"). The commissioner and JP precincts come from your county's own records when Pallot has them (see below), and otherwise from Ballotpedia, which names a precinct only when it has a race on this ballot; the city council district comes from Ballotpedia. The card's small print says which gave each. The pencil at the top of the card turns every number (U.S. House, State Senate, State House, SBOE, commissioner and JP) into a box in its place, to change it from your voter registration certificate; the reset arrow next to it puts the looked-up numbers back (it's grayed out until you've changed one). Only the numbers you change become yours; the others keep following your address, your county's records and Ballotpedia. A district you enter decides which of the state's races are on your ballot, and the map draws it. When races depend on a precinct Pallot doesn't know, it shows as an amber dash, and the card says which precinct to enter from your voter registration certificate; **Enter it** opens the boxes, as the pencil does. After **Update my ballot**, a message at the foot of the window offers **Show**, which goes to the races for your commissioner and JP precincts. If the address could only be placed approximately, the card says to check the districts.

  Your **election precinct** ("Precinct 300", the "Pct" on your voter registration certificate) comes from the Texas Legislative Council's map of every county's election precincts; the card's small print names the map. It's not your commissioner or JP precinct. It isn't shown for an address that could only be placed approximately, or one near the line between two precincts, and a note under the ballot says why. Your certificate wins if they differ.

  Each election precinct lies inside one commissioner precinct and one JP precinct, so in seven counties your election precinct also gives those two, from the county's own records:
  - **Harris, Dallas, Tarrant, Travis and Fort Bend** publish a list of their election precincts with each one's commissioner and JP precinct (Fort Bend's has commissioner precincts only, so its JP precinct comes from Ballotpedia). Pallot uses a county's list only when it has exactly the precincts on the Texas Legislative Council's map, so it's never another year's.
  - **Bexar and Denton** publish maps of their commissioner and JP precincts instead. Pallot takes points spread through your election precinct, each at least 160 feet from its edges, and gives a number only when they all fall in the same one.

  A number you enter wins over the county's, and the county's over Ballotpedia's; when the county and Ballotpedia differ, a note says so. Near the line between two election precincts, a number is given only when both precincts have the same one. Other counties work as before.

- **Map of your districts:** a street map from OpenStreetMap with the outline of each district and of your election precinct, in its own color and line (solid, dashed, dotted, or dashes and dots), and a pin at your address. It opens centered on your address, zoomed so your election precinct fits around it, close enough to see your streets.
  - Right above the map, a button for each district, with a sample of its line: pick one, or its line on the map, to highlight it and zoom to it; pick it again, or the pin button on the map, to come back to your address. Hover over a line to see which district it is.
  - Drag the map to move it, and zoom with **+** and **−**, or with the scroll wheel once you've clicked the map (so scrolling the page never zooms it by accident). On a phone, move and zoom it with two fingers; one finger scrolls the page. With the map selected, the arrow keys move it.
  - The outlines are simplified to about 160 feet (your election precinct to about 16 feet), so near a boundary, go by the district numbers.
  - The street map's tiles come from OpenStreetMap through the Pallot server, which keeps them. Turn the street map off in Settings to see the outlines alone.
  - Click the map's heading to fold it away, as you would a race, and again to bring it back. It's folded at first (open in the Detailed view), and your choice is remembered in the browser: it's the **Map of your districts** switch under Options. While it's folded, nothing is fetched for it.
- **Precincts:** until your commissioner and JP precincts are known, the races that depend on them are listed under "Depends on your commissioner or JP precinct", with a link up to Your districts.
- **Races:** click a race's heading to collapse it to one line, with the race on the left and your pick ("✓ James Talarico") on the right. Collapsed races stay collapsed when you come back.
  - While you scroll through a race, its heading stays at the top, under the progress bar, until the next race comes.
  - Once you've picked, the heading shows your pick, collapsed or not, with **✕ Clear** next to it to take it back. A message at the foot of the window offers **Undo**. Propositions have it too.
  - With Ballotpedia on (it starts off), races the state's ballot doesn't have, such as city council, school board and appraisal district races, say "Listed by Ballotpedia" under their name.
  - Ballotpedia's notes on a race (a replacement nominee, a redrawn district) show at the top of it, with Ballotpedia's link.
  - **Incumbent** comes from the state's filing, from Ballotpedia when it matches the candidate exactly in the same race, or from the seat holders' lists when the holder is on the ballot by full name (or first and last name).
  - **Open seat**, in a U.S. Senate, U.S. House, State Senate or State House race's heading, means whoever holds the seat now isn't running for it, or the seat is empty. A candidate of the holder's party who isn't the holder has a **Party holds seat** pill next to their party; hover over it to see who holds the seat ("Held by John Cornyn, a Republican"). A U.S. House holder was elected under the district's lines from before Texas redrew its map in 2025, and the pill's tooltip says so. Turn off **Seat holders** in Settings to hide all of it. A first initial alone (Troy and Trever Nehls) isn't enough to say anything.
- **Picks follow the party:** a picked candidate's row and their race take their party's color on the edge (Republican red, Democratic blue, Libertarian yellow, Green green, gray otherwise), with no tint behind the row. Party badges are solid color so they stand apart from the sources' badges.
- **Money:** congressional and state races have a money box above the candidates, open at first, laid out like the poll box: "Money raised for the 2026 election (2021–26) · reports through Sep 30, 2026", then one bar for the total the race's candidates raised, a segment per candidate in their party's color, and a legend with what each raised and the total. Cash on hand and outside spending are in **Compare funding** and Details. In its corner, **Compare funding** (below) and **FEC ↗** (or **TEC ↗**) opens the source. Click the box's title to fold it to that line, or turn off **Funding** under Options to fold every race's box and hide the candidates' Funding lines. A **?** after a name means the source only likely matched that candidate. The figures come from the FEC for Congress and the Texas Ethics Commission for state offices. Each candidate's tab from that source in Details breaks it down:
  - where the money came from;
  - donation sizes;
  - where donors live;
  - the largest donors (the FEC groups them by employer);
  - outside spending.

  The tab starts with the candidate's **Funding** chips, the same as on their row.

  **Compare funding**, on the money box's line even while it's folded, puts everyone in the race side by side: totals, then each breakdown with one bar per candidate, and the largest donors and outside spenders in columns, with names that appear in more than one candidate's list marked. The FAQ's "Campaign money" section explains how each figure is put together. Outside spending is marked with a blue "for" or an amber "against" the candidate; none of it went to the campaign.
- **Polls:** U.S. Senate, U.S. House and Governor races with public polls show a poll box under the money box, "Polls · latest poll Oct 5, 2026", with one bar: each candidate's median share, in their party's color, with the rest (undecided and others) in gray. Its legend lists the candidates the polls asked about and Undecided / other. In its corner, **29 polls** says how many polls the bar is worked out from (hover for how, click for the FAQ's answer) and **FiftyPlusOne ↗** opens the source. The median is over each pollster's latest poll of the matchup actually on the ballot, likely voters where a poll asked them. Click the box's title to fold it, or turn off **Polls** under Options to fold every poll box. Each candidate's **Polls** tab lists the polls. Most House districts have no polls, so they show no bar.
- **Write-ins:** the candidates who filed as write-ins with the Texas Secretary of State are listed in their race after the printed names, marked **Write-in**. Pick one and it shows on the collapsed line and the printed sheet as "Name (write-in)", since you write the name in yourself. Every race also ends with a write-in line. Type someone else's name and it becomes your pick; it shows on the collapsed line and the printed sheet as "Name (write-in)". In Texas a write-in only counts for someone who filed as a write-in candidate, and the page says so when you pick one.
- **Each candidate has:**
  - a pick button, by their photo and name, with their party and pills such as **Incumbent** beside the name, and an outlined red **Banned** first when they're on your ban list, which also strikes their name through in red
  - a note
  - **Profile**, under their name, which opens their Details on the **Profile** tab (on **Issues** when it's empty): a section for their filing with the state (**Texas SOS**), then one for **Ballotpedia**'s profile when Ballotpedia is on. Next comes **Issues**: 30 issues in five groups (Rights & society, Economy, Government, Foreign policy & defense, Public services), a section each, each issue a link that searches the web for where the candidate stands on it, in neutral words, with the engine you pick in Settings. After it come the tabs of the other sources that have something on them: the money (FEC for Congress, Texas Ethics Commission for state offices), with a **Totals** section and a section per breakdown, then Polls, then **Endorsements**, with a count. Endorsements holds TrackAIPAC, Vote for Peace and the endorsement lists, a section per source with everything it has on the candidate, all open, the ones for the candidate (green) first, then the ones against (amber); click a section's name to fold it to its name and chips. Every section on Profile, Issues, the money tab and Endorsements starts open and folds the same way. **‹** and **›** step through the race's other candidates without closing it, staying on the tab you're on. **Search ↗** (or **Ask ↗**), **Ban** (**Unban** once banned; see **Ban list** below) and **Pick** (**Unpick** once picked) sit at the top beside ‹ › ✕, on a phone on a line of their own. Scroll down and the top shrinks to a small photo, the name in its party's colour, and the buttons' icons; the tabs stay under it.
  - a **Search ↗** link (**Ask ↗** when it's an AI assistant), beside Note, that searches for their name, office and place, using Google AI Mode unless you pick another AI assistant (Perplexity, ChatGPT, Claude, Microsoft Copilot or Grok) or a search engine (Google, Bing, DuckDuckGo, Brave, Yahoo, Startpage, Ecosia or Kagi) in Settings
  - under their name, up to two lines, each only when it has something: **Endorsements** and **Funding**. An endorsement is green, with the source's name: TrackAIPAC's endorsement, Vote for Peace's Ally, or an endorsement list. One against is amber and says so: **TrackAIPAC watchlist** or **Vote for Peace: Opposed**. The green ones come first. A neutral one (Vote for Peace's Neutral) shows only in Details. An endorsement chip opens that source's page for the candidate (↗); a Funding chip opens Details on the money tab. Turn off **Endorsements** under Options to hide the first line: a candidate who has any then shows one small button, "3 endorsements", that opens it.
  - **Funding** sums up where the campaign's money comes from, worked out from its reports. Each chip says **Mostly** when its side is more than half and **Overwhelmingly** when it's more than three quarters. Green: **small donors** (donations under $500 are most of what it raised) and **Texas donors** (most of the itemized donations with an address came from Texas). Amber: their opposites, **large donations** and **out-of-state donors**, and **self-funded** (the candidate's own gifts and loans are most of it). At exactly half there's no chip. The line starts with what the campaign raised (**Raised $9.2M**), then these chips, green before amber, and ends with outside spending: for Congress **Outside spending for** (blue) and **Outside spending against** (amber), for state offices just **Outside spending**, since the TEC doesn't record which side it took. Hover over a chip for the figure; click one to open the money tab in Details. A campaign that raised less than $10,000 gets no Mostly or Overwhelmingly chips. For Congress, the Mostly and Overwhelmingly chips and outside spending need the FEC key; self-funding is for Congress only. Turn off **Funding** under Options to hide the line, with the races' money boxes.

  A **?** on a source's chip, its tab or section in Details, or a name in the money box means that source only likely matched the candidate, so check it.
- **Endorsement lists:** some organizations' lists of the candidates they endorse come with Pallot, and others (Muslims United PAC's, CAIR Action's and Emgage PAC's) are fetched from the organization's website; About and the FAQ name the ones in your version. A list that comes with Pallot is a copy made once, on the date Settings shows, and never fetched again; a fetched one is kept a week, and Settings shows when it was fetched. A candidate on a list has the list's name under **Endorsements** on their row, and a tab in Details with the office as the organization lists it, its note, and a link to its list. A list keeps every state it covers; a lookup uses only the candidates in the address's state (Texas, for now). Settings shows how many candidates a list has in Texas and in all.
- **Pick by rule:** picks across your ballot at once, since Texas has no straight-ticket voting. Open it from the top of the ballot for every race, or from the funnel in a race's heading for that race; **Apply to** can also be one section.
  - **Pick:** any of the parties you choose (a chip for each party on your ballot, with how many races it's in, and one for the declared write-ins), and then only if all of these hold:
    - incumbents only, or challengers only;
    - any endorser you choose endorses them: TrackAIPAC, Vote for Peace (the candidates it calls an Ally) and each endorsement list, one chip each for those that endorse someone on your ballot, all off at first;
    - what they raised, spent, have on hand, or had spent for them from outside is under (or over) an amount, or the least (or the most) in the race;
    - small donations, under $500, make up at least a share of what they raised (50% at first);
    - donors in Texas gave at least a share of their itemized donations with an address (50% at first);
    - they lead the polls.
  - **Don't pick, and take back:** anyone on your ban list (on at first, shown when someone on your ballot is on it), on TrackAIPAC's watchlist, opposed by Vote for Peace, with Israel lobby money over an amount ($0 at first), whose own gifts and loans make up over a share of what their campaign raised (50% at first; congressional races only), or polling under a share (5% at first). A pick of theirs is taken back, even one you made yourself.
  - The conditions are grouped under Party, Incumbent or challenger, Endorsements, Money and Polls. One your ballot has nothing for (no polls, say) isn't shown; a line under them names it.
  - A TrackAIPAC, Vote for Peace, endorsement list, money or polls condition counts only in races its source covers (Vote for Peace's, the races where it has someone; an endorsement list's, the races where it endorses someone): "Democrats who spent under $1M" still picks a county race's Democrat. Small donations, Texas donors and self-funding need an FEC key in congressional races; self-funding isn't known in state races. Without the Write-ins chip, a rule picks only the names printed on the ballot.
  - A race with more matches than seats is left for you, never guessed, a tie for the least or the most included. **Don't replace picks I've already made** (on at first) leaves the races you've picked alone, apart from what Don't pick takes back.
  - Beside the rule (under it, on a phone), the dialog says it in words ("Pick Democratic candidates who spent under $1M. Don't pick anyone on TrackAIPAC's watchlist, and take back their picks."), then what it would do ("43 races to pick", "1 pick taken back", "5 with no match"), race by race, as you change it. Nothing changes until **Apply**, which offers **Undo** for 10 seconds. With **Collapse a race when I pick** on, Apply folds the races it fills, and Undo opens them again.
  - **Reset** clears the rule in the dialog, and **How rules work** at the bottom explains the above.
  - The last rule you applied is remembered in the browser.
- **Ban list:** candidates you never want to vote for. **Ban**, beside a candidate's Note and Search or in their Details, adds their name; **Unban** takes it off again (with any pattern from Settings that matched them), each with **Undo**. You can also type names in Settings, as part of a name or a pattern (`^Smith`, `Jo(e|hn) Doe`) to catch every spelling, matched ignoring case. A candidate on it has an outlined red **Banned** pill beside their name and their name struck through, on the ballot and in Details; hover over the pill for the entry that matched. The list is kept only in this browser.
- **Print my picks:** a **full page** (with your notes and blank lines for races you haven't picked, if you want them), or a **wallet card** to cut out and fold. Both start with Election Day and the early-voting dates. The full page lists your districts, with your election precinct as "Pct 300". Your address isn't printed, so the sheet doesn't give away where you live. Your browser's own print (Ctrl+P) prints the same sheet with your current picks, laid out as you last chose in Print my picks (at first, a full page with your notes).

Picks, notes, collapsed races, your pick rule and your ban list are kept in the browser's `localStorage`, never on the server.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → county, U.S. House, State Senate and State House districts | already on the 2026 maps (120th Congress, 2026 legislative districts) |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Google Geocoding API | last fallback, when neither the Census nor Nominatim can match an address (new streets, mostly) | needs `PALLOT_GOOGLE_API_KEY`; without one it's never asked; results flagged as approximate unless they hit a building |
| Ballotpedia's address search | address suggestions while typing | an **unofficial** endpoint (Esri data), like Ballotpedia's ballot below; it has its own switch in Settings |
| Texas Legislative Council map (PLANE2106) | State Board of Education district, and its outline on the map | downloaded once |
| Texas Legislative Council precinct map (data.capitol.texas.gov, the `precincts` maps) | your election precinct, and its outline on the map | the portal's list of maps is asked once a week; the newest map, a primary's or a general's (now the 2026 primary's, about 45 MB), is downloaded on the first lookup and again only when a newer one is listed. Nothing about you is sent |
| County map servers: Harris, Dallas, Tarrant, Travis, Fort Bend, Bexar and Denton | your commissioner and JP precincts, from your election precinct | each county's list of its election precincts, or its maps of its commissioner and JP precincts, found by name (the newest year, never a proposal) and downloaded whole, at most once a week, when you look up an address there. Nothing about you is sent |
| US Census TIGERweb | the outlines of your U.S. House, State Senate and State House districts, for the map | one request per district, with its number and never your address |
| OpenStreetMap tiles (tile.openstreetmap.org) | the street map under the outlines | through the Pallot server, only the tiles of the area you look at, following OpenStreetMap's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); drawn with [Leaflet](https://leafletjs.com), which comes with Pallot |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Texas Secretary of State, Important Election Dates | each election's last day to register, early voting and mail-ballot deadline | one public web page (sos.state.tx.us), read whole |
| Ballotpedia | city council, school board and special-district races, and others the state doesn't list (appraisal district boards); notes on races; JP/constable/commissioner precinct (when it has a race on this ballot) and city council district; candidate profiles | an **unofficial** endpoint. Its terms forbid commercial scraping, so it starts off: turn it on in Settings for personal use |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)) |
| Vote for Peace (voteforpeace.info, from Organize for Peace) | whether it calls a candidate an Ally, Neutral or Opposed, on war, human rights and lobby money, with the groups it cites and its notes; every level, from Congress to county courts and city councils | bundled with Pallot, used with Organize for Peace's permission (see [Bundled snapshots](#bundled-snapshots)); starts off, turn it on in Settings |
| Endorsement lists (one file per organization, in `pallot/endorsements/`) | the candidates an organization endorses, with its note and the office as it lists it | each a copy made once, frozen, part of Pallot and never fetched. About and the FAQ name the lists in your version |
| Live endorsement lists: Muslims United PAC (muslimsunitedpac.com) | the candidates it endorses, with its take on each and a link to their page on its site | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone |
| Live endorsement lists: CAIR Action (cairactionguide.org) | the candidates its Action Guide endorses or prefers, with that level in its words and a link to its list for the state | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone |
| Live endorsement lists: Emgage PAC (candidates.emgagepac.org) | the candidates it endorses, with its note on each when it has one, and a link to its list | the JSON list behind its donation page, the whole list in one request, the same for everyone; that request needs a token the page hands out, so the page is fetched first, and only when the list is |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them | the OpenFEC API, with a snapshot of its answers for Texas's federal races bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)). Without your own key, race totals only (see [The FEC key](#the-fec-key-optional)) |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | bundled with Pallot, built from TEC's nightly CSV export (see [Bundled snapshots](#bundled-snapshots)) |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API |
| Seat holders: the [congress-legislators](https://github.com/unitedstates/congress-legislators) project and [Open States](https://openstates.org) | who holds each U.S. Senate, U.S. House, State Senate and State House seat now, and their party: Open seat, Party holds seat, and Incumbent where the filing doesn't say | two public files (public domain and CC0), each downloaded whole at most once a week, and only when the ballot has a race of that body. Nothing about you is sent. Statewide offices, the SBOE, courts and local races aren't covered |

The Texas SOS data covers every race touching a county. Pallot keeps only the voter's congressional, legislative and SBOE districts; judicial and DA districts are whole counties. Commissioner, JP and constable races depend on the voter's commissioner and JP precincts. Those come from the numbers the voter enters under Your districts, the county's records (in the seven counties above), or Ballotpedia, in that order, where one number covers both the JP and the constable, since each justice precinct elects one of each; otherwise those races are listed under "Depends on your commissioner or JP precinct". Ballotpedia names a precinct only when it has a race on this ballot, from its district's name or, when that doesn't say which kind ("Fort Bend County Precinct 1"), from the races in it. Ballotpedia lists MUDs and water districts for a whole county, so those appear under "Special districts" as "may be on your ballot". Ballotpedia's other races are added when the state lists none of their candidates for that day, such as an appraisal district's board. The county's ballot order lists only the names printed on the ballot, so the declared write-ins come from the state's statewide candidate list, matched to the county's races by office (a county office's only from that county). A race with only write-ins isn't on the county's ballot order, so it's shown when Pallot can place it: a federal or statewide race, one of the voter's districts, or one of the county's own offices. A district judge or DA race with only write-ins isn't shown, since the list doesn't say which counties it covers. When Texas SOS has no ballot for the county, as for a special election, Pallot uses its statewide candidate list instead. That list doesn't say which counties judicial, DA and county races cover, so only federal, statewide, congressional, legislative and SBOE races are shown, and a note says so.

The election precinct comes from the newest precinct map, whether a primary's or a general's. The Texas Legislative Council publishes a general election's map only after that election, and counties can only redraw precincts in March or April of odd-numbered years, so a primary's precincts carry over to its general: 99.5% did in 2022 and 99.9% in 2024. An address's point and the middle of its census block must fall in the same precinct; when they don't, Pallot names both and doesn't pick one. That can't catch the geocoder putting an address on the wrong side of a street that's a precinct line, so your voter registration certificate wins.

Campaign money covers congressional races (FEC) and state races (TEC), which includes:
- statewide offices;
- the Legislature;
- the State Board of Education;
- appellate and district courts;
- district attorneys.

County candidates (county courts at law and probate courts included), precinct, city and school candidates file with their county or city, so their races show none.

What "raised" covers (the FAQ's "How are the FEC figures put together?" and "How are the Texas Ethics Commission figures put together?" go through every figure):
- **TEC totals:** the reports whose period ends after the last November general election, excluding daily pre-election and special-session reports, whose money is reported again later.
- **FEC totals:** the whole election period (two years for the House, six for the Senate).

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labeled **exact** ("Matched") or **likely** ("Likely match"), and ambiguous ones are left unmatched. A state race's candidates are matched to Ballotpedia within that race's own race on Ballotpedia's ballot (the one its candidates are found in), with the party to confirm, so a middle initial on one side still matches exactly; first names that only share an initial ("Tom" and "Thomas") stay "likely". With Texas SOS off, a state race's seat for the Texas Ethics Commission match comes from Ballotpedia's district ("Texas House of Representatives District 49" is State Representative, District 49), so a namesake elsewhere in Texas isn't taken for the candidate. TrackAIPAC lists members of Congress by their current seat, so a 2026 seat change after the 2025 redistricting shows up as "likely" unless TrackAIPAC's entry mentions the new seat. Vote for Peace names a candidate's office its own way ("TX State Representative", "Harris District County Court Judge" and a number), which Pallot reads as the seat; a court named without its place ("TX Supreme Court Justice") counts for any place on that court, and a county or city office for the county it names. In one race, one entry goes to one candidate: the closest name takes it, so "Kristen Hawkins" isn't also given to "Kyle Hawkins". The endorsement lists are matched the same way, from the office and district (or county) each entry names; an entry for another state is never matched.

## Caching

Pallot saves every answer it gets in `data/`, so looking up the same address again makes **zero** external calls, even after a restart. Settings shows how the last lookup used each source.

- Lifetimes:
  - reference data: 30 days
  - elections, ballot order and statewide candidate lists: 24 hours (a year for past elections)
  - empty ballot orders: 6 hours
  - geocodes: 30 days (an address that wasn't found: 1 day)
  - address suggestions: 30 days
  - Ballotpedia: 24 hours
  - FEC: 7 days (a year for past elections)
  - polls: 24 hours
  - key election dates: 24 hours
  - district outlines for the map: 30 days
  - the list of election precinct maps: 7 days; the map itself is kept until a newer one is listed
  - counties' lists of their election precincts, and their maps of commissioner and JP precincts: 7 days
  - street map tiles: 7 days, the least OpenStreetMap's policy allows
  - endorsement lists fetched from an organization's website: 7 days
  - who holds each seat: 7 days
  - after a failed request: its old copy is served for 15 minutes before the source is asked again
  - address suggestions, street map tiles, and addresses that weren't found, are deleted once they've been expired for 30 days (`PALLOT_TTL_PRUNE_AFTER`), when Pallot starts and every 6 hours while it runs. The street map's tiles are also kept under 512 MB and the suggestions under 64 MB, the oldest deleted first (`PALLOT_TILES_MAX_MB`, `PALLOT_SUGGEST_MAX_MB`). Everything else stays as the copy to show when a source is down.
  - Override any of these with `PALLOT_TTL_<NAME>` in seconds; see [Configuration](#configuration).
- The TrackAIPAC, Vote for Peace and Texas Ethics Commission data come with Pallot, so lookups never contact any of them; they're only fetched again by `pallot-cache hard-refresh` (see [Keeping the cache](#keeping-the-cache)).
- The endorsement lists that come with Pallot are part of it and are never fetched at all. The live ones are fetched whole, one request per list, at most once a week.
- Candidate details and the declared write-ins come from one statewide list per election (~2.6 MB, one request per day), not one request per candidate.
- If a refresh fails, the old copy is shown with a "data as of" note, and that request isn't retried for 15 minutes, so a source that's down doesn't slow every lookup. A source that fails before answering once has nothing to fall back on.
- An error that a source sends as if it were an answer counts as a failure too, so it never replaces the good copy: TIGERweb's and the counties' map servers answering with an error, or the Texas SOS's dates page coming back without its election dates (a maintenance page, say). With no good copy yet, the error is kept for 15 minutes, so lookups meanwhile don't ask again.
- If the Census geocoder, Nominatim or Google (each on its own), Texas SOS, Ballotpedia (its ballot or its address search, each on its own), FiftyPlusOne, the seat holders' lists, the Texas SOS's dates page, TIGERweb, OpenStreetMap's tile server or the Texas Legislative Council's portal (the precinct and SBOE maps) refuses a request, Pallot stops asking it for an hour; if a county's map server does, it stops asking all seven counties for an hour. What it already sent still shows.
- If the State Board of Education map can't be downloaded, lookups don't try again for 15 minutes, and your SBOE district is missing meanwhile. `pallot-cache refresh` always tries.
- If a precinct map's download fails, the map already kept stays, and lookups don't try that map again for a week (15 minutes while no map is kept), unless the portal lists a changed one. `pallot-cache refresh` always tries.
- Pallot sends at most 55 calls a minute with each FEC key, and waits only when every key has used its minute. If the FEC still answers that a key reached its rate limit, Pallot stops using that key for 2 minutes; if it refuses a key, for an hour. Meanwhile it asks with your other keys (`PALLOT_FEC_API_KEY2` to `5`). Settings names the key and why. When every key is resting, Pallot stops asking the FEC and shows what it already has meanwhile. A key you change in `.env` is used as soon as Pallot restarts. With `DEMO_KEY`, the limit is shared by everything on your IP address.
- `pallot-cache` doesn't ask a paused source either, and stops asking one that pauses partway through. The FEC is the exception, since nobody waits on a refresh: `pallot-cache` asks it more slowly (one call every 2 seconds per key, leaving half of each key's minute to a Pallot running meanwhile), and when every key is resting for a few minutes, it waits and carries on. Its refresh of TrackAIPAC and Vote for Peace stops at once if their site refuses it.

## Settings

The **Settings** page, linked from the left pane, has six sections: **Ballot view**, **Web search**, **Ban list**, **Sources**, **Appearance** and **Clear data**. On a phone, or with the left pane folded, a row of links to them stays at the top of the window. Everything you choose there is saved in your browser, so it changes only what you see, not anyone else using the same Pallot. The page:
- under **Ballot view**, chooses **Minimal**, **Simple** or **Detailed** (none, with "Your own mix, below", when the switches are mixed), and has a switch each for the map of your districts, funding, polls, endorsements, and where dates & districts come from, with a line on what each does, then **Collapse a race when I pick** and **Only races I haven't picked**: the same choices as the ballot's Minimal | Simple | Detailed and Options. An open ballot follows a change at once, in any tab;
- picks the web search engine or AI assistant;
- under **Ban list**, lists the names you banned from the ballot and lets you add a name or a pattern, or remove one with its ×;
- lists the sources in five groups, each with how many of its sources are on, and folds a group away when you click its heading (it stays folded in this browser):
  - **Address lookup & maps**: the address lookup (always on), election precincts, the counties' commissioner and JP precincts (which need election precincts on), the district outlines, the street map and address suggestions;
  - **Official ballot data**: Texas SOS, the key election dates, the FEC and the Texas Ethics Commission;
  - **Third-party ballot data**: Ballotpedia and the seat holders;
  - **Third-party polls**: FiftyPlusOne's polls;
  - **Third-party endorsements**: TrackAIPAC, Vote for Peace and each endorsement list, with **Turn all on** and **Turn all off** for the whole group;
- turns each of those sources on or off for you, except the address lookup. Your switches are kept in this browser and sent with each request, so the server builds your ballot with them; a source you haven't switched follows the defaults (see [Which sources start on](#which-sources-start-on));
- says whether the FEC is using your key, how old the FEC's and Texas SOS's bundled answers are, whether a source is paused (the address lookup and Texas SOS included), whether a map's last download failed, how old the Texas Ethics Commission snapshot is, when each endorsement list was captured or fetched, and how many candidates it has in Texas and in all;
- shows what the server has saved for each source (responses, size, when they were fetched, how many are past their lifetime) and how the last lookup used it (requests made, how old the data was), plus the total on disk;
- sets the appearance: **System** (the default) follows your device's light or dark setting, or pick **Light** or **Dark**. It changes at once, in every open Pallot tab;
- under **Clear data**, clears what this browser keeps:
  - **Clear my picks & notes**: your picks, notes, write-ins and pick rule. Your address stays;
  - **Clear browser data**: everything Pallot keeps in this browser, your address, sources, appearance, search engine, view choices and ban list included, so the ballot goes back to Simple.

  Both clear at once and offer **Undo** for 10 seconds.

Settings can't refresh or clear what the server saved: anyone who opens Pallot can open Settings, and it has no login. That's for whoever runs Pallot, on the machine it runs on: see [Keeping the cache](#keeping-the-cache).

Ballotpedia and Vote for Peace start off. Turn Ballotpedia on to add city council, school board and special district races (the ballot says so while it's off), and Vote for Peace to add its Allies and Opposed. When you go back to your ballot after changing a setting, it reloads with the new one. That includes a ballot kept by the Back button or left open in another tab. With Texas SOS off, the ballot comes entirely from Ballotpedia.

### Which sources start on

`pallot/sources.toml` declares which sources are on for someone who hasn't switched them, under `[sources]`, one `id = true` or `false` each (the ids `pallot-cache check` shows in brackets). Every endorsement list starts on. To change the defaults for everyone using your Pallot, don't edit that file: put a `sources.toml` in the data folder (`data/`, or `PALLOT_DATA_DIR`), listing only what you change, and restart Pallot. For example, to share Pallot with others without Ballotpedia's unofficial endpoints:

```toml
[sources]
ballotpedia = false
suggestions = false
```

A file Pallot can't use (a source that doesn't exist, a value that isn't `true` or `false`) stops it from starting, with a message saying what's wrong. Each person's own switches in Settings still win.

## Keeping the cache

`pallot-cache` checks, refreshes and prunes what Pallot keeps in its data folder. Run it on the machine Pallot runs on, with uv, or inside the container with Docker. It can run while Pallot does: the server picks up what it fetched.

```bash
uv run pallot-cache check                          # each source's saved copies, and how many are stale (past their lifetime)
uv run pallot-cache refresh                        # soft refresh: fetch again only what's stale, and a missing or newer map
uv run pallot-cache prune                          # delete what's no use even as a fallback, then shrink the file
uv run pallot-cache hard-refresh                   # fetch everything again, and refresh the bundled snapshots
uv run pallot-cache rebuild                        # delete everything saved, then fetch it all again (asks first)
docker compose exec pallot pallot-cache check      # the same, in the container
```

- **check** changes nothing and asks no one: for each source, its saved responses, their size, how many are stale, when they were fetched, whether it's paused, its maps or snapshot, and whether a map is missing or the portal lists a newer one.
- **refresh** asks again only for the responses past their lifetime, downloads the SBOE or precinct map when none is kept, and the precinct map when the portal lists a newer one (about 45 MB). The snapshots have no lifetime, so it leaves them.
- **prune** deletes expired address suggestions and street map tiles, addresses that weren't found, and the oldest tiles and suggestions past their caps, then shrinks the file. Pallot does the same when it starts, and every 6 hours without shrinking the file. It never deletes another source's copies, which stay to show when a source is down.
- **hard-refresh** asks again for every saved response, re-downloads the SBOE map, checks for a newer precinct map, and refreshes TrackAIPAC, Vote for Peace and the Texas Ethics Commission (see [Bundled snapshots](#bundled-snapshots); TEC's may download about 1 GB).
- **rebuild** deletes every saved response, pause and map, then fetches them all again, as hard-refresh does. The snapshots aren't deleted, only refreshed; `--reset-snapshots` puts them back as they came with Pallot first. `--delete-only` deletes and fetches nothing again: the next lookups fetch what they need, which is how to erase the addresses Pallot saved (`--only geocoding suggestions ballotpedia`). It asks first, unless you add `--yes`.
- The street map's tiles and the address suggestions are never fetched in bulk: they're only fetched as someone looks at the map or types an address, as OpenStreetMap's tile policy asks.
- `--only` takes source ids (`--only sos fec`) for every command but prune.
- It exits with 1 when something couldn't be fetched (the old copy stays), so it can run from cron or a systemd timer, for example once a night: `uv run pallot-cache refresh`.

## Bundled snapshots

The TrackAIPAC, Vote for Peace and Texas Ethics Commission data come with Pallot as snapshots in the repo. Pallot copies them into `data/` on first run, so ballot lookups never contact trackaipac.com, voteforpeace.info or TEC. Each has a row in Settings, which says how old it is:
- `pallot-cache hard-refresh` (or with `--only trackaipac`, `voteforpeace` or `tec`) fetches a new copy.
  - TrackAIPAC's checks the site's pages and saves only if the site changed.
  - Vote for Peace's fetches its All Candidates page (one request, about 7 MB) and saves only if a candidate changed.
  - TEC's first makes one small request to see whether TEC's nightly export (`TEC_CF_CSV.zip`, about 1 GB) has changed; if not, that's all. If it has, it downloads the zip in one request (a minute or two on a fast connection) and rebuilds the snapshot.
- `pallot-cache rebuild --reset-snapshots --only trackaipac` (or `voteforpeace`, `tec`) goes back to the snapshot that came with Pallot, then refreshes it.
- **TEC's download server blocks bursts of requests.** If a refresh says it was refused, try later, or download the zip in a browser, save it as `data/tec/TEC_CF_CSV.zip`, and run the refresh again.

Pallot also comes with some sources' answers (`bundles/data/`). For now that's:
- the FEC's answers for Texas's federal races: each seat's list of candidates and their totals, and the breakdowns of the candidates on the ballot;
- Texas SOS's statewide data: the elections of this year and next, its tables of counties, parties and filing statuses, and each upcoming election's statewide list of candidates (about 2.6 MB);
- Texas SOS's ballot order for every county in each upcoming election (about 10 MB). A county whose ballot order isn't published yet is left out, so a lookup there still asks Texas SOS for it, and asks again after 6 hours while it's empty.

At startup, Pallot puts them in its cache, dated when they were last checked, unless the cache has a newer copy. So a lookup asks a source only for what the bundle doesn't have, or once the bundle's answer is older than its bundle lifetime: the FEC's 7 days (`PALLOT_TTL_FEC_BUNDLE`); Texas SOS's elections 3 days, tables 30 days, candidate lists and ballot orders 2 days (`PALLOT_TTL_SOS_ELECTIONS_BUNDLE`, `PALLOT_TTL_SOS_REFERENCE_BUNDLE`, `PALLOT_TTL_SOS_CANDIDATES_BUNDLE`, `PALLOT_TTL_SOS_BALLOT_ORDER_BUNDLE`). After that, the live answer is kept for the source's usual lifetime. This matters most on a host whose `data/` starts empty at each restart. The source's row in Settings says how many answers came with Pallot and when they were checked.
- `uv run pallot-bundle refresh` rebuilds every bundle in the repo; `--only fec` (or `sos`, `sos_ballot_order`) limits it to the FEC's. `--due` skips a bundle checked more recently than it's worth (daily or weekly; the FEC's and Texas SOS's are daily), `--dry-run` says what would change, and `--force` writes even if nothing changed.
- The FEC's takes each upcoming election's federal races and candidates from Texas SOS, then asks the FEC what a lookup would, with your keys (`PALLOT_FEC_API_KEY` to `5`, required) at the gentle pace `pallot-cache` uses: about 470 requests, 5 minutes with 3 keys.
- Texas SOS's statewide data makes the 9 or so requests a lookup starts with, a few seconds.
- Texas SOS's ballot orders ask for all 254 counties' in each upcoming election, one request a second (4 to 5 minutes per election), and stop at the first refusal. A county Texas SOS answers with a server error is left out, and asked live; past 10 of them, the refresh fails.
- A source's answers are written only when every request succeeded and something changed. Otherwise it only notes when they were checked, in `meta.json`. A source that fails is reported, and the others still go.
- On a server, `pallot-cache hard-refresh --only fec` asks the FEC again for every answer in the cache, the bundled ones included.

## Configuration

Set these as environment variables, for example `PALLOT_DATA_DIR=/var/lib/pallot uv run pallot`, or in a `.env` file in the project folder: `cp .env.example .env` and fill it in. Pallot reads `.env` at startup, and git ignores it. Variables already set in the environment win over `.env`. Docker Compose reads the same `.env` and passes it to the container, where `PALLOT_DATA_DIR` is always `/data`: the folder it names on the host is mounted there.

| Variable | Default |
|---|---|
| `PALLOT_DATA_DIR` | `data/` in the project (cache, SBOE and precinct maps, TrackAIPAC, Vote for Peace and TEC data, and your `sources.toml` if you add one; git-ignored) |
| `PALLOT_FEC_API_KEY`, `PALLOT_FEC_API_KEY2` to `PALLOT_FEC_API_KEY5` | `DEMO_KEY`, which only allows race totals and runs out after a few requests. Get a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/). The extra keys are optional: Pallot uses all of them in turn, and skips one the FEC has rate limited or refused. They are only sent to the FEC, in a header, and Pallot never writes them anywhere (a resting key is noted by a short hash of it) |
| `PALLOT_GOOGLE_API_KEY` | none, so Google is never asked. A [Google Geocoding API key](https://developers.google.com/maps/documentation/geocoding/get-api-key), to find addresses the Census and OpenStreetMap can't. It's only sent to Google, in a header, and Pallot never writes it anywhere. Google bills by the request, though Pallot asks only for an address both others missed, and keeps the answer for 30 days |
| `PALLOT_USER_AGENT` | `Pallot/0.1 (personal ballot helper; +https://github.com/Just-Peace/Pallot)`. Nominatim and OpenStreetMap's tile server require one that names the app and how to reach whoever runs it; add your email if you like |
| `PALLOT_HTTP_TIMEOUT` | `30` seconds |
| `PALLOT_ALLOWED_HOSTS` | none: Pallot answers to `localhost` and IP addresses only. List any other names you open it by, comma-separated (for example `nas.local`, or a reverse proxy's domain), or `*` for any. Other names get an error, which protects Settings from DNS rebinding |
| `PALLOT_TTL_*` | cache lifetimes, see [Caching](#caching); for example `PALLOT_TTL_GEOCODE_BACKOFF` and `PALLOT_TTL_SOS_BACKOFF` for how long the address lookup and Texas SOS are left alone after refusing a request, `PALLOT_TTL_KEY_DATES` for the key election dates, `PALLOT_TTL_KEY_DATES_BACKOFF` for how long that page is left alone after refusing a request, `PALLOT_TTL_OUTLINES` for the district map's outlines, `PALLOT_TTL_ELECTION_PRECINCTS` for the list of precinct maps (and `PALLOT_TTL_ELECTION_PRECINCTS_BACKOFF` for how long the portal is left alone after refusing a request, for both the precinct and SBOE maps), `PALLOT_TTL_COUNTY_PRECINCTS` for the counties' lists and maps of their precincts (and `PALLOT_TTL_COUNTY_PRECINCTS_BACKOFF` for how long the counties are left alone after one refuses a request), `PALLOT_TTL_ENDORSEMENT_FEEDS` for the endorsement lists fetched from organizations' websites (and `PALLOT_TTL_ENDORSEMENT_FEEDS_BACKOFF` for how long an organization's website is left alone after refusing a request), `PALLOT_TTL_OFFICEHOLDERS` for the lists of who holds each seat (and `PALLOT_TTL_OFFICEHOLDERS_BACKOFF` for how long they're left alone after one is refused), `PALLOT_TTL_TILES` for the street map's tiles (at least 7 days, as OpenStreetMap asks: a shorter one is raised to 7 days), `PALLOT_TTL_FEC_BUNDLE` for how long the FEC's answers that came with Pallot are used, from when they were last checked (see [Bundled snapshots](#bundled-snapshots)), and `PALLOT_TTL_SOS_ELECTIONS_BUNDLE`, `PALLOT_TTL_SOS_REFERENCE_BUNDLE`, `PALLOT_TTL_SOS_CANDIDATES_BUNDLE` and `PALLOT_TTL_SOS_BALLOT_ORDER_BUNDLE` for Texas SOS's, and `PALLOT_TTL_PRUNE_AFTER` for how long expired address suggestions, tiles and addresses not found are kept |
| `PALLOT_TILES_MAX_MB` | `512`: the most the street map's tiles take in the cache; past it, the oldest are deleted when Pallot prunes |
| `PALLOT_SUGGEST_MAX_MB` | `64`: the same for the address suggestions |
| `PALLOT_PRUNE_EVERY` | `21600` seconds (6 hours): how often a running Pallot prunes the street map's tiles and the address suggestions |
| `PALLOT_PORT` | `8000`: the port `uv run pallot` listens on (`--port` wins), and in Docker the port published on the host |

### Docker

- `compose.yaml` mounts `data/` (or the folder `PALLOT_DATA_DIR` names) at `/data`, so Docker and `uv run pallot` share the cache, `sources.toml`, TrackAIPAC, Vote for Peace and TEC data, and nothing is fetched twice. Don't run both at once, because they'd share one SQLite file.
- It's published on every network interface. To keep it to this machine, change the `ports` line in `compose.yaml` to `"127.0.0.1:8000:8000"`. `PALLOT_PORT` in `.env` changes the port.
- To open it by a name rather than an address (`http://nas.local:8000`, or through a reverse proxy), add the name to `PALLOT_ALLOWED_HOSTS` in `.env`. A reverse proxy must pass the original `Host` header on.
- The container runs as user and group 1000, which must be able to write `data/`. That's why the quick start creates it: otherwise Docker creates it owned by root. If your ids differ (`id -u`, `id -g`), set `PALLOT_UID` and `PALLOT_GID` in `.env`.
- `.env` is passed in when the container starts, never built into the image.

## Not built yet

Known bugs, planned improvements and features, and UI ideas are [GitHub issues](https://github.com/Just-Peace/Pallot/issues).

## Working on Pallot

How it's put together, the tests, and adding a source: [DEVELOPMENT.md](DEVELOPMENT.md).
