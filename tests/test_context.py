import pytest
from pathlib import Path
from chives.config import Config
from chives.store import Store
from chives.context import build_context


@pytest.fixture
def config(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "PERSONALITY.md").write_text("You are Chives.")
    (tmp_path / "profile" / "USER.md").write_text("User has ADHD.")
    (tmp_path / "profile" / "PROTOCOLS.md").write_text("Keep answers short.")
    c = Config()
    c.profile_path = str(tmp_path / "profile")
    c.state_path = str(tmp_path / "state")
    return c


@pytest.fixture
def store(config, tmp_path):
    return Store(config.state_path)


def test_includes_personality(config, store):
    ctx = build_context(config, store, "hello")
    assert "You are Chives" in ctx


def test_includes_user_profile(config, store):
    ctx = build_context(config, store, "hello")
    assert "ADHD" in ctx


def test_includes_memories(config, store):
    store.add_memory("user likes tea")
    ctx = build_context(config, store, "what do I like")
    assert "tea" in ctx


def test_missing_profile_files_dont_crash(config, store):
    config.profile_path = "/nonexistent/path"
    ctx = build_context(config, store, "hello")
    assert isinstance(ctx, str)
