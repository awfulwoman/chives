from __future__ import annotations
import openai
from chives.config import Config
from chives.context import build_context
from chives.store import Store
from chives.tools.registry import get_tools_schema, dispatch_tool


class Agent:
    def __init__(self, config: Config, store: Store) -> None:
        self.client = openai.AsyncOpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
        )
        self.model = config.llm.model
        self.config = config
        self.store = store

    async def run(self, user_message: str, connector: str, thread_id: str) -> str:
        self.store.add_turn(connector, thread_id, "user", user_message)

        system = build_context(self.config, self.store, user_message)
        history = self.store.get_turns(connector, thread_id)
        messages = [{"role": "system", "content": system}, *history]

        schemas = get_tools_schema()

        while True:
            kwargs = {"model": self.model, "messages": messages}
            if schemas:
                kwargs["tools"] = schemas

            response = await self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    result = await dispatch_tool(tc.function.name, tc.function.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                content = choice.message.content or ""
                self.store.add_turn(connector, thread_id, "assistant", content)
                return content
