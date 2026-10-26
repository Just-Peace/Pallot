"""California's key dates (the last day to register, the date to ask for a replacement mail
ballot, Election Day), from the Secretary of State's "Election Dates and Resources" page.

The page is plain HTML with one table, a row per upcoming statewide election, its columns
known by their headings: the election (its date, poll hours and name), voter registration
("Online or Postmark by" a date), the replacement vote-by-mail application's recommended date,
and when completed ballots must arrive. California mails every active voter a ballot and its
counties set their own in-person voting, so the page gives no early voting dates, and none are
shown. A page without a row Pallot can read is refused, so the last good copy keeps serving.
"""

from __future__ import annotations

import datetime as dt
import functools
import re

from ..states import Rows
from .key_dates import Deadlines, KeyDatesPage, first_date

SOURCE = "key_dates_ca"
DESCRIPTION = "California's registration and mail-ballot dates and Election Day, from its Secretary of State."
URL = "https://www.sos.ca.gov/elections/voting-resources/voting-california/election-dates-and-resources"
REGISTRATION_URL = "https://voterstatus.sos.ca.gov/"
COUNTY_OFFICES_URL = "https://www.sos.ca.gov/elections/voting-resources/county-elections-offices"
MAIL_URL = "https://www.sos.ca.gov/elections/voter-registration/vote-mail"

_DATE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})")
_NAME = re.compile(r"(?:[A-Z][A-Za-z]*\s+)*Election\b")


def parse(html: str) -> list[Deadlines]:
    """Every election row of the page's deadlines table; ValueError without the table's headings."""
    reader = Rows(cells=("td", "th"), breaks=True)
    reader.feed(html)
    reader.close()
    header = next((row for row in reader.rows if row and row[0].lower().startswith("election date")), None)
    if header is None:
        raise ValueError("no table of election deadlines")
    column = {key: next((i for i, cell in enumerate(header) if key in cell.lower()), None)
              for key in ("registration", "replacement")}
    found = []
    for row in reader.rows[reader.rows.index(header) + 1:]:
        day = first_date(row[0], _DATE) if row else None
        if day is None:
            continue
        rest = _DATE.sub("", row[0])
        named = _NAME.search(rest)

        def at(key: str) -> dt.date | None:
            index = column[key]
            return first_date(row[index], _DATE) if index is not None and index < len(row) else None

        found.append(Deadlines(day, named.group(0).strip() if named else "Election", register_by=at("registration"),
                               mail_apply_by=at("replacement"), state="CA"))
    return found


@functools.lru_cache(maxsize=2)
def elections(html: str) -> list[Deadlines]:
    """parse(), once per copy of the page; [] for a page it can't read."""
    try:
        return parse(html)
    except ValueError:
        return []


def no_elections(page: object) -> str | None:
    """The cache's check: a page without an election it can read is refused."""
    return None if isinstance(page, str) and elections(page) else "the page lists no elections"


class CaKeyDatesPage(KeyDatesPage):
    source = SOURCE
    url = URL

    @staticmethod
    def elections(html: str) -> list[Deadlines]:
        return elections(html)

    @staticmethod
    def no_elections(page: object) -> str | None:
        return no_elections(page)
