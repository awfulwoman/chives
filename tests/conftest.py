import pytest


@pytest.fixture(autouse=True)
def isolate_dotenv(tmp_path, monkeypatch):
    """Config() reads .env from cwd — run tests in an empty dir so a
    developer's real .env (secrets, live LLM URL, etc.) never leaks in."""
    monkeypatch.chdir(tmp_path)
