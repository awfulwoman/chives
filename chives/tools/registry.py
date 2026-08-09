import inspect
import json
import logging
from functools import wraps
from typing import Callable, List

log = logging.getLogger(__name__)

_registry: dict[str, Callable] = {}
_schemas: list[dict] = []

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def tool(fn: Callable) -> Callable:
    """Register a function as an agent tool with OpenAI-compatible JSON schema."""
    name = fn.__name__
    doc = inspect.getdoc(fn) or ""
    sig = inspect.signature(fn)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        ann = param.annotation
        json_type = _TYPE_MAP.get(ann, "string")
        properties[param_name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    _registry[name] = fn
    _schemas.append({
        "type": "function",
        "function": {
            "name": name,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    })

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def get_tools_schema() -> List[dict]:
    return list(_schemas)


async def dispatch_tool(name: str, arguments: str) -> str:
    """Dispatch a tool call by name with JSON-encoded arguments. Returns JSON string."""
    fn = _registry.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        args = json.loads(arguments)
        result = fn(**args)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as exc:
        log.warning("Tool %s failed with args %s: %s", name, arguments, exc, exc_info=True)
        return json.dumps({"error": str(exc)})


def register_raw(name: str, schema: dict, fn: Callable) -> None:
    """Register a tool with a pre-built schema. For dynamic tool registration."""
    _registry[name] = fn
    _schemas.append(schema)


def clear_registry() -> None:
    """Clear all registered tools. Used in tests."""
    _registry.clear()
    _schemas.clear()
