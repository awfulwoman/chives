import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(tmp_path, username="admin", password="secret"):
    from chives.connectors.editor import register_editor_routes
    from chives.config import Config, EditorConfig

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "PERSONALITY.md").write_text("You are Chives.")

    config = Config.model_construct(
        editor=EditorConfig(username=username, password=password),
        profile_path=str(profile_dir),
    )

    app = FastAPI()
    register_editor_routes(app, config)
    return app, profile_dir


def test_editor_requires_auth(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor")
    assert resp.status_code == 401


def test_editor_rejects_bad_credentials(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor", auth=("admin", "wrong"))
    assert resp.status_code == 401


def test_editor_disabled_when_unset(tmp_path):
    app, _ = _make_app(tmp_path, username="", password="")
    client = TestClient(app)
    resp = client.get("/editor", auth=("admin", "secret"))
    assert resp.status_code == 401


def test_editor_lists_markdown_files(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor", auth=("admin", "secret"))
    assert resp.status_code == 200
    assert "PERSONALITY.md" in resp.text


def test_editor_get_file_content(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor/PERSONALITY.md", auth=("admin", "secret"))
    assert resp.status_code == 200
    assert "You are Chives." in resp.text


def test_editor_get_nonexistent_file_is_blank(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor/USER.md", auth=("admin", "secret"))
    assert resp.status_code == 200


def test_editor_index_has_new_file_form(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor", auth=("admin", "secret"))
    assert resp.status_code == 200
    assert 'id="new-file"' in resp.text


def test_editor_save_creates_new_file(tmp_path):
    app, profile_dir = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/editor/USER.md",
        json={"content": "The user likes tea."},
        auth=("admin", "secret"),
    )
    assert resp.status_code == 200
    assert (profile_dir / "USER.md").read_text() == "The user likes tea."


def test_editor_save_writes_file(tmp_path):
    app, profile_dir = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/editor/PERSONALITY.md",
        json={"content": "Updated personality."},
        auth=("admin", "secret"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert (profile_dir / "PERSONALITY.md").read_text() == "Updated personality."


def test_editor_save_rejects_path_traversal(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/editor/..%2F..%2Fetc%2Fpasswd.md",
        json={"content": "pwned"},
        auth=("admin", "secret"),
    )
    assert resp.status_code in (400, 404)


def test_editor_rejects_non_markdown_filename(tmp_path):
    app, _ = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/editor/secrets.txt", auth=("admin", "secret"))
    assert resp.status_code == 400
