import pytest
from chives.config import Config


def test_defaults():
    config = Config()
    assert config.llm.base_url == "http://localhost:11434/v1"
    assert config.llm.model == "llama3.2"
    assert config.llm.api_key == "ollama"
    assert config.gateway_url == "http://127.0.0.1:4000/mcp"
    assert config.morning_brief_time == "08:00"
    assert config.event_reminder_minutes == 15
    assert config.editor.username == ""
    assert config.editor.password == ""
    assert config.idle_checkin_hours == 0
    assert config.state_path == "state"
    assert config.profile_path == "profile"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHIVES_LLM__BASE_URL", "http://192.168.1.150:11434/v1")
    monkeypatch.setenv("CHIVES_LLM__MODEL", "mistral")
    config = Config()
    assert config.llm.base_url == "http://192.168.1.150:11434/v1"
    assert config.llm.model == "mistral"


def test_editor_env_override(monkeypatch):
    monkeypatch.setenv("CHIVES_EDITOR__USERNAME", "admin")
    monkeypatch.setenv("CHIVES_EDITOR__PASSWORD", "change_me")
    config = Config()
    assert config.editor.username == "admin"
    assert config.editor.password == "change_me"


def test_gateway_env_override(monkeypatch):
    monkeypatch.setenv("CHIVES_GATEWAY_URL", "http://192.168.1.100:4000/mcp")
    monkeypatch.setenv("CHIVES_MORNING_BRIEF_TIME", "07:30")
    config = Config()
    assert config.gateway_url == "http://192.168.1.100:4000/mcp"
    assert config.morning_brief_time == "07:30"
