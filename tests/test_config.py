"""Configuration from the environment and the project's .env file."""

from __future__ import annotations

from pallot.config import DAY, DEMO_KEY, load_config, read_env_file


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
