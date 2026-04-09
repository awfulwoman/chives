import json
import pytest
from unittest.mock import MagicMock, patch
from chives.config import IMAPConfig
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def imap_config():
    return IMAPConfig(host="imap.example.com", port=993, username="user", password="pass")


def _make_fetch_response():
    """Simulates imaplib fetch response for a simple text email."""
    raw = (
        b"From: sender@example.com\r\n"
        b"Subject: Test subject\r\n"
        b"Date: Thu, 10 Apr 2026 10:00:00 +0000\r\n"
        b"Message-ID: <msg001@example.com>\r\n"
        b"\r\n"
        b"Hello world"
    )
    return [b"1 (RFC822 {%d}" % len(raw), raw]


def test_fetch_unread_emails(imap_config):
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.return_value = ("OK", _make_fetch_response())
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
        import sys
        sys.modules.pop("chives.tools.email", None)
        import chives.tools.email as email_tools
        email_tools.init(imap_config)
        result = email_tools.fetch_unread_emails(max_count="5")
        data = json.loads(result)
        assert isinstance(data, list)


def test_search_emails(imap_config):
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", _make_fetch_response())
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
        import sys
        sys.modules.pop("chives.tools.email", None)
        import chives.tools.email as email_tools
        email_tools.init(imap_config)
        result = email_tools.search_emails(query="test")
        data = json.loads(result)
        assert isinstance(data, list)
