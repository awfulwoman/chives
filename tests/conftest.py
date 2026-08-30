"""Global test isolation.

The suite must never read the developer's real ``.env`` — doing so couples
assertions to whatever machine happens to be running them. This strips
``CHIVES_*`` from the environment and detaches pydantic-settings from the
dotenv file for every test.

Live e2e tests deliberately use ``E2E_*`` variables instead, so they survive
this scrubbing.
"""
from __future__ import annotations

import os

import pytest

from chives.config import Config


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    for key in [k for k in os.environ if k.startswith("CHIVES_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(Config.model_config, "env_file", None)
