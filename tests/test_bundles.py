"""bundles: refreshing only what's due, the command, Settings' notice and what ships with Pallot.
Each source's builder is tested in its own test_bundle_<source>.py."""

from __future__ import annotations

import datetime as dt
import sys
import time

from fastapi.testclient import TestClient

from bundles import registry, store
from bundles.__main__ import main
from bundles.entry import Bundle, BundleError
from bundles.refresh import refresh
from pallot.config import DAY, PROJECT_DIR, Config, Ttls
from pallot.http_cache import RequestSpec

from .bundling import NOW, notice

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


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
        assert notice(client, "polls").startswith("Came with 1 answer, checked ")


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
                assert "headers" not in answer["request"]  # never a key or a page's token
            assert store.answers_hash(loaded.answers) == store.read_meta(store.PACKAGE_DATA_DIR)[entry.name]["answers_hash"]
