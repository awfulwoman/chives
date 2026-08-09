from __future__ import annotations
import html
import secrets
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from chives.config import Config


class SaveRequest(BaseModel):
    content: str


def _make_authenticator(config: Config):
    security = HTTPBasic()

    def authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> str:
        valid_user = config.editor.username
        valid_pass = config.editor.password
        user_ok = secrets.compare_digest(credentials.username, valid_user)
        pass_ok = secrets.compare_digest(credentials.password, valid_pass)
        if not valid_user or not valid_pass or not (user_ok and pass_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    return authenticate


def _resolve_path(profile_dir: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    candidate = (profile_dir / filename).resolve()
    if candidate.parent != profile_dir.resolve():
        raise HTTPException(status_code=400, detail="Invalid filename")
    return candidate


def _list_page(profile_dir: Path) -> str:
    files = sorted(p.name for p in profile_dir.glob("*.md")) if profile_dir.exists() else []
    items = "".join(
        f'<li><a href="/editor/{f}">{html.escape(f)}</a></li>' for f in files
    ) or "<li>No markdown files found.</li>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chives Profile Editor</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; padding: 2rem; }}
    a {{ color: #38bdf8; }}
    li {{ margin-bottom: 0.5rem; }}
    form {{ margin-top: 1.5rem; display: flex; gap: 0.5rem; }}
    input {{ background: #1e2330; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;
      padding: 0.5rem; font-family: ui-monospace, monospace; }}
    button {{ padding: 0.5rem 1.25rem; background: #22c55e; color: #0f1117; border: none;
      border-radius: 6px; font-weight: 600; cursor: pointer; }}
  </style>
</head>
<body>
  <h1>Profile Editor</h1>
  <ul>{items}</ul>
  <form id="new-file">
    <input id="new-filename" type="text" placeholder="NEWFILE.md" pattern="[^/\\\\]+\\.md" required>
    <button type="submit">New file</button>
  </form>
  <script>
    document.getElementById('new-file').addEventListener('submit', (e) => {{
      e.preventDefault();
      let name = document.getElementById('new-filename').value.trim();
      if (!name.endsWith('.md')) name += '.md';
      window.location.href = '/editor/' + encodeURIComponent(name);
    }});
  </script>
</body>
</html>"""


def _edit_page(filename: str, content: str) -> str:
    safe_name = html.escape(filename)
    escaped = html.escape(content)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Edit {safe_name} — Chives</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; padding: 2rem; }}
    textarea {{ width: 100%; height: 70vh; background: #1e2330; color: #e2e8f0; border: 1px solid #334155;
      border-radius: 6px; padding: 1rem; font-family: ui-monospace, monospace; font-size: 0.9rem; box-sizing: border-box; }}
    button {{ margin-top: 1rem; padding: 0.5rem 1.25rem; background: #22c55e; color: #0f1117; border: none;
      border-radius: 6px; font-weight: 600; cursor: pointer; }}
    a {{ color: #38bdf8; }}
    #status {{ margin-left: 1rem; color: #94a3b8; }}
  </style>
</head>
<body>
  <p><a href="/editor">&larr; back to files</a></p>
  <h1>{safe_name}</h1>
  <textarea id="content">{escaped}</textarea><br>
  <button id="save">Save</button>
  <span id="status"></span>
  <script>
    document.getElementById('save').addEventListener('click', async () => {{
      const statusEl = document.getElementById('status');
      statusEl.textContent = 'Saving...';
      try {{
        const resp = await fetch(window.location.pathname, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ content: document.getElementById('content').value }}),
        }});
        statusEl.textContent = resp.ok ? 'Saved.' : 'Error saving.';
      }} catch (e) {{
        statusEl.textContent = 'Error saving.';
      }}
    }});
  </script>
</body>
</html>"""


def register_editor_routes(app: FastAPI, config: Config) -> None:
    """Mount authenticated GET/POST /editor routes for editing profile markdown files."""
    profile_dir = Path(config.profile_path)
    authenticate = _make_authenticator(config)

    @app.get("/editor", response_class=HTMLResponse)
    async def editor_index(user: str = Depends(authenticate)):
        return _list_page(profile_dir)

    @app.get("/editor/{filename}", response_class=HTMLResponse)
    async def editor_get(filename: str, user: str = Depends(authenticate)):
        path = _resolve_path(profile_dir, filename)
        content = path.read_text() if path.exists() else ""
        return _edit_page(filename, content)

    @app.post("/editor/{filename}")
    async def editor_save(filename: str, req: SaveRequest, user: str = Depends(authenticate)):
        path = _resolve_path(profile_dir, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(req.content)
        return {"status": "ok"}
