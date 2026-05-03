from __future__ import annotations
import email
import imaplib
import json
from contextlib import contextmanager
from chives.config import IMAPConfig
from chives.tools.registry import tool

_imap_config: IMAPConfig | None = None


def init(imap_config: IMAPConfig) -> None:
    global _imap_config
    _imap_config = imap_config
    _register()


@contextmanager
def _connection():
    assert _imap_config is not None
    conn = imaplib.IMAP4_SSL(_imap_config.host, _imap_config.port)
    conn.login(_imap_config.username, _imap_config.password)
    conn.select("INBOX")
    try:
        yield conn
    finally:
        conn.logout()


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="replace")
                break
    else:
        body = msg.get_payload(decode=True).decode(errors="replace")
    return {
        "from": msg.get("From", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "body_preview": body[:300],
    }


def _register() -> None:
    @tool
    def fetch_unread_emails(max_count: str) -> str:
        """Fetch unread emails from INBOX. max_count is the maximum number to return."""
        n = int(max_count)
        with _connection() as conn:
            _, data = conn.search(None, "UNSEEN")
            ids = data[0].split()[-n:]
            results = []
            for uid in ids:
                _, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
                raw = msg_data[0][1]
                results.append(_parse_message(raw))
        return json.dumps(results)

    @tool
    def search_emails(query: str) -> str:
        """Search emails by subject or sender. Returns up to 10 matches."""
        with _connection() as conn:
            _, data = conn.search(None, f'OR SUBJECT "{query}" FROM "{query}"')
            ids = data[0].split()[-10:]
            results = []
            for uid in ids:
                _, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
                raw = msg_data[0][1]
                results.append(_parse_message(raw))
        return json.dumps(results)

    @tool
    def fetch_email_body(message_id: str) -> str:
        """Fetch the full body of an email by its Message-ID header value."""
        with _connection() as conn:
            _, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
            ids = data[0].split()
            if not ids:
                return json.dumps({"error": f"No email found with ID: {message_id}"})
            _, msg_data = conn.fetch(ids[0], "(BODY.PEEK[])")
            msg = email.message_from_bytes(msg_data[0][1])
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="replace")
            return json.dumps({"message_id": message_id, "body": body})

    globals().update({
        "fetch_unread_emails": fetch_unread_emails,
        "search_emails": search_emails,
        "fetch_email_body": fetch_email_body,
    })
