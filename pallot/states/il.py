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
their districts, a Cook County circuit judge or a First District appellate judge (the First
District is Cook County) the whole county, and another circuit's or appellate district's judge
its counties. A subcircuit's vacancy and the regional superintendents of schools can't be placed
from the address. The judges standing for retention (ballot groups RB and RC) are each a yes-or-no
question, in their whole circuit, a subcircuit's judge's too. A downstate appellate judge's isn't
placed: since the districts were redrawn in 2021, a judge elected before then stands for
retention in the old district or the new one, as they chose (705 ILCS 23/5), and the file doesn't say which.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import html
import io
import re
from typing import Any

from ..http_cache import RequestSpec
from . import (
    Filing, Office, StateList, counties_of, decoded, legislator, ordinal, party, require, statewide, us_house,
    us_senate,
)

BASE = "https://www.elections.il.gov/ElectionOperations/"
INDEX = BASE + "CandidateOfficeFilingSearch.aspx"
DOWNLOAD = BASE + "DownloadCandidates.aspx?ID={id}"
FORM = {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnText", "__EVENTARGUMENT": ""}
COLUMNS = ("CandidateID", "BracketID", "LastName", "FirstName", "CandidateStatus", "ElecDate", "ElectionType",
           "PartyName", "PartySequence", "OfficeName", "BallotGroup", "OfficeSequence", "Sequence")
MINIMUM = {"cd": 17}  # a list with fewer Congress races isn't the whole list
STATEWIDE = {"GOVERNOR AND LIEUTENANT GOVERNOR": "Governor and Lieutenant Governor", "ATTORNEY GENERAL": "Attorney General",
             "SECRETARY OF STATE": "Secretary of State", "COMPTROLLER": "Comptroller", "TREASURER": "Treasurer"}
TICKET = "GOVERNOR AND LIEUTENANT GOVERNOR"
_BALLOT = ("A", "B", "F", "J", "LB", "LC", "LD", "K", "RB", "RC")  # the file's ballot groups in the ballot's order
_ELECTION = re.compile(
    r"""href=["']([^"']*CandidateFilingSearch\.aspx\?ID=([^"'&]+))["'][^>]*>\s*GENERAL ELECTION\s*</a>\s*</td>\s*"""
    r"""<td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})\s*<""", re.I)
_LEGISLATURE = re.compile(r"^(\d+)(?:ST|ND|RD|TH) (CONGRESS|SENATE|REPRESENTATIVE)$")
_APPELLATE = re.compile(r"^(\d+)(?:ST|ND|RD|TH) APPELLATE - (.+) VACANCY$", re.I)
_CIRCUIT = re.compile(r"^(COOK|\d+)(?:ST|ND|RD|TH)? CIRCUIT - (.+) VACANCY$", re.I)
_RETAIN = re.compile(r"^(COOK|\d+)(?:ST|ND|RD|TH)? (CIRCUIT|APPELLATE) - (?:.+ - )?RETAIN .+$", re.I)
_NAMES = {"INDEPENDENT": "Independent"}
_MIXED = re.compile(r"^([A-Z][a-z]+)([A-Z][A-Z'.,]+)$")
_CIRCUITS = {  # 705 ILCS 35/1, with the 24th split from the 20th since December 5, 2022
    1: ("ALEXANDER", "JACKSON", "JOHNSON", "MASSAC", "POPE", "PULASKI", "SALINE", "UNION", "WILLIAMSON"),
    2: ("CRAWFORD", "EDWARDS", "FRANKLIN", "GALLATIN", "HAMILTON", "HARDIN", "JEFFERSON", "LAWRENCE", "RICHLAND",
        "WABASH", "WAYNE", "WHITE"),
    3: ("BOND", "MADISON"),
    4: ("CHRISTIAN", "CLAY", "CLINTON", "EFFINGHAM", "FAYETTE", "JASPER", "MARION", "MONTGOMERY", "SHELBY"),
    5: ("CLARK", "COLES", "CUMBERLAND", "EDGAR", "VERMILION"),
    6: ("CHAMPAIGN", "DE WITT", "DOUGLAS", "MACON", "MOULTRIE", "PIATT"),
    7: ("GREENE", "JERSEY", "MACOUPIN", "MORGAN", "SANGAMON", "SCOTT"),
    8: ("ADAMS", "BROWN", "CALHOUN", "CASS", "MASON", "MENARD", "PIKE", "SCHUYLER"),
    9: ("FULTON", "HANCOCK", "HENDERSON", "KNOX", "MCDONOUGH", "WARREN"),
    10: ("MARSHALL", "PEORIA", "PUTNAM", "STARK", "TAZEWELL"),
    11: ("FORD", "LIVINGSTON", "LOGAN", "MCLEAN", "WOODFORD"),
    12: ("WILL",),
    13: ("BUREAU", "GRUNDY", "LASALLE"),
    14: ("HENRY", "MERCER", "ROCK ISLAND", "WHITESIDE"),
    15: ("CARROLL", "JO DAVIESS", "LEE", "OGLE", "STEPHENSON"),
    16: ("KANE",),
    17: ("BOONE", "WINNEBAGO"),
    18: ("DUPAGE",),
    19: ("LAKE",),
    20: ("ST. CLAIR",),
    21: ("IROQUOIS", "KANKAKEE"),
    22: ("MCHENRY",),
    23: ("DEKALB", "KENDALL"),
    24: ("MONROE", "PERRY", "RANDOLPH", "WASHINGTON"),
}
_APPEALS = {  # the Judicial Districts Act of 2021 (705 ILCS 23/15 to 23/30), by their circuits
    2: (16, 19, 22, 23),
    3: (12, 13, 18, 21),
    4: (7, 8, 9, 10, 11, 14, 15, 17),
    5: (1, 2, 3, 4, 5, 6, 20, 24),
}


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
    """A name in capitals as written ("O'MALLEY" is "O'Malley", "5TH" is "5th", "McDADE" is "McDade",
    "III" stays)."""
    def word(text: str) -> str:
        if text.rstrip(",.") in ("II", "III", "IV"):
            return text
        if text.isupper():
            return text.lower() if text[0].isdigit() else text.title()
        mixed = _MIXED.match(text)
        return mixed.group(1) + mixed.group(2).title() if mixed else text

    return " ".join(word(part) for part in text.split())


def _court(place: str, court: str) -> tuple[str, dict[str, Any]] | None:
    """A court's name and its judges' Filing fields (family, reach, district, counties), from the
    office's "COOK" or number and "CIRCUIT" or "APPELLATE"; None for a number it doesn't know."""
    if place == "COOK" or court == "APPELLATE" and place == "1":
        circuit = court == "CIRCUIT"
        return ("the Circuit Court of Cook County" if circuit else "the Appellate Court, 1st District",
                {"family": "COOK CIRCUIT JUDGE" if circuit else "APPELLATE JUDGE", "reach": "county",
                 "district": None if circuit else "1", "counties": ("COOK",)})
    number = int(place)
    circuits = (number,) if court == "CIRCUIT" else _APPEALS.get(number, ())
    if not circuits or not all(circuit in _CIRCUITS for circuit in circuits):
        return None
    name = f"the Circuit Court, {ordinal(number)} Circuit" if court == "CIRCUIT" else \
        f"the Appellate Court, {ordinal(number)} District"
    return name, {"family": f"{court} JUDGE", "reach": "counties", "district": str(number),
                  "counties": counties_of(_CIRCUITS, circuits)}


def _kind(shown: str, name: str) -> Office:
    """The race of an office, and for a retention question, ``name``'s, the judge's."""
    office = shown.upper()
    if found := _RETAIN.match(office):
        court = _court(found.group(1), found.group(2))
        retain = Office(office, f"Retain {name}" + (f", Judge of {court[0]}" if court else ""), office, "judicial",
                        "unplaced", incumbent=True, retention=True)
        placed = court and (found.group(2) == "CIRCUIT" or court[1]["reach"] == "county")
        return dataclasses.replace(retain, **court[1]) if placed else retain
    if office == "UNITED STATES SENATOR":
        return us_senate("IL", office)
    if office in STATEWIDE:
        return statewide(STATEWIDE[office], office)
    if found := _LEGISLATURE.match(office):
        number, kind = int(found.group(1)), found.group(2)
        if kind == "CONGRESS":
            return us_house("IL", number, office)
        return legislator("sd" if kind == "SENATE" else "hd", number, office)
    for pattern, kind in ((_APPELLATE, "APPELLATE"), (_CIRCUIT, "CIRCUIT")):
        found = pattern.match(shown)
        court = found and " - " not in found.group(2) and _court(found.group(1).upper(), kind)
        if court:
            return Office(office, f"Judge of {court[0]} ({_capitalized(found.group(2))} vacancy)", group="judicial",
                          **court[1])
    group = "judicial" if "CIRCUIT" in office or "APPELLATE" in office else "state"
    return Office(office, _capitalized(shown), office, group, "unplaced")


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
        office = _text(row["OfficeName"])
        if office == TICKET and row["BracketID"] not in ("", "0", row["CandidateID"]):
            continue
        try:
            day = dt.datetime.strptime(_text(row["ElecDate"]), "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        name = " and ".join([_text(f"{row['FirstName']} {row['LastName']}"), *mates.get(row["CandidateID"], [])])
        race = _kind(office, name)
        group = _text(row["BallotGroup"])
        code, party_name = party(_capitalized(_text(row["PartyName"])), _NAMES)
        rank = _BALLOT.index(group) if group in _BALLOT else len(_BALLOT)
        filings.append(race.filing(
            day=day, name=name, party=code, party_name=party_name,
            order=((rank * 100_000 + _number(row["OfficeSequence"])) * 1000 + _number(row["PartySequence"])) * 100
            + _number(row["Sequence"]),
        ))
    return require(filings, MINIMUM)


class IlList(StateList):
    state = "IL"
    source = "state_il"
    label = "Illinois State Board of Elections"
    page = INDEX
    description = ("Illinois's candidates for state and federal offices and its judges, and the judges standing for "
                   "retention, from its State Board of Elections' candidate filings.")
    max_bytes = 16 << 20
    postback = True
    index_key = "elections"

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", INDEX)

    @staticmethod
    def download(key: str) -> RequestSpec:
        return RequestSpec("POST", DOWNLOAD.format(id=key), form=FORM)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        text = decoded(raw)
        return None if text.startswith("CandidateID\t") else elections(text)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        key = index["elections"].get(day.isoformat())
        return None if key is None else [self.download(key)]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if isinstance(raw, bytes):
            raw = decoded(raw)
        if not isinstance(raw, str):
            raise ValueError("not a candidate data file")
        return parse(raw)
