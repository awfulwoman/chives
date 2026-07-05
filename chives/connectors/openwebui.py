from __future__ import annotations
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_MODEL_NAME = "chives:latest"
_MODEL_DIGEST = "sha256:" + "0" * 64


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


def create_app(agent_run: Callable[[str, str, str], Awaitable[str]]) -> FastAPI:
    app = FastAPI(title="Chives")

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
        thread_id = "openwebui"
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
