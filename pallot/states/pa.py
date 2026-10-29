"""Pennsylvania: the Department of State's Election Info page, which carries every candidate
for the coming November election as JSON in a hidden field (``dataJson``), its election picked
in a drop-down ("2026 General Election (11/03/2026)").

It has everyone who filed for the year, primary losers and party committee seats included: a
candidate is on the general ballot when approved and either won the primary (PrimaryResult) or
was nominated by papers or as a substitute. Names are "LAST, FIRST M", parties written out, and
a cross-filed candidate comes once per party. It has no incumbents.

Pennsylvania's key dates, for its general election (25 P.S. 2753: the Tuesday after the first Monday
of November in an even year; the odd years' is the municipal election): registration closes the
fifteenth day before (25 Pa.C.S. 1326(b)); any voter can vote by mail, the application reaching the
county board by 5 p.m. on the Tuesday before (25 P.S. 3150.12a), and the ballot must reach the board
by 8 p.m. on Election Day (3150.16); there's no early voting, but a voter can apply for a mail
ballot at the county election office and vote it there; polls are open 7 a.m. to 8 p.m. (3045).
There's no registration on Election Day.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from ..text import display_office, display_person
from . import Filing, Office, StateList, party, party_rank
from .dates import Counts, Guide

URL = "https://www.pavoterservices.pa.gov/ElectionInfo/ElectionInfo.aspx"
COLUMNS = ("CandidateName", "PartyName", "CandidateStatusValue", "CandidateTypeValue", "OfficeName", "DistrictName",
           "PrimaryResult")
_DATA = re.compile(r"""<input[^>]*id=['"]dataJson['"][^>]*value='([^']*)'""")
_ELECTION = re.compile(r'<option selected="selected" value="\d+">[^<(]*\((\d{2}/\d{2}/\d{4})\)')
_NUMBERED = re.compile(r"(\d+)\w\w (?:Congressional|Senatorial|Legislative) District")


def _kind(office: str, district: str) -> Office | None:
    """An office's race, its id the office and district, or None for one that isn't on the
    general ballot (a party's committee seat)."""
    number = found.group(1) if (found := _NUMBERED.fullmatch(district)) else None

    def race(shown: str, group: str, reach: str, seat: str | None = None, counties: tuple[str, ...] = ()) -> Office:
        return Office(f"{office} {district}", shown, office, group, reach, seat, counties)

    if office == "UNITED STATES SENATOR":
        return race(race_name("PA", None), "federal", "state")
    if office == "REPRESENTATIVE IN CONGRESS" and number:
        return race(race_name("PA", int(number)), "federal", "cd", number)
    if office == "SENATOR IN THE GENERAL ASSEMBLY" and number:
        return race(f"State Senator District {number}", "legislature", "sd", number)
    if office == "REPRESENTATIVE IN THE GENERAL ASSEMBLY" and number:
        return race(f"State Representative District {number}", "legislature", "hd", number)
    if "COMMITTEE" in office or "DELEGATE" in office:
        return None
    judicial = "JUDGE" in office or "JUSTICE" in office
    if district == "Statewide":
        return race(display_office(office), "judicial" if judicial else "state", "state")
    if county := re.fullmatch(r"(.+?) ?County", district):
        return race(f"{county.group(1)} County {display_office(office)}", "judicial" if judicial else "county", "county",
                    counties=(county.group(1).upper(),))
    return race(display_office(office), "judicial", "unplaced") if judicial else None


class PaList(StateList):
    state = "PA"
    source = "state_pa"
    label = "Pennsylvania Department of State"
    page = URL
    description = "Pennsylvania's official list of the candidates for state and federal offices, from its Department of State."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL, as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        text = raw if isinstance(raw, str) else ""
        found, election = _DATA.search(text), _ELECTION.search(text)
        if not found or not election:
            raise ValueError("no candidates or election on the page")
        rows = json.loads(html.unescape(found.group(1)))
        missing = [c for c in COLUMNS if rows and c not in rows[0]]
        if missing:
            raise ValueError(f"no {', '.join(missing)} field")
        day = dt.datetime.strptime(election.group(1), "%m/%d/%Y").date().isoformat()
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            if row["CandidateStatusValue"] != "Approved":
                continue
            if row["PrimaryResult"] != "true" and row["CandidateTypeValue"] not in ("Paper", "Substitute"):
                continue
            office, district = " ".join(row["OfficeName"].split()), " ".join(row["DistrictName"].split())
            last, _, rest = row["CandidateName"].partition(",")  # a suffix comes with the last name: "HARVIE JR, ROBERT J"
            name = display_person(" ".join(f"{rest} {last}".split()))
            kind = _kind(office, district)
            if kind is None or not name:
                continue
            key = (office, district, name)
            if key in merged:
                merged[key]["parties"].append(row["PartyName"])
                continue
            merged[key] = {"kind": kind, "parties": [row["PartyName"]]}
        position = {race: i for i, race in enumerate(sorted({key[:2] for key in merged}))}
        filings = []
        for (office, district, name), entry in merged.items():
            race = entry["kind"]
            parties = list(dict.fromkeys(p.strip() for p in entry["parties"] if p and p.strip()))
            code, party_name = party(parties[0]) if len(parties) == 1 else (None, " / ".join(parties) or None)
            rank = {"state": 0, "cd": 1, "sd": 0, "hd": 1}.get(race.reach, 2)
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name,
                order=(rank * 10_000 + position[(office, district)]) * 10
                + party_rank(code, party_name),
            ))
        return filings


GUIDE = Guide(
    name="Pennsylvania",
    source="Pennsylvania Department of State",
    url="https://www.pa.gov/agencies/vote",
    computed=True,
    registration_url="https://www.pavoterservices.pa.gov/pages/VoterRegistrationApplication.aspx",
    mail_url="https://www.pavoterservices.pa.gov/OnlineAbsenteeApplication/",
    register="The last day to register to vote in {election} in Pennsylvania. There's no registration on Election "
             "Day.",
    mail_summary="Mail ballot application due",
    mail="If you vote by mail in {election}, your application must reach your county board of elections by 5 p.m. "
         "today. You can also apply at the county election office and vote your mail ballot there. Your ballot must "
         "reach the board by 8 p.m. on Election Day; one that arrives later isn't counted, even if it was mailed in "
         "time. Any voter can vote by mail; how to apply:",
    early_where="There's no early voting at a polling place; you can apply for a mail ballot at your county election "
                "office and vote it there.",
    credit="Dates worked out from Pennsylvania's election law; more from the Pennsylvania Department of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://www.pavoterservices.pa.gov/pages/voterregistrationstatus.aspx",
    check_hint="Pennsylvania's voter registration status (Department of State)",
    where_url="https://www.pavoterservices.pa.gov/pages/pollingplaceinfo.aspx",
    where_hint="Pennsylvania's polling place search (Department of State)",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote by mail, no reason needed, or apply at the county election office "
                     "and vote the ballot there. Your ballot must reach your county board by 8 p.m. on Election Day.",
    mail_deadline="Your application must reach your county board by 5 p.m. on ",
    local_office="Your county board of elections",
)
RULE = Counts(15, 7, None, None).rule("PA")
