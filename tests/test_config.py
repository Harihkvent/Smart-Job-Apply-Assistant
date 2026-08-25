"""Tests for src.config module."""

import os

import pytest
import yaml

from src.config import DEFAULTS, load_config


def test_load_config_defaults(tmp_path, monkeypatch):
    """When no config file exists, should return all defaults."""
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    config = load_config(config_path=str(tmp_path / "nonexistent.yml"))

    assert config["llm_provider"] == "krutrim"
    assert config["llm_endpoint"] == "https://cloud.olakrutrim.com/v1"
    assert config["llm_model"] == "Krutrim-spectre-v2"
    for key, value in DEFAULTS.items():
        assert config[key] == value


def test_load_config_from_file(tmp_path, monkeypatch):
    """Create a temp YAML file, load it, verify values override defaults."""
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text(yaml.dump({
        "llm_provider": "openai",
        "llm_model": "gpt-4",
        "max_daily_applies": 10,
    }))

    config = load_config(config_path=str(cfg_file))

    assert config["llm_provider"] == "openai"
    assert config["llm_model"] == "gpt-4"
    assert config["max_daily_applies"] == 10
    # Non-overridden defaults remain
    assert config["llm_endpoint"] == DEFAULTS["llm_endpoint"]
    assert config["server_port"] == DEFAULTS["server_port"]


def test_load_config_env_override(tmp_path, monkeypatch):
    """Set env vars and verify they override file values."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text(yaml.dump({"db_path": "file_db.db"}))

    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key-123")
    monkeypatch.setenv("DB_PATH", "env_db.db")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    config = load_config(config_path=str(cfg_file))

    # Env var overrides both default and file value
    assert config["db_path"] == "env_db.db"
    assert config["llm_api_key"] == "test-key-123"


def test_load_config_missing_file(tmp_path, monkeypatch):
    """Verify it works gracefully when file doesn't exist."""
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    missing = str(tmp_path / "does_not_exist.yml")
    config = load_config(config_path=missing)

    # Should not raise, should return defaults
    assert isinstance(config, dict)
    assert config["llm_provider"] == "krutrim"
    assert config["llm_endpoint"] == "https://cloud.olakrutrim.com/v1"
    assert config["llm_model"] == "Krutrim-spectre-v2"
