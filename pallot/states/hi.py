"""Hawaii: the Office of Elections' Candidate Report (olvr.hawaii.gov), its CandidateFiling.aspx grid
(grid.py). The grid's page without an election sends you away, and its dropdown names each report
by its year alone ("2026 Candidate Report" under 94), so its id comes from the Office of Elections'
Candidate Reports page, which links the current report under the year it names ("Candidate Filing
for the 2026 Elections", ``elid=94``). The list is the grid's Export to CSV, posted back for that
election. A plain script gets a 200 (behind Cloudflare, with no challenge).

A row per candidate, the primary's and the general's together: the contest ("U.S. REPRESENTATIVE,
DIST I", "STATE SENATOR, DIST 18 VACANCY"), the party (NONPARTISAN is none; NONPARTISAN SPECIAL
the nonpartisan races'), the name as the ballot prints it, last name first in capitals ("CASE,
Ed", "DUPIO, Gaius, II (Kipi)"), the legal name, the candidate's address, phone, email and website,
the dates the papers were issued and filed, and the status. Only "In General" is on the November
ballot: a candidate unopposed after the primary is "Elected After Primary" and isn't printed. Only
the name, office, district and party are kept: the list is kept as its filings, so the cache and
the bundle hold nothing else.

Its races in 2026, from the Office of Elections' contest schedule: the U.S. House (two districts,
in Roman numerals), Governor and Lieutenant Governor, 15 of the State Senate's 25 districts (18 and
19 for a 2-year term, the rest of a vacancy's), all 51 of the State House, and the Office of
Hawaiian Affairs' trustees, three at large and one each resident of Maui and of Oahu, every one
elected by the whole state. The list has Governor and Lieutenant Governor as two contests, but
they're nominated apart and elected as one ticket, a vote for a party's Governor counting for its
Lieutenant Governor (Haw. Const. art. V, §2), so they're paired by party as the ballot prints them.
The county races (mayors, councils, prosecutors) are left out with a ballot note.

Hawaii's key dates, for its general election (the first Tuesday after the first Monday of
November in an even year, HRS §11-91 and 2 U.S.C. §7), checked on 2026-10-29 against the Office of
Elections' 2026 Election Dates & Deadlines (elections.hawaii.gov; the Legislature's statute site,
capitol.hawaii.gov, refuses scripts): every election is by mail (HRS ch. 11, part VIIA, §11-101),
each voter mailed a ballot to arrive at least 18 days before (§11-102); a paper registration must
reach the county elections division 8 days before, while online registration and late
registration in person at a voter service center go on through Election Day (§11-15.2); voter
service centers are open from the tenth business day before through Election Day, but not on
Sundays (§11-109); and a ballot must reach the county by 7 p.m. on Election Day, when voting
closes (§11-104). 2026: Oct 16, Oct 26 and Oct 20 – Nov 3, as on the Office of Elections' calendar.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from typing import Any

from ..http_cache import RequestSpec
from ..matching import last_first
from . import Filing, Office, decoded, legislator, party, statewide, us_house, us_senate
from .dates import Counts, Guide, mailed_to_every_voter
from .grid import GridList, GridRow, titled

INDEX = "https://elections.hawaii.gov/candidates/candidate-reports/"
PAGE = "https://olvr.hawaii.gov/Controls/CandidateFiling.aspx"
EXPORT = {"ctl00$cphFooter$rdgSearch$ctl00$ctl02$ctl00$ExportToCsvButton": " "}
DROPDOWN = "ctl00$cphFooter$ddlElection"
TICKET = "Governor and Lieutenant Governor"
OHA = {"OHA AT-LARGE TRUSTEE": "At-Large", "OHA MAUI RESIDENT TRUSTEE": "Maui Resident",
       "OHA OAHU RESIDENT TRUSTEE": "Oahu Resident", "OHA HAWAII RESIDENT TRUSTEE": "Hawaii Island Resident",
       "OHA KAUAI RESIDENT TRUSTEE": "Kauai Resident", "OHA MOLOKAI RESIDENT TRUSTEE": "Molokai/Lanai Resident"}
COUNTIES = ("HAWAII ", "HONOLULU ", "KAUAI ", "MAUI ")  # a county race's contest begins with its county
ROMAN = {"I": 1, "II": 2}
_LINK = re.compile(r"""CandidateFiling\.aspx\?elid=(\d+)""", re.I)
_YEAR = re.compile(r"\b(\d{4}) Elections?\b", re.I)
_DISTRICT = re.compile(r"(U\.S\. REPRESENTATIVE|STATE SENATOR|STATE REPRESENTATIVE), DIST (\w+)( VACANCY)?")


class HiList(GridList):
    state = "HI"
    source = "state_hi"
    label = "Hawaii Office of Elections"
    page = PAGE
    index = INDEX
    election = "elid"
    form = EXPORT
    kept = ("IN GENERAL",)
    minimum = {"cd": 2, "sd": 4, "hd": 30}  # only the contested races: an unopposed candidate is elected after the primary
    description = ("Hawaii's official list of the candidates for Congress, Governor and Lieutenant Governor, the "
                   "Legislature and the Office of Hawaiian Affairs, from its Office of Elections.")
    scope_note = ("Your county's races (mayor, council, prosecuting attorney) and the proposed constitutional amendments "
                  "aren't shown: the ballot mailed to you has them. A seat whose candidate was unopposed after the "
                  "primary is already filled, so it isn't on the ballot.")

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The Candidate Reports page's link to the report, by the year of the elections the page
        names before it ("Candidate Filing for the 2026 Elections"); None for the CSV; ValueError
        for a page without a link to it."""
        text = decoded(raw)
        if not text.lstrip().startswith("<"):
            return None
        found: dict[str, str] = {}
        links = list(_LINK.finditer(text))
        if not links:
            raise ValueError("no link to a candidate report")
        for link in links:
            years = _YEAR.findall(html.unescape(re.sub(r"<[^>]+>", " ", text[:link.start()])))
            if years:
                found.setdefault(years[-1], link.group(1))
        return {"elections": found}

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        """GridList's postback, the report chosen in its dropdown too."""
        found = super().follow(index, day)
        return found and [dataclasses.replace(spec, form={**spec.form, DROPDOWN: spec.params[self.election]})
                          for spec in found]

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row; None for a county race. ValueError for an office it doesn't know."""
        contest = " ".join(row.race.split()).upper()
        if contest == "U.S. SENATOR":
            return us_senate("HI")
        if contest == "GOVERNOR":
            return statewide(TICKET, "GOVERNOR")
        if contest == "LIEUTENANT GOVERNOR":
            return statewide("Lieutenant Governor")
        if contest in OHA:
            return Office(contest, f"Office of Hawaiian Affairs Trustee, {OHA[contest]}", "OHA TRUSTEE", "state",
                          "state")
        if found := _DISTRICT.fullmatch(contest):
            kind, number, vacancy = found.groups()
            if kind == "U.S. REPRESENTATIVE":
                if number not in ROMAN:
                    raise ValueError(f"no U.S. House district {number!r}")
                return us_house("HI", ROMAN[number])
            if not number.isdigit():
                raise ValueError(f"no district for {row.race}")
            race = legislator("sd" if kind == "STATE SENATOR" else "hd", int(number))
            return dataclasses.replace(race, unexpired=True) if vacancy else race
        if contest.startswith(COUNTIES):
            return None
        raise ValueError(f"an office it doesn't know: {row.race}")

    @classmethod
    def affiliation(cls, row: GridRow) -> tuple[str | None, str | None]:
        """The party; none for a nonpartisan candidate or race."""
        return (None, None) if row.party.upper().startswith("NONPARTISAN") else party(row.party)

    @classmethod
    def named(cls, name: str) -> str:
        """The name first name first: "CASE, Ed" is "Ed Case", "DUPIO, Gaius, II (Kipi)" "Gaius Dupio II"."""
        last, _, rest = name.partition(",")
        return last_first(f"{titled(last.strip())}, {rest.replace(',', ' ')}") if rest else titled(name)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        """GridList's, with each party's Governor and Lieutenant Governor one ticket (a Lieutenant
        Governor without a Governor of their party kept alone), and the trustees at large as many
        seats as half their candidates, the primary having sent on two for each."""
        filings = super().parse(raw)
        mates = {(f.party, f.party_name): f for f in filings if f.office_id == "LIEUTENANT GOVERNOR" and (f.party or f.party_name)}
        paired = {key for f in filings if f.office_id == "GOVERNOR" and (key := (f.party, f.party_name)) in mates}
        at_large = sum(f.office_id == "OHA AT-LARGE TRUSTEE" for f in filings)
        kept = []
        for f in filings:
            if f.office_id == "GOVERNOR" and (f.party, f.party_name) in paired:
                f = dataclasses.replace(f, name=f"{f.name} and {mates[f.party, f.party_name].name}")
            elif f.office_id == "LIEUTENANT GOVERNOR" and (f.party, f.party_name) in paired:
                continue
            elif f.office_id == "OHA AT-LARGE TRUSTEE":
                f = dataclasses.replace(f, seats=(at_large + 1) // 2)
            kept.append(f)
        return kept


VSC = "https://elections.hawaii.gov/voter-service-centers-and-places-of-deposit/"
GUIDE = Guide(
    name="Hawaii",
    source="Hawaii Office of Elections",
    url="https://elections.hawaii.gov/",
    computed=True,
    registration_url="https://olvr.hawaii.gov/",
    mail_url="https://hawaii.ballottrax.net/voter/",
    register="The last day for a paper registration to reach your county elections division for {election} in "
             "Hawaii. You can still register online, or in person at a voter service center, and vote there, through "
             "Election Day.",
    mail_summary="Ballots arrive by mail",
    mail="Every voter in Hawaii is mailed a ballot for {election}. It must reach your county elections division by "
         "7 p.m. on Election Day, by mail or at a drop box or voter service center; a postmark doesn't count. Track "
         "yours:",
    early_where="Your county's voter service centers, every day but Sunday through Election Day: you can register, "
                "vote in person or drop off your ballot there. Your county elections division lists them.",
    credit="Dates worked out from Hawaii's election law; more from the Hawaii Office of Elections",
    poll_hours="7 p.m.",
    check_url="https://elections.hawaii.gov/register-to-vote/register-online-to-vote/",
    check_hint="Hawaii Office of Elections: check your registration and your mailing address online",
    where_url=VSC,
    where_hint="Hawaii Office of Elections: every voter service center and ballot drop box",
    mail_label="Track your ballot",
    mail_eligibility=mailed_to_every_voter("It arrives at least 18 days before Election Day. It must reach your county "
                                           "elections division by 7 p.m. on Election Day, by mail, in a drop box or at "
                                           "a voter service center; a postmark doesn't count."),
    local_office="Your county elections division",
    polls_text="Voter service centers and drop boxes close at 7 p.m. on Election Day; if you're in line at 7, you can "
               "vote.",
    late_registration="After that, register online, or in person at a voter service center, through Election Day",
    hours_set_by="your county elections division",
)
RULE = Counts(8, None, 14, None).rule("HI")  # every voter is mailed a ballot
