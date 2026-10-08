"""bundles: building each source's bundled answers (the FEC's here), refreshing only what's due,
and Pallot loading them at startup."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
import time

import pytest
from fastapi.testclient import TestClient

from bundles import registry, store
from bundles import sos as sos_bundle
from bundles.__main__ import main
from bundles.entry import Bundle, BundleError
from bundles.refresh import BUILD_INTERVAL, refresh
from pallot.config import DAY, PROJECT_DIR, Config, Ttls
from pallot.http_cache import RequestSpec
from pallot.services import MIN_INTERVAL

from .conftest import FEC_KEY, TODAY, get_ballot

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)  # the cache's clock is the real one


def build(tmp_path, key: str = FEC_KEY, now: dt.datetime = NOW, **kwargs):
    config = Config(data_dir=tmp_path / "data", fec_api_key=key)
    [outcome] = refresh(["fec"], data_dir=tmp_path / "bundles", config=config, today=lambda: TODAY, now=now,
                        min_interval={}, **kwargs)
    return outcome


def test_the_bundle_holds_what_a_lookup_asks_the_fec(tmp_path, upstream):
    outcome = build(tmp_path)
    assert outcome.status == "updated" and outcome.counts["races"] == 14 and outcome.answers > 14  # the fixture's seats
    text = (tmp_path / "bundles" / "fec.json").read_text()
    answers = json.loads(text)["answers"]
    meta = store.read_meta(tmp_path / "bundles")["fec"]
    assert len(answers) == outcome.answers == meta["answers"] == len(text.splitlines()) - 2  # one answer per line
    urls = [answer["request"]["url"] for answer in answers]
    assert urls.count("https://api.open.fec.gov/v1/elections/") == 14  # each seat's race list
    assert any("/candidate/" in url for url in urls)  # and the breakdowns of the candidates on the ballot
    assert meta["last_checked"] == meta["last_refresh"] == NOW.isoformat()
    assert FEC_KEY not in text


def test_an_unchanged_bundle_only_notes_when_it_was_checked(tmp_path, upstream):
    build(tmp_path)
    written = (tmp_path / "bundles" / "fec.json").read_text()
    later = NOW + dt.timedelta(days=1)
    assert build(tmp_path, now=later).status == "no_changes"
    meta = store.read_meta(tmp_path / "bundles")["fec"]
    assert meta["last_checked"] == later.isoformat() and meta["last_refresh"] == NOW.isoformat()
    assert (tmp_path / "bundles" / "fec.json").read_text() == written


def test_nothing_is_written_when_a_call_fails_or_without_a_key(tmp_path, upstream):
    upstream.fec_status = 500
    failed = build(tmp_path)
    assert failed.status == "failed" and "FEC calls failed" in failed.detail
    assert "PALLOT_FEC_API_KEY" in build(tmp_path, key="DEMO_KEY").detail
    assert not (tmp_path / "bundles").exists()


def test_a_lookup_asks_the_fec_nothing_the_bundle_has(tmp_path, upstream, make_app):
    build(tmp_path)
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        notice = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "fec")["notice"]
    senate = next(r for r in ballot["races"] if r["name"] == "U.S. Senator")
    assert senate["cards"] and upstream.count("open.fec.gov") == asked
    assert notice.startswith(f"Came with {len(store.load('fec', tmp_path / 'bundles').answers):,} answers, checked ")


def test_a_stale_bundle_is_asked_again_and_a_newer_copy_is_kept(tmp_path, upstream, make_app):
    build(tmp_path, now=NOW - dt.timedelta(days=8))  # past Ttls.fec_bundle
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    assert upstream.count("open.fec.gov") > asked
    query = ("SELECT MIN(fetched_at) FROM responses WHERE source = 'fec' AND request LIKE '%elections%'"
             " AND request LIKE '%senate%'")
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        newest = db.execute(query).fetchone()[0]
    with TestClient(make_app(bundles=tmp_path / "bundles")):  # a restart loads the bundle again
        pass
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        assert db.execute(query).fetchone()[0] == newest  # the live answer, newer than the bundle's, stays


def build_sos(tmp_path, now: dt.datetime = NOW):
    [outcome] = refresh(["sos"], data_dir=tmp_path / "bundles", config=Config(data_dir=tmp_path / "data"),
                        today=lambda: TODAY, now=now, min_interval={})
    return outcome


def goelect_calls(upstream, path: str = "") -> list[str]:
    return [call for call in upstream.calls if "goelect.txelections" in call and path in call]


def test_the_sos_bundle_holds_the_statewide_data_each_for_its_lifetime(tmp_path, upstream):
    outcome = build_sos(tmp_path)
    assert outcome.status == "updated" and outcome.counts["elections"] >= 1 and outcome.counts["candidates"] > 100
    answers = store.load("sos", tmp_path / "bundles").answers
    entry = next(e for e in registry.BUNDLES if e.source == "sos")
    lifetimes = {answer["request"]["url"].rsplit("/", 1)[1]: entry.ttl(Ttls(), RequestSpec(**answer["request"]))
                 for answer in answers}
    assert lifetimes["2026"] == lifetimes["2027"] == 3 * DAY
    assert lifetimes["getAllRegions"] == lifetimes["getDeclarationStatus"] == 30 * DAY
    assert lifetimes["findQualifiedCandidates"] == 2 * DAY
    assert not any("getCandidateBallotOrder" in url for url in lifetimes)
    with pytest.raises(ValueError):
        entry.ttl(Ttls(), RequestSpec("GET", "https://goelect.txelections.civixapps.com/elsewhere"))


def test_a_lookup_asks_texas_sos_only_for_the_county_ballot_order(tmp_path, upstream, make_app):
    build_sos(tmp_path)
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        notice = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "sos")["notice"]
    assert ballot["races"] and goelect_calls(upstream)
    assert goelect_calls(upstream) == goelect_calls(upstream, "getCandidateBallotOrder")
    assert notice.startswith("Came with ")


def test_old_sos_answers_are_asked_again_by_their_own_lifetimes(tmp_path, upstream, make_app):
    build_sos(tmp_path, now=NOW - dt.timedelta(days=4))  # past the elections' and candidates' bundle lifetimes
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    assert goelect_calls(upstream, "getElectionsByYear") and goelect_calls(upstream, "findQualifiedCandidates")
    assert not goelect_calls(upstream, "getAllRegions") and not goelect_calls(upstream, "getPoliticalParties")


def build_ballot_orders(tmp_path):
    [outcome] = refresh(["sos_ballot_order"], data_dir=tmp_path / "bundles", config=Config(data_dir=tmp_path / "data"),
                        today=lambda: TODAY, now=NOW, min_interval={})
    return outcome


def ballot_order_key(answer) -> tuple[int, int]:
    return answer["request"]["json"]["electionId"], answer["request"]["json"]["countyId"]


def test_every_published_ballot_order_is_bundled_apart_from_the_statewide_data(tmp_path, upstream):
    outcome = build_ballot_orders(tmp_path)
    regions = len(json.loads((PROJECT_DIR / "tests" / "fixtures" / "sos_regions.json").read_text()))
    assert outcome.status == "updated" and outcome.counts["ballot_orders"] == 2  # the general's, in Harris and Travis
    assert len(goelect_calls(upstream, "getCandidateBallotOrder")) == outcome.counts["elections"] * regions
    answers = store.load("sos_ballot_order", tmp_path / "bundles").answers
    assert sorted(map(ballot_order_key, answers)) == [(53815, 101), (53815, 227)]  # empty ones are asked live
    entry = next(e for e in registry.BUNDLES if e.name == "sos_ballot_order")
    assert {entry.ttl(Ttls(), RequestSpec(**answer["request"])) for answer in answers} == {2 * DAY}
    assert build_sos(tmp_path).status == "updated"
    assert not any("getCandidateBallotOrder" in answer["request"]["url"]
                   for answer in store.load("sos", tmp_path / "bundles").answers)
    assert set(store.read_meta(tmp_path / "bundles")) == {"sos", "sos_ballot_order"}


def test_ballot_orders_stop_at_the_first_refusal_and_write_nothing(tmp_path, upstream):
    upstream.ballot_order_status = 403
    outcome = build_ballot_orders(tmp_path)
    assert outcome.status == "failed" and "ballot orders" in outcome.detail
    assert len(goelect_calls(upstream, "getCandidateBallotOrder")) == 1
    assert not (tmp_path / "bundles").exists()


def test_a_county_texas_sos_errs_on_is_left_out_up_to_a_limit(tmp_path, upstream):
    upstream.ballot_orders_down = {(53815, 227)}
    outcome = build_ballot_orders(tmp_path)
    assert outcome.status == "updated" and outcome.counts["server_errors"] == 1
    assert [ballot_order_key(a) for a in store.load("sos_ballot_order", tmp_path / "bundles").answers] == [(53815, 101)]
    upstream.ballot_orders_down = {(66618, county) for county in range(1, sos_bundle.MAX_SERVER_ERRORS + 2)}
    failed = build_ballot_orders(tmp_path)
    assert failed.status == "failed" and "HTTP 500" in failed.detail


def test_a_build_asks_texas_sos_a_request_a_second_and_a_lookup_unthrottled():
    assert BUILD_INTERVAL["sos"] == 1.0 and "sos" not in MIN_INTERVAL


def test_a_lookup_with_both_sos_bundles_asks_texas_sos_nothing(tmp_path, upstream, make_app):
    general = json.loads((PROJECT_DIR / "tests" / "fixtures" / "sos_ballot_53815_227.json").read_text())
    upstream.ballot_orders = {(66618, 227): general, (66734, 227): general}  # every election's published
    build_sos(tmp_path)
    build_ballot_orders(tmp_path)
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        notice = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "sos")["notice"]
    assert ballot["races"] and not goelect_calls(upstream)
    answers = sum(len(store.load(name, tmp_path / "bundles").answers) for name in ("sos", "sos_ballot_order"))
    assert notice.startswith(f"Came with {answers:,} answers, checked ")


def test_an_unpublished_ballot_order_is_still_asked_live(tmp_path, upstream, make_app):
    outcome = build_ballot_orders(tmp_path)
    build_sos(tmp_path)
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    asked = goelect_calls(upstream)
    assert asked == goelect_calls(upstream, "getCandidateBallotOrder") and len(asked) == outcome.counts["elections"] - 1


def fake(source: str, cadence: str, built: list[str], fail: bool = False) -> Bundle:
    """A source whose builder stores one answer in the throwaway cache, as a request would."""
    async def build_it(ctx):
        built.append(source)
        if fail:
            raise BundleError("refused")
        ctx.cache.seed(source, [(RequestSpec("GET", f"https://{source}.test/", params={"n": "1"}), {"n": 1})], time.time(), 60)
        return {}
    return Bundle(source, build_it, cadence, lifetime=lambda ttl, spec: DAY)


def test_due_refreshes_a_daily_source_checked_yesterday_but_not_a_weekly_one(tmp_path):
    built: list[str] = []
    bundles = (fake("daily", "daily", built), fake("weekly", "weekly", built))
    yesterday = NOW - dt.timedelta(days=1)
    refresh(data_dir=tmp_path, config=Config(data_dir=tmp_path / "data"), now=yesterday, min_interval={}, bundles=bundles)
    built.clear()
    outcomes = refresh(due=True, data_dir=tmp_path, config=Config(data_dir=tmp_path / "data"), now=NOW,
                       min_interval={}, bundles=bundles)
    assert built == ["daily"]
    assert [(o.source, o.status) for o in outcomes] == [("daily", "no_changes"), ("weekly", "skipped")]
    meta = store.read_meta(tmp_path)
    assert meta["daily"]["last_checked"] == NOW.isoformat() and meta["weekly"]["last_checked"] == yesterday.isoformat()
    built.clear()
    refresh(data_dir=tmp_path, config=Config(data_dir=tmp_path / "data"), now=NOW, min_interval={}, bundles=bundles)
    assert built == ["daily", "weekly"]  # without --due, everything asked for


def test_the_command_reports_each_source_and_fails_when_one_did(tmp_path, monkeypatch, capsys):
    built: list[str] = []
    monkeypatch.setattr(registry, "BUNDLES", (fake("daily", "daily", built), fake("broken", "daily", built, fail=True)))
    assert main(["refresh", "--data-dir", str(tmp_path)]) == 2
    out, err = capsys.readouterr()
    assert "daily: updated (1 answers)." in out and "broken: failed, refused." in err
    assert not (tmp_path / "broken.json").exists()
    assert main(["refresh", "--due", "--only", "daily", "--data-dir", str(tmp_path)]) == 0
    assert "daily: skipped, checked " in capsys.readouterr().out and built == ["daily", "broken"]


def test_settings_says_what_came_with_any_bundled_source(tmp_path, monkeypatch, make_app):
    monkeypatch.setattr(registry, "BUNDLES", (fake("polls", "daily", []),))
    store.write_answers(tmp_path / "bundles" / "polls.json", [{"request": {"method": "GET", "url": "https://polls.test/",
                                                                           "params": None}, "value": []}])
    store.write_meta(tmp_path / "bundles", "polls", {"last_checked": NOW.isoformat()})
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        notice = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "polls")["notice"]
    assert notice.startswith("Came with 1 answer, checked ")


def test_every_bundle_ships_with_pallot_and_has_a_lifetime():
    project = tomllib.loads((PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    tools = project["tool"]["setuptools"]
    assert "bundles" in tools["packages"] and "data/*.json" in tools["package-data"]["bundles"]
    assert project["project"]["scripts"]["pallot-bundle"] == "bundles.__main__:main"
    ignored = [line.strip() for line in (PROJECT_DIR / ".dockerignore").read_text().splitlines()]
    assert "/data" in ignored and not any(line.startswith(("bundles", "data", "**/data")) for line in ignored)
    files = {path.stem for path in store.PACKAGE_DATA_DIR.glob("*.json")} - {"meta"}
    names = [entry.name for entry in registry.BUNDLES]
    assert len(set(names)) == len(names)
    assert files <= set(names) and set(store.read_meta(store.PACKAGE_DATA_DIR)) <= set(names)
    for entry in registry.BUNDLES:
        if entry.lifetime is None:
            assert isinstance(getattr(Ttls(), f"{entry.name}_bundle"), int)
        if (store.PACKAGE_DATA_DIR / f"{entry.name}.json").exists():
            loaded = store.load(entry.name)
            assert loaded.answers and loaded.checked_at
            for answer in loaded.answers:
                spec = RequestSpec(**answer["request"])
                assert entry.ttl(Ttls(), spec) >= DAY and entry.wants(spec, answer["value"])
            assert store.answers_hash(loaded.answers) == store.read_meta(store.PACKAGE_DATA_DIR)[entry.name]["answers_hash"]
