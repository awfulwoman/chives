from __future__ import annotations
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from chives.config import Config
from chives.store import Store

_MODEL_NAME = "chives:latest"
_MODEL_DIGEST = "sha256:" + "0" * 64


def _thread_id(messages: list[ChatMessage], prefix: str = "openwebui") -> str:
    """Derive a stable thread ID from the first message so each conversation is isolated."""
    first = next((m.content for m in messages if m.role == "user"), "")
    digest = hashlib.sha1(first.encode()).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "chives"
    messages: list[ChatMessage] = []
    stream: bool = False


class OllamaChatRequest(BaseModel):
    model: str = _MODEL_NAME
    messages: list[ChatMessage] = []
    stream: bool = True
    # ignored: tools, keep_alive, options, think, format
    model_config = {"extra": "allow"}


class OllamaPullRequest(BaseModel):
    model: str
    stream: bool = True
    model_config = {"extra": "allow"}


def _status_html(config: Config, store: Store, started_at: float) -> str:
    stats = store.stats()
    uptime_s = int(time.time() - started_at)
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)
    uptime = f"{h}h {m}m {s}s"

    last = stats["last_turn"]
    if last:
        ts = datetime.fromtimestamp(last["created_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        last_html = f'<tr><td>Last turn</td><td>{last["connector"]} / {last["role"]} — {ts}</td></tr>'
    else:
        last_html = '<tr><td>Last turn</td><td>—</td></tr>'

    connector_rows = "".join(
        f"<tr><td>{c}</td><td>{n} turns</td></tr>"
        for c, n in stats["turns_by_connector"].items()
    ) or "<tr><td colspan='2'>No turns yet</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>Chives</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; margin: 0; padding: 2rem; }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.5rem; }}
    .sub {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 2rem; }}
    .badge {{ display: inline-block; background: #22c55e; color: #fff; font-size: 0.75rem; font-weight: 600;
              padding: 0.15rem 0.5rem; border-radius: 999px; vertical-align: middle; margin-left: 0.5rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }}
    .card {{ background: #1e2330; border-radius: 8px; padding: 1.25rem; }}
    .card h2 {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
                color: #64748b; margin: 0 0 0.75rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    td {{ padding: 0.3rem 0; }}
    td:first-child {{ color: #94a3b8; width: 50%; }}
    .num {{ font-size: 2rem; font-weight: 700; color: #e2e8f0; }}
    .num-label {{ font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }}
  </style>
</head>
<body>
  <h1>Chives <span class="badge">running</span></h1>
  <p class="sub">Uptime: {uptime} &nbsp;·&nbsp; Auto-refreshes every 30 s</p>
  <div class="grid">
    <div class="card">
      <h2>LLM</h2>
      <table>
        <tr><td>Model</td><td>{config.llm.model}</td></tr>
        <tr><td>Base URL</td><td>{config.llm.base_url}</td></tr>
        <tr><td>Morning brief</td><td>{config.morning_brief_time}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>Activity</h2>
      <table>
        <tr><td>Total turns</td><td>{stats["turn_total"]}</td></tr>
        {last_html}
        <tr><td>Emails seen</td><td>{stats["email_seen_count"]}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>Memory &amp; Nudges</h2>
      <table>
        <tr><td>Memory facts</td><td>{stats["memory_count"]}</td></tr>
        <tr><td>Pending nudges</td><td>{stats["pending_nudges"]}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>Connectors</h2>
      <table>{connector_rows}</table>
    </div>
  </div>
</body>
</html>"""


def create_app(agent_run: Callable[[str, str, str], Awaitable[str]], store: Store, config: Config) -> FastAPI:
    app = FastAPI(title="Chives")
    started_at = time.time()

    @app.get("/", response_class=HTMLResponse)
    async def status_page():
        return _status_html(config, store, started_at)

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [{
                "id": "chives-agent",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        user_msg = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )
        thread_id = _thread_id(req.messages)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if req.stream:
            async def generate():
                response = await agent_run(user_msg, "openwebui", thread_id)
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "chives-agent",
                    "choices": [{"index": 0, "delta": {"content": response}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                done_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "chives-agent",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        response = await agent_run(user_msg, "openwebui", thread_id)
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "chives-agent",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }],
        }

    @app.get("/api/tags")
    async def ollama_list_models():
        return {
            "models": [{
                "name": _MODEL_NAME,
                "model": _MODEL_NAME,
                "modified_at": _now_iso(),
                "size": 0,
                "digest": _MODEL_DIGEST,
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "chives",
                    "families": ["chives"],
                    "parameter_size": "0B",
                    "quantization_level": "Q0_0",
                },
            }]
        }

    @app.post("/api/pull")
    async def ollama_pull(req: OllamaPullRequest):
        if req.stream:
            async def pull_stream():
                yield json.dumps({"status": "success"}) + "\n"
            return StreamingResponse(pull_stream(), media_type="application/x-ndjson")
        return {"status": "success"}

    @app.post("/api/show")
    async def ollama_show(req: dict[str, Any]):
        return {
            "model_info": {},
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "chives",
                "families": ["chives"],
                "parameter_size": "0B",
                "quantization_level": "Q0_0",
            },
        }

    @app.post("/api/chat")
    async def ollama_chat(req: OllamaChatRequest):
        user_msg = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )
        thread_id = "homeassistant"

        if req.stream:
            async def generate():
                response = await agent_run(user_msg, "homeassistant", thread_id)
                chunk = {
                    "model": _MODEL_NAME,
                    "created_at": _now_iso(),
                    "message": {"role": "assistant", "content": response},
                    "done": False,
                }
                yield json.dumps(chunk) + "\n"
                done_chunk = {
                    "model": _MODEL_NAME,
                    "created_at": _now_iso(),
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 0,
                    "load_duration": 0,
                    "prompt_eval_count": 0,
                    "prompt_eval_duration": 0,
                    "eval_count": 0,
                    "eval_duration": 0,
                }
                yield json.dumps(done_chunk) + "\n"
            return StreamingResponse(generate(), media_type="application/x-ndjson")

        response = await agent_run(user_msg, "homeassistant", thread_id)
        return {
            "model": _MODEL_NAME,
            "created_at": _now_iso(),
            "message": {"role": "assistant", "content": response},
            "done": True,
            "done_reason": "stop",
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    return app
