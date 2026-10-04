"""Which sources are on: Pallot's defaults (pallot/sources.toml), the data folder's sources.toml
on top of them, and each voter's own switches, sent by their browser, on top of both."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pallot.admin import SOURCES
from pallot.settings import DEFAULT_SOURCES, DEFAULTS_FILE, BadSourcesFile, Sources, defaults, read_sources_file

from .conftest import switch


def enabled(client: TestClient) -> dict[str, bool]:
    return {s["id"]: s["enabled"] for s in client.get("/api/sources").json()["sources"]}


def test_the_defaults_file_names_every_source_that_can_be_turned_off():
    assert set(read_sources_file(DEFAULTS_FILE)) == {info.id for info in SOURCES if info.toggleable}


@pytest.mark.shipped_defaults
def test_the_defaults_come_from_the_file():
    assert DEFAULT_SOURCES == read_sources_file(DEFAULTS_FILE)
    assert DEFAULT_SOURCES["ballotpedia"] is False and DEFAULT_SOURCES["voteforpeace"] is False
    assert DEFAULT_SOURCES["sos"] is True


def test_the_data_folders_file_changes_the_defaults_for_everyone(make_app, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "sources.toml").write_text("[sources]\nfec = false\nexamplepac = false\n", encoding="utf-8")
    with TestClient(make_app()) as client:
        assert enabled(client)["fec"] is False and enabled(client)["examplepac"] is False
        assert enabled(client)["sos"] is True and enabled(client)["mupac"] is True  # a list not named: on
        switch(client, "fec", True)  # a voter's own switch still wins
        assert enabled(client)["fec"] is True


@pytest.mark.parametrize(("text", "why"), [
    ("[sources]\nfec = 'no'\n", "fec must be true or false"),
    ("[sources]\nfecc = false\n", "no such source fecc"),
    ("fec = false\n", "put the switches under [sources]"),
    ("[sources\n", "sources.toml: "),
])
def test_a_data_folder_file_that_cant_be_used_says_why(tmp_path, text, why):
    (tmp_path / "sources.toml").write_text(text, encoding="utf-8")
    with pytest.raises(BadSourcesFile, match=why.replace("[", r"\[")):
        defaults(["examplepac"], tmp_path / "sources.toml")


def test_no_file_in_the_data_folder_leaves_pallots_defaults(tmp_path):
    assert defaults(["examplepac"], tmp_path / "sources.toml") == {**DEFAULT_SOURCES, "examplepac": True}


def test_a_voters_choices_only_switch_known_sources():
    sources = Sources({"fec": True, "ballotpedia": False}).chosen('{"fec": false, "ballotpedia": true, "nope": false}')
    assert not sources.enabled("fec") and sources.enabled("ballotpedia") and sources.enabled("geocoding")
