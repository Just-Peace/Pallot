"""The candidate-list grid six states share (states/grid.py), on Washington's 2026 grid: its election
dropdown, the CSV it exports on a postback, and its HTML table. tests/fixtures/grid_wa.html is the
page cut down to its dropdown and its table's first rows, grid_wa.csv the export, both without the
candidates' contact details (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from pallot.config import Ttls
from pallot.http_cache import HttpCache
from pallot.states import Office, legislator, us_house
from pallot.states import grid
from pallot.states.grid import GridList, GridRow

from .conftest import FIXTURES

PAGE = "https://voter.votewa.gov/CandidateList.aspx"
HTML = (FIXTURES / "grid_wa.html").read_text(encoding="utf-8")
CSV = (FIXTURES / "grid_wa.csv").read_bytes()
EXPORT = next(iter(grid.EXPORT))


class WaGrid(GridList):
    """A state's adapter as the grid's states give it: its page and its offices (Congress and the
    State Senate here)."""

    state = "WA"
    source = "state_wa"
    label = "Washington Secretary of State"
    page = PAGE
    description = "Washington's candidates."
    minimum = {"cd": 10}
    parties = {"STATES NO PARTY PREFERENCE": "No party preference"}

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        number = row.district.split()[-1]
        if row.district_type.upper() == "CONGRESSIONAL":
            return us_house("WA", int(number), row.district.upper())
        if row.district_type.upper() == "LEGISLATIVE" and row.race == "State Senator":
            return legislator("sd", int(number))
        return None


class TableGrid(WaGrid):
    table = True
    minimum = {}


def test_the_dropdown_gives_each_general_elections_id():
    found = grid.elections(HTML)["elections"]
    assert found == {"2027-11-02": "906", "2026-11-03": "899", "2025-11-04": "894", "2024-11-05": "889"}
    with pytest.raises(ValueError, match="not a candidate list page"):
        grid.elections("<html><body>Just a moment...</body></html>")


def test_the_export_has_every_active_candidate_with_its_shared_columns():
    found = grid.rows(CSV)
    assert len(found) == 887
    first = found[0]
    assert (first.race, first.district_type, first.district, first.name, first.party, first.order) == (
        "U.S. Representative", "Congressional", "Congressional District 1", "Suzan DelBene", "DEMOCRATIC", 1)
    assert first.cells["TERM TYPE"] == "Regular" and first.cells["EMAIL"] == ""


def test_the_html_table_reads_as_the_export_does():
    table = grid.rows(HTML)
    assert len(table) == 6
    assert [(r.race, r.district, r.name, r.party, r.order) for r in table] == [
        (r.race, r.district, r.name, r.party, r.order) for r in grid.rows(CSV)[:6]]


def test_a_withdrawn_or_inactive_candidate_is_left_out_under_any_columns_names():
    text = ('"Contest","District","Candidate Name","Party","Status","Ballot Order","Withdrawn Date"\r\n'
            '"State Senator","Legislative District 1","Ann Able","Democratic","Qualified","1",""\r\n'
            '"State Senator","Legislative District 1","Bo Baker","Republican","Withdrawn","2",""\r\n'
            '"State Senator","Legislative District 1","Cy Cole","Libertarian","Qualified","3","9/1/2026"\r\n'
            '"State Senator","Legislative District 1","Di Dunn","","ACTIVE","",""\r\n')
    assert [(r.name, r.party, r.order) for r in grid.rows(text)] == [("Ann Able", "Democratic", 1), ("Di Dunn", "", 0)]


def test_an_answer_that_isnt_the_grid_is_refused():
    for text in ("Service Unavailable", "<html><body><table><tr><td>Down</td></tr></table></body></html>"):
        with pytest.raises(ValueError, match="no heading row"):
            grid.rows(text)


def test_a_states_offices_become_filings_in_ballot_order():
    filings = WaGrid.parse(CSV)
    reach = Counter(f.reach for f in filings)
    assert reach["cd"] == 20 and reach["sd"] == 41 and set(reach) == {"cd", "sd"}
    assert {f.district for f in filings if f.reach == "cd"} == {str(n) for n in range(1, 11)}
    assert {f.day for f in filings} == {""}
    first = sorted((f for f in filings if f.district == "1" and f.reach == "cd"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name, f.office) for f in first] == [
        ("Suzan DelBene", "D", None, "U.S. Representative District 1"),
        ("Mary Silva", "R", None, "U.S. Representative District 1")]
    assert first[0].order < next(f for f in filings if f.district == "2" and f.reach == "cd").order


def test_a_list_short_of_its_races_is_refused():
    with pytest.raises(ValueError, match="U.S. House races, not 10"):
        WaGrid.parse(b"\r\n".join(CSV.splitlines()[:7]))


def test_the_index_is_the_dropdown_and_a_table_grid_keeps_its_filings_in_it():
    assert WaGrid.read_index(CSV) is None
    assert WaGrid.read_index(HTML.encode()) == {"elections": grid.elections(HTML)["elections"]}
    index = TableGrid.read_index(HTML.encode())
    assert [f["name"] for f in index["filings"]] == ["Suzan DelBene", "Mary Silva", "Rick Larsen", "Edwin H. Feller",
                                                     "John Braun", "Marie Gluesenkamp Perez"]


@pytest.mark.anyio
async def test_the_list_is_the_export_posted_back_for_the_elections_id_and_kept(tmp_path):
    posted = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})
        posted.append((request.url.params.get("e"), parse_qs(request.content.decode(), keep_blank_values=True)))
        return httpx.Response(200, content=CSV, headers={"content-type": "text/csv; charset=utf-8"})

    with respx.mock() as router:
        route = router.route(host="voter.votewa.gov").mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "cache.sqlite3", client)
            adapter = WaGrid(cache, Ttls())
            filings = await adapter.filings(dt.date(2026, 11, 3))
            assert route.call_count == 3  # the page, the election's page for its hidden fields, the export
            again = await adapter.filings(dt.date(2026, 11, 3))
            assert route.call_count == 3
            assert await adapter.filings(dt.date(2028, 11, 7)) is None
            assert route.call_count == 3
            cache.close()
    assert len(filings) == 61 and {f.day for f in filings} == {"2026-11-03"} and again == filings
    [(election, form)] = posted
    assert election == "899"
    assert form["__VIEWSTATE"] == ["VIEWSTATE-recorded"] and form["__EVENTVALIDATION"] == ["EVENTVALIDATION-recorded"]
    assert form[EXPORT] == [" "]


def test_a_table_grids_list_is_its_postbacks_table_dated_as_asked(tmp_path):
    cache = HttpCache(tmp_path / "cache.sqlite3", httpx.AsyncClient())
    adapter = TableGrid(cache, Ttls())
    page = adapter.on(TableGrid.read_index(HTML.encode()), dt.date(2026, 11, 3))
    assert {f.day for f in page} == {"2026-11-03"} and len(page) == 6
    assert adapter.combine([[], page]) == page
    cache.close()
