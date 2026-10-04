"""Key dates (the Texas SOS's Important Election Dates page): parsing, calendar files, and
the ballot's When to vote block."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from pallot import ics
from pallot.config import Ttls
from pallot.http_cache import HttpCache, RequestSpec, UpstreamError, track_calls
from pallot.sources import key_dates
from pallot.sources.key_dates import Deadlines, parse

from .conftest import FIXTURES, get_ballot, last_use, switch

D = dt.date
NOV_3 = Deadlines(D(2026, 11, 3), "Uniform Election Date", register_by=D(2026, 10, 5), mail_apply_by=D(2026, 10, 23),
                  early_start=D(2026, 10, 19), early_end=D(2026, 10, 30))
STAMP = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)


def page() -> str:
    return (FIXTURES / "sos_key_dates.html").read_text(encoding="utf-8")


# -- parsing ----------------------------------------------------------------------------


def test_the_recorded_page_gives_every_2026_election():
    found = parse(page())
    assert [(d.day, d.name) for d in found] == [
        (D(2026, 3, 3), "Primary Election"),
        (D(2026, 5, 2), "Uniform Election Date (Limited)"),
        (D(2026, 5, 26), "Primary Runoff Election"),
        (D(2026, 11, 3), "Uniform Election Date"),
    ]  # the 2024 and 2025 tables are inside HTML comments
    assert found[-1] == NOV_3


def test_label_variants_footnotes_and_notes():
    primary, may, runoff, _ = parse(page())
    # "First Day of Early Voting", without "by Personal Appearance"; the date has a "*" footnote
    assert (primary.early_start, primary.early_end, primary.mail_apply_by) == (D(2026, 2, 17), D(2026, 2, 27), D(2026, 2, 20))
    assert may.mail_apply_by == D(2026, 4, 20)  # moved off San Jacinto Day, with a note after the date
    assert runoff.register_by == D(2026, 4, 27)


def test_rows_in_any_order_and_look_alike_rows():
    html = """
    <table class="norm-5px" summary="Saturday, May 1, 2027 &ndash; Uniform Election Date">
      <tr><th colspan="2">Saturday, May 1, 2027 – Uniform Election Date</th></tr>
      <tr><td>First day to apply for a ballot by mail</td><td>Friday, January 1, 2027</td></tr>
      <tr><td>Last Day to Apply by Mail (<strong>Received,&nbsp;not</strong>&nbsp;Postmarked)</td>
          <td>Tuesday, April 20, 2027 at 5:00 p.m.</td></tr>
      <tr><td>Last Day for Candidates Planning to File to Register to Vote</td><td>Monday, January 4, 2027</td></tr>
      <tr><td>Last  day to register<br>to vote</td><td>Thursday, April 1, 2027*<br> *A note</td></tr>
    </table>"""
    assert parse(html) == [Deadlines(D(2027, 5, 1), "Uniform Election Date", register_by=D(2027, 4, 1),
                                     mail_apply_by=D(2027, 4, 20))]


def test_the_title_can_come_from_the_heading_row():
    html = """<table class="norm-5px"><caption>Longer calendars are elsewhere</caption>
      <tr><th colspan="2">Tuesday, March 2, 2027 - Special Election</th></tr>
      <tr><td>Last Day to Register to Vote</td><td>Monday, February 1, 2027</td></tr></table>"""
    assert parse(html) == [Deadlines(D(2027, 3, 2), "Special Election", register_by=D(2027, 2, 1))]


def test_another_layout_gives_nothing():
    assert parse("<html><table><tr><td>Last Day to Register to Vote</td><td>Monday, October 5, 2026</td></tr></table>") == []
    assert parse('<table class="norm-5px" summary="Important dates"><tr><td>x</td><td>y</td></tr></table>') == []
    assert parse("") == []


# -- calendar files -----------------------------------------------------------------------


def test_the_calendar_file():
    text = ics.calendar(NOV_3, today=D(2026, 9, 27), stamp=STAMP)
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    unfolded = text.replace("\r\n ", "")
    assert [line.removeprefix("UID:") for line in unfolded.split("\r\n") if line.startswith("UID:")] == [
        "tx-2026-11-03-register@pallot", "tx-2026-11-03-early_start@pallot", "tx-2026-11-03-early_end@pallot",
        "tx-2026-11-03-election@pallot",
    ]  # the mail-ballot deadline only when asked for: most voters can't vote by mail
    assert "DTSTART;VALUE=DATE:20261005\r\nDTEND;VALUE=DATE:20261006" in unfolded
    assert "DTSTAMP:20260927T120000Z" in unfolded and "LOCATION" not in unfolded
    assert "SUMMARY:Election Day (Nov 3 election)" in unfolded
    assert f"Check that you're registered: {key_dates.REGISTRATION_URL}\\n\\nDates from" in unfolded
    assert "7 a.m. to 7 p.m.\\; if you're in line at 7\\, you can vote." in unfolded


def test_one_event_and_dates_already_past():
    mail = ics.calendar(NOV_3, today=D(2026, 9, 27), stamp=STAMP, only="mail").replace("\r\n ", "")
    assert mail.count("BEGIN:VEVENT") == 1 and "UID:tx-2026-11-03-mail@pallot" in mail and "received\\, not postmarked" in mail
    later = ics.calendar(NOV_3, today=D(2026, 10, 20), stamp=STAMP)
    assert later.count("BEGIN:VEVENT") == 2  # the last day of early voting, and Election Day
    assert ics.calendar(NOV_3, today=D(2026, 11, 4), stamp=STAMP) is None
    assert ics.calendar(Deadlines(D(2026, 11, 3), "x"), today=D(2026, 9, 27), stamp=STAMP, only="register") is None


def test_long_lines_fold_without_splitting_a_character():
    folded = ics._fold("DESCRIPTION:" + "é" * 80)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "DESCRIPTION:" + "é" * 80


# -- fetching -------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_page_is_cached_as_text_and_parsed_once(tmp_path):
    with respx.mock() as router:
        route = router.get(key_dates.URL).mock(return_value=httpx.Response(200, text=page(),
                                                                            headers={"content-type": "text/html"}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            source = key_dates.KeyDatesPage(cache, Ttls())
            first = await source.deadlines()
            assert await source.on(D(2026, 11, 3)) == NOV_3 and await source.on(D(2026, 11, 4)) is None
            assert await source.deadlines() is first  # parsed once per fetched copy
            assert route.call_count == 1
            assert (await cache.refresh(key_dates.SOURCE)).refreshed == 1  # re-fetched as text
    assert RequestSpec("GET", key_dates.URL).key != RequestSpec("GET", key_dates.URL, as_text=True).key
    assert RequestSpec.loads(RequestSpec("GET", "https://x.test/", as_text=True).dumps()).as_text


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.anyio
async def test_a_page_with_no_election_table_keeps_the_old_page(tmp_path):
    clock = Clock()
    maintenance = httpx.Response(200, text="<html><body>Down for maintenance</body></html>",
                                 headers={"content-type": "text/html"})
    with respx.mock() as router:
        route = router.get(key_dates.URL).mock(side_effect=[
            httpx.Response(200, text=page(), headers={"content-type": "text/html"}), maintenance, maintenance,
        ])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, retry_after=Ttls().retry_after, clock=clock)
            source = key_dates.KeyDatesPage(cache, Ttls())
            assert await source.on(D(2026, 11, 3)) == NOV_3
            clock.now += Ttls().key_dates + 1
            stats = track_calls()
            assert await source.on(D(2026, 11, 3)) == NOV_3 and stats.stale_sources == {key_dates.SOURCE}
            report = await cache.refresh(key_dates.SOURCE)
            assert report.failed == 1 and report.errors == (f"{key_dates.URL}: the page lists no elections",)
            assert await source.on(D(2026, 11, 3)) == NOV_3
            cache.close()
    assert route.call_count == 3


@pytest.mark.anyio
async def test_a_page_with_no_election_table_and_no_old_page(tmp_path):
    with respx.mock() as router:
        router.get(key_dates.URL).mock(return_value=httpx.Response(200, text="<html>Moved</html>",
                                                                   headers={"content-type": "text/html"}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, retry_after=Ttls().retry_after)
            with pytest.raises(UpstreamError, match="^key_dates: the page lists no elections$"):
                await key_dates.KeyDatesPage(cache, Ttls()).deadlines()
            cache.close()


def test_the_check_refuses_only_a_page_without_elections():
    assert key_dates.no_elections(page()) is None
    assert key_dates.no_elections("<p>Maintenance</p>") == "the page lists no elections"


# -- through the API ------------------------------------------------------------------------


def test_the_ballot_has_its_elections_key_dates(client, upstream):
    ballot = get_ballot(client)
    assert ballot["key_dates"] == {
        "election": "Uniform Election Date", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-19", "early_voting_end": "2026-10-30",
        "source_url": key_dates.URL,
    }
    assert upstream.count("sos.state.tx.us") == 1 and last_use(client, key_dates.SOURCE)["status"] == "used"
    assert get_ballot(client)["meta"]["external_calls"] == 0 and upstream.count("sos.state.tx.us") == 1


def test_key_dates_off(client, upstream):
    switch(client, "key_dates", False)
    assert get_ballot(client)["key_dates"] is None
    assert upstream.count("sos.state.tx.us") == 0 and last_use(client, key_dates.SOURCE)["status"] == "off"


def test_a_refusal_pauses_key_dates_and_the_ballot_still_loads(client, upstream):
    upstream.key_dates_status = 403
    ballot = get_ballot(client)
    assert ballot["key_dates"] is None and ballot["races"]
    assert any(note.startswith("Couldn't load the key dates") for note in ballot["notes"])
    assert last_use(client, key_dates.SOURCE)["status"] == "error"
    get_ballot(client)
    assert upstream.count("sos.state.tx.us") == 1  # paused: not asked again
    status = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == key_dates.SOURCE)
    assert status["notice"].startswith("Paused until") and status["notice_tone"] == "warn"


def test_calendar_downloads(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03"})
    assert response.status_code == 200 and response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="texas-election-2026-11-03.ics"'
    assert response.text.count("BEGIN:VEVENT") == 4

    one = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "event": "mail"})
    assert one.text.count("BEGIN:VEVENT") == 1
    assert one.headers["content-disposition"] == 'attachment; filename="texas-election-2026-11-03-mail.ics"'

    assert client.get("/api/key-dates.ics", params={"date": "2026-11-04"}).status_code == 404
    assert client.get("/api/key-dates.ics", params={"date": "2026-11-03", "event": "nope"}).status_code == 422
    assert upstream.count("sos.state.tx.us") == 1


def test_pallot_cache_refreshes_and_rebuilds_key_dates(client, make_app, upstream):
    get_ballot(client)
    assert make_app.cache_command("hard-refresh", "key_dates") == (0, "Key election dates (Texas SOS): Refreshed 1 saved response.")
    assert upstream.count("sos.state.tx.us") == 2
    assert make_app.cache_command("rebuild", "key_dates")[1].startswith("Deleted 1 saved response.\n")
    assert upstream.count("sos.state.tx.us") == 3
    assert get_ballot(client)["key_dates"]["register_by"] == "2026-10-05" and upstream.count("sos.state.tx.us") == 3
