"""Illinois: the State Board of Elections' candidate data file for a general election, the
tab-separated file its Download Candidate Data Files page hands out. Each election has its own
page under an opaque ID, so the ID is found on the Board's list of elections by the election's
name and date, never worked out ahead. The page is an ASP.NET form: the file is the answer to a
postback of its Tab-Delimited Text File link, sent with the page's own hidden fields
(HttpCache.form_from_page).

Each row is a candidate with a status: only the Active are on the ballot. The established
parties' nominees are in it as well as the independents. A Governor and Lieutenant Governor
ticket is two rows under one bracket, the Governor's ID: they're one candidate, "JB Pritzker and
Christian Mitchell". The file carries candidates' addresses, websites and emails: only the name,
party and race are read, so the cache and the bundle hold the parsed filings and the list of
elections alone. Apostrophes come escaped as SQL ("O' + Char(39) + 'Brien").

The statewide offices come under the state, Congress, the State Senate and the State House by
their districts, and a Cook County circuit judge or a First District appellate judge (the First
District is Cook County) the whole county. Subcircuits, other circuits and appellate districts,
and the regional superintendents of schools can't be placed from the address; retention
questions are left out.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import re
from pathlib import Path
from typing import Any

from ..http_cache import RequestSpec, Unreadable
from ..sources.fec import race_name
from . import Filing, StateList, filings_json, ordinal, party

BASE = "https://www.elections.il.gov/ElectionOperations/"
INDEX = BASE + "CandidateOfficeFilingSearch.aspx"
DOWNLOAD = BASE + "DownloadCandidates.aspx?ID={id}"
FORM = {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnText", "__EVENTARGUMENT": ""}
COLUMNS = ("CandidateID", "BracketID", "LastName", "FirstName", "CandidateStatus", "ElecDate", "ElectionType",
           "PartyName", "PartySequence", "OfficeName", "BallotGroup", "OfficeSequence", "Sequence")
HOUSE_RACES = 17  # a list with fewer Congress races isn't the whole list
STATEWIDE = {"GOVERNOR AND LIEUTENANT GOVERNOR": "Governor and Lieutenant Governor", "ATTORNEY GENERAL": "Attorney General",
             "SECRETARY OF STATE": "Secretary of State", "COMPTROLLER": "Comptroller", "TREASURER": "Treasurer"}
TICKET = "GOVERNOR AND LIEUTENANT GOVERNOR"
_BALLOT = ("A", "B", "F", "J", "LB", "LC", "LD", "K")  # the file's ballot groups in the ballot's order
_ELECTION = re.compile(
    r"""href=["']([^"']*CandidateFilingSearch\.aspx\?ID=([^"'&]+))["'][^>]*>\s*GENERAL ELECTION\s*</a>\s*</td>\s*"""
    r"""<td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})\s*<""", re.I)
_LEGISLATURE = re.compile(r"^(\d+)(?:ST|ND|RD|TH) (CONGRESS|SENATE|REPRESENTATIVE)$")
_APPELLATE = re.compile(r"^(\d+)(?:ST|ND|RD|TH) APPELLATE - (.+) VACANCY$", re.I)
_COOK = re.compile(r"^COOK CIRCUIT - (.+) VACANCY$", re.I)
_NAMES = {"INDEPENDENT": "Independent"}
_MIXED = re.compile(r"^([A-Z][a-z]+)([A-Z][A-Z'.,]+)$")


def elections(text: str) -> dict[str, Any]:
    """The list of elections as kept: each general election's ISO date and its page's ID;
    ValueError for a page that isn't it."""
    if "gvElections" not in text:
        raise ValueError("not the State Board's list of elections")
    found = {}
    for _, key, day in _ELECTION.findall(text):
        found[dt.datetime.strptime(day, "%m/%d/%Y").date().isoformat()] = html.unescape(key)
    return {"elections": found}


def _text(value: str | None) -> str:
    return " ".join((value or "").replace("' + Char(39) + '", "'").split())


def _capitalized(text: str) -> str:
    """A name in capitals as written ("O'MALLEY" is "O'Malley", "5TH" is "5th", "McDADE" is "McDade")."""
    def word(text: str) -> str:
        if text.isupper():
            return text.lower() if text[0].isdigit() else text.title()
        mixed = _MIXED.match(text)
        return mixed.group(1) + mixed.group(2).title() if mixed else text

    return " ".join(word(part) for part in text.split())


def _kind(shown: str) -> dict[str, Any] | None:
    """The race of an office, as Filing's fields: its id, shown name, family, group, reach, district
    and counties; None for a retention question."""
    office = shown.upper()
    race = {"office_id": office, "office": _capitalized(shown), "family": office, "district": None, "counties": ()}
    if "RETAIN" in office.split():
        return None
    if office == "UNITED STATES SENATOR":
        return {**race, "office": race_name("IL", None), "family": "US SENATE", "group": "federal", "reach": "state"}
    if office in STATEWIDE:
        return {**race, "office": STATEWIDE[office], "group": "state", "reach": "state"}
    if found := _LEGISLATURE.match(office):
        number, kind = int(found.group(1)), found.group(2)
        if kind == "CONGRESS":
            return {**race, "office": race_name("IL", number), "family": "US HOUSE", "group": "federal", "reach": "cd",
                    "district": str(number)}
        senate = kind == "SENATE"
        return {**race, "office": f"State {'Senator' if senate else 'Representative'} District {number}",
                "family": "STATE SENATE" if senate else "STATE HOUSE", "group": "legislature",
                "reach": "sd" if senate else "hd", "district": str(number)}
    if found := _APPELLATE.match(shown):
        number = int(found.group(1))
        return {**race, "office": f"Judge of the Appellate Court, {ordinal(number)} District "
                                  f"({_capitalized(found.group(2))} vacancy)",
                "family": "APPELLATE JUDGE", "group": "judicial", "district": str(number),
                **({"reach": "county", "counties": ("COOK",)} if number == 1 else {"reach": "unplaced"})}
    if (found := _COOK.match(shown)) and "SUBCIRCUIT" not in office:
        return {**race, "office": f"Judge of the Circuit Court of Cook County ({_capitalized(found.group(1))} vacancy)",
                "family": "COOK CIRCUIT JUDGE", "group": "judicial", "reach": "county", "counties": ("COOK",)}
    group = "judicial" if "CIRCUIT" in office else "state"
    return {**race, "group": group, "reach": "unplaced"}


def _number(text: str | None) -> int:
    return int(text) if (text or "").strip().isdigit() else 0


def parse(raw: str) -> list[Filing]:
    """Every active candidate in the file, a ticket as one; ValueError for a file that isn't it
    (renamed columns, an error page) or one short of Congress's races."""
    reader = csv.DictReader(io.StringIO(raw.lstrip("﻿")), delimiter="\t", quoting=csv.QUOTE_NONE)
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column")
    rows = [row for row in reader if _text(row["CandidateStatus"]) == "Active" and _text(row["ElectionType"]) == "GE"]
    mates: dict[str, list[str]] = {}
    for row in rows:
        if _text(row["OfficeName"]) == TICKET and row["BracketID"] not in ("", "0", row["CandidateID"]):
            mates.setdefault(row["BracketID"], []).append(_text(f"{row['FirstName']} {row['LastName']}"))
    filings = []
    for row in rows:
        race = _kind(_text(row["OfficeName"]))
        if race is None or race["office_id"] == TICKET and row["BracketID"] not in ("", "0", row["CandidateID"]):
            continue
        try:
            day = dt.datetime.strptime(_text(row["ElecDate"]), "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        name = " and ".join([_text(f"{row['FirstName']} {row['LastName']}"), *mates.get(row["CandidateID"], [])])
        group = _text(row["BallotGroup"])
        code, party_name = party(_capitalized(_text(row["PartyName"])), _NAMES)
        rank = _BALLOT.index(group) if group in _BALLOT else len(_BALLOT)
        filings.append(Filing(
            day=day, name=name, party=code, party_name=party_name,
            order=((rank * 100_000 + _number(row["OfficeSequence"])) * 1000 + _number(row["PartySequence"])) * 100
            + _number(row["Sequence"]), **race,
        ))
    races = {f.district for f in filings if f.reach == "cd"}
    if len(races) < HOUSE_RACES:
        raise ValueError(f"{len(races)} U.S. House races, not {HOUSE_RACES}")
    return filings


def _decoded(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


class IlList(StateList):
    state = "IL"
    source = "state_il"
    label = "Illinois State Board of Elections"
    page = INDEX
    description = ("Illinois's candidates for state and federal offices, Cook County's judges among them, from its State "
                   "Board of Elections' candidate filings.")
    max_bytes = 16 << 20

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cache.form_from_page(self.source, hidden_fields)

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", INDEX)

    @staticmethod
    def download(key: str) -> RequestSpec:
        return RequestSpec("POST", DOWNLOAD.format(id=key), form=FORM)

    @classmethod
    def read_file(cls, path: Path) -> dict[str, Any]:
        text = _decoded(path.read_bytes())
        if text.lstrip("﻿").startswith("CandidateID\t"):
            return filings_json(cls.parse(text))
        return elections(text)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a candidate data file")
        return parse(raw)

    def check(self, value: Any) -> str | None:
        if isinstance(value, dict) and "elections" in value:
            return None if isinstance(value["elections"], dict) else "its list of elections isn't one"
        return super().check(value)

    async def filings(self, day: dt.date) -> list[Filing] | None:
        index = await self.cache.get_json(self.source, self.spec(day), ttl=self.ttl.state_list)
        key = index.value["elections"].get(day.isoformat())
        if key is None:
            return None
        got = await self.cache.get_json(self.source, self.download(key), ttl=self.ttl.state_list)
        return [f for f in self.read(got.value) if f.day == day.isoformat()] or None


_HIDDEN = re.compile(r"""<input[^>]*type=["']hidden["'][^>]*>""", re.I)
_ATTR = re.compile(r"""(name|value)=["']([^"']*)["']""", re.I)


def hidden_fields(text: str) -> dict[str, str]:
    """An ASP.NET page's hidden fields (``__VIEWSTATE``, ``__EVENTVALIDATION``), for its postback."""
    fields = {}
    for tag in _HIDDEN.findall(text):
        attrs = {name.lower(): html.unescape(value) for name, value in _ATTR.findall(tag)}
        if "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    if "__VIEWSTATE" not in fields:
        raise Unreadable("the download page has no form to post")
    return fields
