import json
import pytest
from chives.tools.registry import tool, get_tools_schema, dispatch_tool, clear_registry


@pytest.fixture(autouse=True)
def reset_registry():
    clear_registry()
    yield
    clear_registry()


def test_tool_registers_schema():
    @tool
    def greet(name: str) -> str:
        """Say hello to someone."""
        return f"Hello {name}"

    schemas = get_tools_schema()
    assert len(schemas) == 1
    fn_schema = schemas[0]["function"]
    assert fn_schema["name"] == "greet"
    assert fn_schema["description"] == "Say hello to someone."
    assert fn_schema["parameters"]["properties"]["name"]["type"] == "string"
    assert "name" in fn_schema["parameters"]["required"]


async def test_dispatch_tool():
    @tool
    def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    result = await dispatch_tool("add", json.dumps({"a": 2, "b": 3}))
    assert result == "5"


async def test_dispatch_unknown_tool():
    result = await dispatch_tool("nonexistent", "{}")
    data = json.loads(result)
    assert "error" in data


async def test_dispatch_tool_exception():
    @tool
    def broken(x: str) -> str:
        """Always fails."""
        raise ValueError("oops")

    result = await dispatch_tool("broken", json.dumps({"x": "y"}))
    data = json.loads(result)
    assert "error" in data
    assert "oops" in data["error"]
