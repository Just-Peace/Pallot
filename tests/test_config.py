"""Configuration from the environment and the project's .env file."""

from __future__ import annotations

import pytest

from pallot import maintain
from pallot.__main__ import main
from pallot.config import DAY, DEMO_KEY, BadConfig, load_config, read_env_file


def test_env_file_values_with_the_environment_winning(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# a comment\nPALLOT_FEC_API_KEY = "from-file"\nexport PALLOT_HTTP_TIMEOUT=12  # seconds\nPALLOT_TTL_FEC=60\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("PALLOT_FEC_API_KEY", raising=False)
    monkeypatch.delenv("PALLOT_HTTP_TIMEOUT", raising=False)
    monkeypatch.setenv("PALLOT_TTL_FEC", "120")
    config = load_config(env_file=env_file)
    assert config.fec_api_key == "from-file" and config.http_timeout == 12.0
    assert config.ttl.fec == 120


def test_no_file_or_an_empty_key_means_demo_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PALLOT_FEC_API_KEY", raising=False)
    assert read_env_file(tmp_path / "missing.env") == {}
    assert load_config(env_file=tmp_path / "missing.env").fec_api_key == DEMO_KEY
    (tmp_path / ".env").write_text("PALLOT_FEC_API_KEY=\n", encoding="utf-8")
    assert load_config(env_file=tmp_path / ".env").fec_api_key == DEMO_KEY


def test_up_to_five_fec_keys_by_their_variables():
    env = {f"PALLOT_FEC_API_KEY{n}": f"k{n}" for n in range(2, 8)} | {"PALLOT_FEC_API_KEY": "k1"}
    assert list(load_config(env).fec_api_keys.values()) == ["k1", "k2", "k3", "k4", "k5"]
    assert load_config({"PALLOT_FEC_API_KEY3": " only "}).fec_api_keys == {"PALLOT_FEC_API_KEY3": "only"}
    assert load_config({"PALLOT_FEC_API_KEY": "k", "PALLOT_FEC_API_KEY2": "k"}).fec_api_keys == {"PALLOT_FEC_API_KEY": "k"}
    assert load_config({}).fec_api_keys == {"PALLOT_FEC_API_KEY": DEMO_KEY}


def test_allowed_hosts_are_a_comma_separated_list():
    assert load_config({"PALLOT_ALLOWED_HOSTS": " Pallot.lan, nas.local ,"}).allowed_hosts == ("pallot.lan", "nas.local")
    assert load_config({}).allowed_hosts == ()


def test_an_explicit_mapping_ignores_the_env_file(tmp_path):
    (tmp_path / ".env").write_text("PALLOT_FEC_API_KEY=from-file\n", encoding="utf-8")
    assert load_config({}, env_file=tmp_path / ".env").fec_api_key == DEMO_KEY


def test_tiles_are_kept_at_least_7_days():
    assert load_config({"PALLOT_TTL_TILES": "3600"}).ttl.tiles == 7 * DAY
    assert load_config({"PALLOT_TTL_TILES": str(30 * DAY)}).ttl.tiles == 30 * DAY


def test_the_transient_caches_caps_are_in_megabytes():
    config = load_config({"PALLOT_TILES_MAX_MB": "100", "PALLOT_SUGGEST_MAX_MB": "0.5"})
    assert (config.tiles_max_bytes, config.suggest_max_bytes) == (100 << 20, 512 << 10)
    assert (load_config({}).tiles_max_bytes, load_config({}).suggest_max_bytes) == (512 << 20, 64 << 20)


def test_port_and_prune_interval_come_from_the_environment():
    assert (load_config({}).port, load_config({}).prune_every) == (8000, 6 * 3600)
    config = load_config({"PALLOT_PORT": "9000", "PALLOT_PRUNE_EVERY": "600"})
    assert (config.port, config.prune_every) == (9000, 600)


def test_the_default_entry_is_the_address_unless_set_to_the_voter_card():
    assert load_config({}).default_entry == "address"
    assert load_config({"PALLOT_DEFAULT_ENTRY": "voter_card"}).default_entry == "voter_card"
    assert load_config({"PALLOT_DEFAULT_ENTRY": "Voter-Card"}).default_entry == "voter_card"
    assert load_config({"PALLOT_DEFAULT_ENTRY": "zip"}).default_entry == "address"


@pytest.mark.parametrize("name, value, why", [
    ("PALLOT_PORT", "80OO", "PALLOT_PORT must be a whole number, not '80OO'"),
    ("PALLOT_TTL_FEC", "7d", "PALLOT_TTL_FEC must be a whole number of seconds, not '7d'"),
    ("PALLOT_HTTP_TIMEOUT", "30s", "PALLOT_HTTP_TIMEOUT must be a number of seconds, not '30s'"),
    ("PALLOT_HTTP_TIMEOUT", "inf", "PALLOT_HTTP_TIMEOUT must be a number of seconds, not 'inf'"),
    ("PALLOT_MAX_LOOKUPS", "eight", "PALLOT_MAX_LOOKUPS must be a whole number, not 'eight'"),
    ("PALLOT_GOOGLE_DAILY_MAX", "1.5", "PALLOT_GOOGLE_DAILY_MAX must be a whole number, not '1.5'"),
    ("PALLOT_PRUNE_EVERY", "6h", "PALLOT_PRUNE_EVERY must be a whole number of seconds, not '6h'"),
    ("PALLOT_TILES_MAX_MB", "1GB", "PALLOT_TILES_MAX_MB must be a number of megabytes, not '1GB'"),
    ("PALLOT_SUGGEST_MAX_MB", "nan", "PALLOT_SUGGEST_MAX_MB must be a number of megabytes, not 'nan'"),
    ("PALLOT_ADDRESSES_MAX_MB", "lots", "PALLOT_ADDRESSES_MAX_MB must be a number of megabytes, not 'lots'"),
    ("PALLOT_LIMIT_BALLOT", "lots", "PALLOT_LIMIT_BALLOT must be a rate like 30/hour or 600/10min, or off, not 'lots'"),
])
def test_a_malformed_setting_names_its_variable_and_value(name, value, why):
    with pytest.raises(BadConfig) as raised:
        load_config({name: value})
    assert str(raised.value) == why


def test_blank_settings_keep_their_defaults():
    blank = {name: " " for name in ("PALLOT_PORT", "PALLOT_TTL_FEC", "PALLOT_HTTP_TIMEOUT", "PALLOT_TILES_MAX_MB",
                                    "PALLOT_LIMIT_BALLOT")}
    assert load_config(blank) == load_config({})


@pytest.mark.parametrize("command", [lambda: main([]), lambda: maintain.main(["check"])])
def test_pallot_and_pallot_cache_stop_with_one_line_on_a_bad_setting(command, monkeypatch, capsys):
    monkeypatch.setenv("PALLOT_PORT", "80OO")
    with pytest.raises(SystemExit) as stopped:
        raise SystemExit(command())
    assert stopped.value.code == 2
    assert capsys.readouterr().err == "PALLOT_PORT must be a whole number, not '80OO'\n"
