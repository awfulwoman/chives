import pytest
from chives.config import Config


def test_defaults():
    config = Config()
    assert config.llm.base_url == "http://localhost:11434/v1"
    assert config.llm.model == "llama3.2"
    assert config.llm.api_key == "ollama"
    assert config.imap.port == 993
    assert config.morning_brief_time == "08:00"
    assert config.event_reminder_minutes == 15
    assert config.idle_checkin_hours == 0
    assert config.state_path == "state"
    assert config.profile_path == "profile"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHIVES_LLM__BASE_URL", "http://192.168.1.150:11434/v1")
    monkeypatch.setenv("CHIVES_LLM__MODEL", "mistral")
    config = Config()
    assert config.llm.base_url == "http://192.168.1.150:11434/v1"
    assert config.llm.model == "mistral"
