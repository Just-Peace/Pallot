from __future__ import annotations

import pytest

from pallot.offices import classify, clean_office_name
from pallot.text import display_office, display_person, web_url

COUNTIES = {"TRAVIS", "HARRIS"}


@pytest.mark.parametrize(
    ("name", "office_type", "kind", "number", "unexpired"),
    [
        ("U. S. SENATOR ", "FD", "us_senate", None, False),
        ("U. S. REPRESENTATIVE DISTRICT 10", "FD", "cd", 10, False),
        ("STATE SENATOR, DISTRICT 21", "SR", "sd", 21, False),
        ("STATE REPRESENTATIVE DISTRICT 93 - UNEXPIRED TERM", "SR", "hd", 93, True),
        ("MEMBER, STATE BOARD OF EDUCATION, DISTRICT 4 - UNEXPIRED TERM", "SR", "sboe", 4, True),
        ("COUNTY COMMISSIONER PRECINCT 2", "CR", "commissioner", 2, False),
        ("JUSTICE OF THE PEACE PRECINCT 1, PLACE 2", "CR", "jp", 1, False),
        ("COUNTY CONSTABLE PRECINCT 4 - UNEXPIRED TERM", "CR", "constable", 4, True),
        ("TRAVIS - COUNTY JUDGE", "CW", "countywide", None, False),
        ("DISTRICT JUDGE, 147TH JUDICIAL DISTRICT", "SR", "whole_county", None, False),
        ("CHIEF JUSTICE, 15TH COURT OF APPEALS DISTRICT", "SR", "whole_county", None, False),
        ("GOVERNOR", "SW", "statewide", None, False),
        ("HARRIS COUNTY DEPARTMENT OF EDUCATION, PLACE 5", "CW", "countywide", None, False),
    ],
)
def test_classify_real_office_names(name, office_type, kind, number, unexpired):
    scope = classify(name, office_type, COUNTIES)
    assert (scope.kind, scope.number, scope.unexpired) == (kind, number, unexpired)


def test_county_prefix_is_only_dropped_for_real_counties():
    assert clean_office_name("TRAVIS - COUNTY JUDGE", COUNTIES) == ("COUNTY JUDGE", False)
    assert clean_office_name("COUNTY ATTORNEY - UNEXPIRED TERM", COUNTIES) == ("COUNTY ATTORNEY", True)


def test_congressional_seats_and_groups():
    assert classify("U. S. SENATOR", "FD").seat == "TX-SEN"
    assert classify("U. S. REPRESENTATIVE DISTRICT 7", "FD").seat == "TX-07"
    assert classify("STATE SENATOR, DISTRICT 7", "SR").seat is None
    assert classify("DISTRICT CLERK", "CW").group == "county"
    assert classify("MEMBER, STATE BOARD OF EDUCATION, DISTRICT 5", "SR").group == "legislature"


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("U. S. REPRESENTATIVE DISTRICT 10", "U.S. Representative District 10"),
        ("JUDGE, COUNTY COURT AT LAW NO. 1", "Judge, County Court at Law No. 1"),
        ("CHIEF JUSTICE, 3RD COURT OF APPEALS DISTRICT", "Chief Justice, 3rd Court of Appeals District"),
        ("Already Mixed Case", "Already Mixed Case"),
    ],
)
def test_display_office(raw, shown):
    assert display_office(raw) == shown


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("BETH VAN DUYNE", "Beth Van Duyne"),
        ("MICHAEL MCCAUL", "Michael McCaul"),
        ("V. ALONZO ECHAVARRIA-GARZA", "V. Alonzo Echavarria-Garza"),
        ("JOHN O'NEAL III", "John O'Neal III"),
        ('ROBERT "BOB" SMITH', 'Robert "Bob" Smith'),
    ],
)
def test_display_person(raw, shown):
    assert display_person(raw) == shown


def test_web_url_adds_a_scheme():
    assert web_url("www.tedbrown.org") == "https://www.tedbrown.org"
    assert web_url("http://x.org") == "http://x.org"
    assert web_url("  ") is None
