from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import trackaipac_cache as t
from trackaipac_cache.parser import normalize_name
from trackaipac_cache.refresh import refresh

from .conftest import FIXTURES, SOURCES, at, drop_item

PELTOLA_TOTAL = "Israel Lobby Total: $96,546"


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    """Two refreshes: day 1 = fixtures, day 2 = Peltola's total changed and Tom Sell removed."""
    pages = {s: (FIXTURES / f"{s}.html").read_text(encoding="utf-8") for s in SOURCES}
    data_dir = tmp_path_factory.mktemp("cache")
    refresh(data_dir=data_dir, fetcher=lambda: pages, now=at(1))
    day2 = dict(pages)
    day2["candidates"] = drop_item(pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $99,999", 1), "Tom Sell")
    refresh(data_dir=data_dir, fetcher=lambda: day2, now=at(2))
    return data_dir


def test_get_candidate_by_id_and_name(cache):
    by_id = t.get_candidate("ak-mary-peltola", data_dir=cache)
    assert by_id is not None and by_id.name == "Mary Peltola"
    assert t.get_candidate("AK-MARY-PELTOLA", data_dir=cache) == by_id
    assert t.get_candidate("  mary PELTOLA ", data_dir=cache) == by_id
    assert by_id.categories == ("watchlist",)
    assert by_id.seat == "AK-SEN"
    listing = by_id.listing("watchlist")
    assert listing.israel_lobby_total == 99999  # reads the latest snapshot
    assert listing.lines[2] == "Israel Lobby Total: $99,999"
    assert by_id.listing("congress") is None


def test_get_candidate_fuzzy_name_forms(cache):
    assert t.get_candidate("angelica duenas", data_dir=cache).candidate_id == "ca-angelica-duenas"
    assert t.get_candidate("Justin J Pearson", data_dir=cache).candidate_id == "tn-justin-j-pearson"


def test_get_candidate_unknown_and_ambiguous(cache):
    assert t.get_candidate("Nobody McNobody", data_dir=cache) is None
    assert t.get_candidate("Tom Sell", data_dir=cache) is None  # no longer listed
    with pytest.raises(t.AmbiguousNameError) as exc:
        t.get_candidate("Mike Rogers", data_dir=cache)
    assert exc.value.candidate_ids == ["al-mike-rogers", "mi-mike-rogers"]
    assert t.get_candidate("mi-mike-rogers", data_dir=cache).chamber == "senate"


def test_every_listing_is_kept_unmerged(cache):
    mejia = t.get_candidate("Analilia Mejia", data_dir=cache)
    assert mejia.categories == ("endorsed", "congress")
    assert [(item.section, item.incumbent) for item in mejia.listings_in("endorsed")] == [
        ("Candidates Endorsed By Citizens Against AIPAC COrruption", False),
        ("Our Endorsed Incumbents", True),
    ]
    assert mejia.listing("congress").seat_text == "NJ-11 [D]"

    tlaib = t.get_candidate("Rashida Tlaib", data_dir=cache)
    assert tlaib.party == "D"
    endorsed, congress = tlaib.listing("endorsed"), tlaib.listing("congress")
    assert endorsed.party is None and congress.party == "D"  # each listing as its page shows it
    assert endorsed.donate_url.startswith("https://secure.actblue.com/donate/rashida-rejects-aipac")
    assert congress.donate_url is None


def test_rows_without_seat_and_vacancies_are_queryable(cache):
    fleischmann = t.get_candidate("Chuck Fleischmann", data_dir=cache)
    assert (fleischmann.state, fleischmann.seat, fleischmann.chamber) == ("TN", None, None)
    assert fleischmann.listing("congress").israel_lobby_total == 63999
    tennessee = t.list_congress(state="TN", data_dir=cache)
    assert "Chuck Fleischmann" in {c.name for c in tennessee}
    assert "Chuck Fleischmann" not in {c.name for c in t.list_congress(state="TN", chamber="house", data_dir=cache)}

    with pytest.raises(t.AmbiguousNameError) as exc:
        t.get_candidate("Vacant", data_dir=cache)
    assert exc.value.candidate_ids == ["fl-vacant", "tx-vacant"]
    assert t.get_candidate("tx-vacant", data_dir=cache).listing("congress").seat_text == "TX- 23"


def test_list_watchlist(cache):
    everyone = t.list_watchlist(data_dir=cache)
    assert len(everyone) == 53  # Tom Sell dropped on day 2
    assert all("watchlist" in c.categories for c in everyone)
    texas = t.list_watchlist(state="TX", data_dir=cache)
    assert texas == t.list_watchlist(state="texas", data_dir=cache) == t.list_watchlist(state="tx", data_dir=cache)
    assert texas and all(c.state == "TX" for c in texas)
    reps = t.list_watchlist(party="Republican", data_dir=cache)
    assert reps == t.list_watchlist(party="r", data_dir=cache)
    assert reps and all(c.party == "R" for c in reps)
    tx_dems = t.list_watchlist(state="TX", party="D", data_dir=cache)
    assert {c.name for c in tx_dems} >= {"James Talarico", "Colin Allred", "Bobby Pulido"}


def test_list_filters_reject_unknown_values(cache):
    with pytest.raises(ValueError, match="unknown state"):
        t.list_watchlist(state="Atlantis", data_dir=cache)
    with pytest.raises(ValueError, match="unknown party"):
        t.list_watchlist(party="Whig", data_dir=cache)
    with pytest.raises(ValueError, match="unknown chamber"):
        t.list_congress(chamber="lords", data_dir=cache)


def test_list_endorsed_incumbent_filter(cache):
    everyone = t.list_endorsed(data_dir=cache)
    incumbents = t.list_endorsed(incumbents_only=True, data_dir=cache)
    challengers = t.list_endorsed(incumbents_only=False, data_dir=cache)
    assert (len(everyone), len(incumbents), len(challengers)) == (55, 20, 36)
    both = {c.name for c in incumbents} & {c.name for c in challengers}
    assert both == {"Analilia Mejia"}  # listed in both sections of the page
    assert {c.name for c in t.list_endorsed(state="Vermont", data_dir=cache)} == {"Bernie Sanders", "Peter Welch", "Becca Balint"}
    assert [c.name for c in t.list_endorsed(state="AR", incumbents_only=False, data_dir=cache)] == ["Robb Ryerse"]


def test_list_congress(cache):
    assert len(t.list_congress(data_dir=cache)) == 535
    assert len(t.list_congress(chamber="senate", data_dir=cache)) == 100
    vt = t.list_congress(state="VT", data_dir=cache)
    assert {c.seat for c in vt} == {"VT-SEN", "VT-AL"}
    assert {c.name for c in t.list_congress(state="ME", party="I", data_dir=cache)} == {"Angus King"}


def test_search(cache):
    assert [c.name for c in t.search("peltola", data_dir=cache)] == ["Mary Peltola"]
    assert [c.candidate_id for c in t.search("mike rogers", data_dir=cache)] == ["al-mike-rogers", "mi-mike-rogers"]
    assert t.search("   ", data_dir=cache) == []
    assert {c.name for c in t.search("314 Action", data_dir=cache)} == {"Janelle Bynum", "Maxine Dexter"}
    assert "Mary Peltola" in {c.name for c in t.search("AK-SEN", data_dir=cache)}


def test_search_ranks_name_matches_first(cache):
    results = t.search("jac", data_dir=cache)
    name_hit = ["jac" in normalize_name(c.name) for c in results]
    assert any(name_hit) and not all(name_hit)  # names like "Jace…" and PAC "JAC" both match
    assert name_hit == sorted(name_hit, reverse=True)


def test_history(cache):
    snaps = t.history("Mary Peltola", data_dir=cache)
    assert [(s.date, s.category, s.israel_lobby_total) for s in snaps] == [
        (date(2026, 9, 1), "watchlist", 96546),
        (date(2026, 9, 2), "watchlist", 99999),
    ]
    assert snaps[0].lines[2] == "Israel Lobby Total: $96,546"


def test_history_of_removed_candidate_and_repeat_listings(cache):
    assert [s.date for s in t.history("Tom Sell", data_dir=cache)] == [date(2026, 9, 1)]
    mejia = t.history("nj-analilia-mejia", data_dir=cache)
    assert [(s.date.day, s.category, s.incumbent) for s in mejia] == [
        (1, "endorsed", False), (1, "endorsed", True), (1, "congress", None),
        (2, "endorsed", False), (2, "endorsed", True), (2, "congress", None),
    ]


def test_history_unknown_and_ambiguous(cache):
    assert t.history("Nobody McNobody", data_dir=cache) == []
    with pytest.raises(t.AmbiguousNameError):
        t.history("Mike Rogers", data_dir=cache)


def test_last_refreshed(cache, tmp_path):
    assert t.last_refreshed(data_dir=cache) == datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    assert t.last_refreshed(data_dir=tmp_path) is None


def test_empty_cache_reads(tmp_path):
    assert t.get_candidate("Mary Peltola", data_dir=tmp_path) is None
    assert t.list_watchlist(data_dir=tmp_path) == []
    assert t.search("mary", data_dir=tmp_path) == []
    assert t.history("Mary Peltola", data_dir=tmp_path) == []


def test_reads_see_rewrites(pages, tmp_path):
    refresh(data_dir=tmp_path, fetcher=lambda: pages, now=at(1))
    assert t.get_candidate("Mary Peltola", data_dir=tmp_path).listing("watchlist").israel_lobby_total == 96546
    changed = {**pages, "candidates": pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $11,111", 1)}
    refresh(data_dir=tmp_path, fetcher=lambda: changed, now=at(1))  # same size, same day
    assert t.get_candidate("Mary Peltola", data_dir=tmp_path).listing("watchlist").israel_lobby_total == 11111


def test_env_var_selects_data_dir(cache, monkeypatch):
    monkeypatch.setenv("TRACKAIPAC_CACHE_DIR", str(cache))
    assert t.get_candidate("Mary Peltola").listing("watchlist").israel_lobby_total == 99999
