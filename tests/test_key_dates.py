"""Key dates (the Texas SOS's Important Election Dates page, and Michigan's worked out by rule):
parsing, calendar files, and the ballot's When to vote block."""

from __future__ import annotations

import dataclasses
import datetime as dt

import httpx
import pytest
import respx

from pallot import ics
from pallot.config import Ttls
from pallot.http_cache import HttpCache, RequestSpec, UpstreamError
from pallot.sources import key_dates
from pallot.sources.key_dates import Deadlines, parse
from pallot.states import key_dates as state_key_dates
from pallot.states.dates import Counts, Roll, columbus_day, mailed_to_every_voter, only_if

from .conftest import FIXTURES, get_ballot, switch

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
            assert await source.on(D(2026, 11, 3)) == NOV_3 and route.call_count == 2
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


def test_the_ballot_has_its_elections_key_dates(client, upstream, logged_calls):
    ballot = get_ballot(client)
    assert ballot["key_dates"] == {
        "election": "Uniform Election Date", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-19", "early_voting_end": "2026-10-30",
        "source": "Texas Secretary of State", "source_url": key_dates.URL, "computed": False,
    }
    assert upstream.count("sos.state.tx.us") == 1
    get_ballot(client)
    assert logged_calls() == 0 and upstream.count("sos.state.tx.us") == 1


def test_key_dates_off(client, upstream):
    switch(client, "key_dates", False)
    assert get_ballot(client)["key_dates"] is None
    assert upstream.count("sos.state.tx.us") == 0


def test_a_refusal_pauses_key_dates_and_the_ballot_still_loads(client, upstream):
    upstream.key_dates_status = 403
    ballot = get_ballot(client)
    assert ballot["key_dates"] is None and ballot["races"]
    assert any(note.startswith("Couldn't load the key dates") for note in ballot["notes"])
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


def test_michigans_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MI"})
    assert response.headers["content-disposition"] == 'attachment; filename="michigan-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "UID:mi-2026-11-03-early_start@pallot\r\nDTSTAMP" in unfolded and "DTSTART;VALUE=DATE:20261024" in unfolded
    assert "7 a.m. to 8 p.m.\\; if you're in line at 8" in unfolded and "Texas" not in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MI", "event": "mail"}).text
    assert "SUMMARY:Absentee application due (Nov 3 election)" in mail
    assert client.get("/api/key-dates.ics", params={"date": "2026-11-10", "state": "MI"}).status_code == 404
    assert client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "ZZ"}).status_code == 422
    assert upstream.count("sos.state.tx.us") == 0


# -- worked out by rule -----------------------------------------------------------------------


@pytest.mark.parametrize("day, early_start", [(D(2026, 11, 3), D(2026, 10, 24)), (D(2026, 8, 4), D(2026, 7, 25)),
                                              (D(2028, 11, 7), D(2028, 10, 28))])
def test_michigans_dates_follow_its_election_law(day, early_start):
    found = state_key_dates.computed("MI", day)
    assert (found.register_by, found.early_start, found.early_end, found.mail_apply_by) == (
        day - dt.timedelta(days=15), early_start, day - dt.timedelta(days=2), day - dt.timedelta(days=4))
    assert found.early_start.weekday() == 5 and found.early_end.weekday() == 6 and found.mail_apply_by.weekday() == 4


def test_only_michigans_statewide_election_days_have_dates():
    assert state_key_dates.first_tuesday_after_first_monday(2022, 11) == D(2022, 11, 8)
    assert state_key_dates.first_tuesday_after_first_monday(2027, 6) == D(2027, 6, 8)
    for day in (D(2026, 11, 10), D(2027, 11, 2), D(2026, 5, 5)):
        assert state_key_dates.computed("MI", day) is None, day
    assert state_key_dates.computed("TX", D(2026, 11, 3)) is None and state_key_dates.computed(None, D(2026, 11, 3)) is None


def test_same_day_registration_states_say_how_to_register_after_the_deadline():
    same_day = {state for state, guide in state_key_dates.GUIDES.items() if guide.late_registration}
    assert same_day == {"MI", "CA", "NV", "IA", "WI", "CO", "WY", "IL", "NC", "VA", "ME", "NM", "WA", "MD", "MT", "HI", "VT", "MN", "NH", "UT"}
    late = state_key_dates.GUIDES["MI"].voter_info().late_registration
    assert late.url == state_key_dates.MICHIGAN.registration_url and "through Election Day" in late.label
    assert state_key_dates.GUIDES["TX"].voter_info().late_registration is None


@pytest.mark.parametrize("state, register, mail, early_start, early_end", [
    ("FL", D(2026, 10, 5), D(2026, 10, 22), D(2026, 10, 24), D(2026, 10, 31)),
    ("NC", D(2026, 10, 9), D(2026, 10, 20), D(2026, 10, 15), D(2026, 10, 31)),
    ("PA", D(2026, 10, 19), D(2026, 10, 27), None, None),
    ("VA", D(2026, 10, 23), D(2026, 10, 23), D(2026, 9, 18), D(2026, 10, 31)),
])
def test_florida_north_carolina_pennsylvania_and_virginia_dates_follow_their_election_law(
    state, register, mail, early_start, early_end,
):
    found = state_key_dates.computed(state, D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        register, mail, early_start, early_end)
    assert (state_key_dates.computed(state, D(2027, 11, 2)) is not None) == (state == "VA")


@pytest.mark.parametrize("day, register, early_start, early_end", [
    (D(2026, 11, 3), D(2026, 10, 5), D(2026, 10, 7), D(2026, 10, 30)),
    (D(2028, 11, 7), D(2028, 10, 10), D(2028, 10, 11), D(2028, 11, 3)),  # past Columbus Day
])
def test_arizonas_dates_follow_its_election_law(day, register, early_start, early_end):
    found = state_key_dates.computed("AZ", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        register, None, early_start, early_end)
    assert state_key_dates.computed("AZ", D(2027, 11, 2)) is None


def test_a_state_without_registration_has_no_register_date_or_event(monkeypatch):
    monkeypatch.setitem(ics.GUIDES, "ZZ", state_key_dates.GUIDES["OH"])
    found = Counts(None, 7, 14, 1).on("ZZ", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start) == (None, D(2026, 10, 27), D(2026, 10, 20))
    assert [event.id for event in ics.events(found)] == ["early_start", "mail", "early_end", "election"]
    assert Counts(None, None, None, None, early_after_register=True).on("ZZ", D(2026, 11, 3)).early_start is None


@pytest.mark.parametrize("roll, register, mail", [
    (None, D(2026, 10, 4), D(2026, 10, 3)),
    (Roll(), D(2026, 10, 5), D(2026, 10, 5)),  # past Sunday, and past Saturday and Sunday
    (Roll(saturday=False), D(2026, 10, 5), D(2026, 10, 3)),
    (Roll(holidays=lambda year: (columbus_day(year), D(year, 10, 5))), D(2026, 10, 6), D(2026, 10, 6)),
])
def test_a_deadline_on_a_closed_day_rolls_to_the_next_open_one(roll, register, mail):
    found = Counts(30, 31, 17, 4, roll=roll).on("ZZ", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        register, mail, D(2026, 10, 17), D(2026, 10, 30))  # early voting's dates never move
    assert Roll(holidays=lambda year: (columbus_day(year),))(D(2026, 10, 10)) == D(2026, 10, 13)


def test_poll_hours_a_town_sets_and_two_time_zones():
    base = state_key_dates.GUIDES["MI"]
    town = dataclasses.replace(base, poll_hours="7 p.m.", hours_set_by="your town")
    assert town.voter_info().poll_hours == "until 7 p.m."
    assert town.polls == "Polls close at 7 p.m.; your town sets when they open. If you're in line at 7, you can vote."
    zones = dataclasses.replace(base, local_time=True)
    assert zones.voter_info().poll_hours == "7 a.m. – 8 p.m. local time"
    assert zones.polls == "Polls are open 7 a.m. to 8 p.m. local time; if you're in line at 8, you can vote."
    both = dataclasses.replace(town, poll_hours="8 p.m.", local_time=True, hours_set_by="your county")
    assert both.voter_info().poll_hours == "until 8 p.m. local time"
    assert both.polls.startswith("Polls close at 8 p.m. local time; your county sets when they open.")
    assert base.voter_info().poll_hours == "7 a.m. – 8 p.m." and dataclasses.replace(base, polls_text="x").polls == "x"


def test_mail_wording_for_an_excuse_and_for_a_ballot_mailed_to_everyone():
    assert only_if("you're away on Election Day") == "Only if you're away on Election Day."
    assert only_if("you're 65 or older", "sick") == "Only if you're 65 or older or sick."
    assert state_key_dates.GUIDES["TX"].mail_eligibility.startswith("Only if you're 65 or older, sick or disabled, away")
    assert state_key_dates.GUIDES["TX"].mail_eligibility.endswith(", or in jail but still eligible to vote.")
    assert mailed_to_every_voter("Mail it back.") == "Every active voter is mailed a ballot. Mail it back."
    assert state_key_dates.GUIDES["NV"].mail_eligibility.startswith("Every active voter is mailed a ballot. Mail it back")


def test_pallot_cache_refreshes_and_rebuilds_key_dates(client, make_app, upstream):
    get_ballot(client)
    assert make_app.cache_command("hard-refresh", "key_dates") == (0, "Key election dates (Texas SOS): Refreshed 1 saved response.")
    assert upstream.count("sos.state.tx.us") == 2
    assert make_app.cache_command("rebuild", "key_dates")[1].startswith("Deleted 1 saved response.\n")
    assert upstream.count("sos.state.tx.us") == 3
    assert get_ballot(client)["key_dates"]["register_by"] == "2026-10-05" and upstream.count("sos.state.tx.us") == 3
