"""Configuration from the environment and the project's .env file."""

from __future__ import annotations

from votebot.config import DEMO_KEY, load_config, read_env_file


def test_env_file_values_with_the_environment_winning(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# a comment\nVOTEBOT_FEC_API_KEY = "from-file"\nexport VOTEBOT_HTTP_TIMEOUT=12  # seconds\nVOTEBOT_TTL_FEC=60\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("VOTEBOT_FEC_API_KEY", raising=False)
    monkeypatch.delenv("VOTEBOT_HTTP_TIMEOUT", raising=False)
    monkeypatch.setenv("VOTEBOT_TTL_FEC", "120")
    config = load_config(env_file=env_file)
    assert config.fec_api_key == "from-file" and config.http_timeout == 12.0
    assert config.ttl.fec == 120


def test_no_file_or_an_empty_key_means_demo_key(tmp_path, monkeypatch):
    monkeypatch.delenv("VOTEBOT_FEC_API_KEY", raising=False)
    assert read_env_file(tmp_path / "missing.env") == {}
    assert load_config(env_file=tmp_path / "missing.env").fec_api_key == DEMO_KEY
    (tmp_path / ".env").write_text("VOTEBOT_FEC_API_KEY=\n", encoding="utf-8")
    assert load_config(env_file=tmp_path / ".env").fec_api_key == DEMO_KEY


def test_an_explicit_mapping_ignores_the_env_file(tmp_path):
    (tmp_path / ".env").write_text("VOTEBOT_FEC_API_KEY=from-file\n", encoding="utf-8")
    assert load_config({}, env_file=tmp_path / ".env").fec_api_key == DEMO_KEY
