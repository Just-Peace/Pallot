"""Texas SOS's two bundles (bundles/sos.py): the statewide data, and every county's ballot order."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from bundles import sos as sos_bundle
from bundles import store
from bundles.refresh import BUILD_INTERVAL
from pallot.config import DAY, PROJECT_DIR, Ttls
from pallot.http_cache import RequestSpec
from pallot.services import MIN_INTERVAL

from .bundling import NOW, answers, build, entry, lifetimes, notice
from .conftest import get_ballot


def build_sos(tmp_path, now: dt.datetime = NOW):
    return build(tmp_path, "sos", now=now)


def build_ballot_orders(tmp_path):
    return build(tmp_path, "sos_ballot_order")


def goelect_calls(upstream, path: str = "") -> list[str]:
    return [call for call in upstream.calls if "goelect.txelections" in call and path in call]


def ballot_order_key(answer) -> tuple[int, int]:
    return answer["request"]["json"]["electionId"], answer["request"]["json"]["countyId"]


def test_the_sos_bundle_holds_the_statewide_data_each_for_its_lifetime(tmp_path, upstream):
    outcome = build_sos(tmp_path)
    assert outcome.status == "updated" and outcome.counts["elections"] >= 1 and outcome.counts["candidates"] > 100
    sos = entry("sos")
    by_url = {answer["request"]["url"].rsplit("/", 1)[1]: sos.ttl(Ttls(), RequestSpec(**answer["request"]))
              for answer in answers(tmp_path, "sos")}
    assert by_url["2026"] == by_url["2027"] == 3 * DAY
    assert by_url["getAllRegions"] == by_url["getDeclarationStatus"] == 30 * DAY
    assert by_url["findQualifiedCandidates"] == 2 * DAY
    assert not any("getCandidateBallotOrder" in url for url in by_url)
    with pytest.raises(ValueError):
        sos.ttl(Ttls(), RequestSpec("GET", "https://goelect.txelections.civixapps.com/elsewhere"))


def test_a_lookup_asks_texas_sos_only_for_the_county_ballot_order(tmp_path, upstream, make_app):
    build_sos(tmp_path)
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        said = notice(client, "sos")
    assert ballot["races"] and goelect_calls(upstream)
    assert goelect_calls(upstream) == goelect_calls(upstream, "getCandidateBallotOrder")
    assert said.startswith("Came with ")


def test_old_sos_answers_are_asked_again_by_their_own_lifetimes(tmp_path, upstream, make_app):
    build_sos(tmp_path, now=NOW - dt.timedelta(days=4))  # past the elections' and candidates' bundle lifetimes
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    assert goelect_calls(upstream, "getElectionsByYear") and goelect_calls(upstream, "findQualifiedCandidates")
    assert not goelect_calls(upstream, "getAllRegions") and not goelect_calls(upstream, "getPoliticalParties")


def test_every_published_ballot_order_is_bundled_apart_from_the_statewide_data(tmp_path, upstream):
    outcome = build_ballot_orders(tmp_path)
    regions = len(json.loads((PROJECT_DIR / "tests" / "fixtures" / "sos_regions.json").read_text()))
    assert outcome.status == "updated" and outcome.counts["ballot_orders"] == 2  # the general's, in Harris and Travis
    assert len(goelect_calls(upstream, "getCandidateBallotOrder")) == outcome.counts["elections"] * regions
    assert sorted(map(ballot_order_key, answers(tmp_path, "sos_ballot_order"))) == [(53815, 101), (53815, 227)]  # empty ones are asked live
    assert lifetimes(tmp_path, "sos_ballot_order") == {2 * DAY}
    assert build_sos(tmp_path).status == "updated"
    assert not any("getCandidateBallotOrder" in answer["request"]["url"] for answer in answers(tmp_path, "sos"))
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
    assert [ballot_order_key(a) for a in answers(tmp_path, "sos_ballot_order")] == [(53815, 101)]
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
        said = notice(client, "sos")
    assert ballot["races"] and not goelect_calls(upstream)
    bundled = len(answers(tmp_path, "sos")) + len(answers(tmp_path, "sos_ballot_order"))
    assert said.startswith(f"Came with {bundled:,} answers, checked ")


def test_an_unpublished_ballot_order_is_still_asked_live(tmp_path, upstream, make_app):
    outcome = build_ballot_orders(tmp_path)
    build_sos(tmp_path)
    upstream.calls.clear()
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    asked = goelect_calls(upstream)
    assert asked == goelect_calls(upstream, "getCandidateBallotOrder") and len(asked) == outcome.counts["elections"] - 1
