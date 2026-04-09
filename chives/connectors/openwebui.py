from __future__ import annotations
import json
import time
import uuid
from typing import Callable, Awaitable
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "chives"
    messages: list[ChatMessage] = []
    stream: bool = False


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

    return app
