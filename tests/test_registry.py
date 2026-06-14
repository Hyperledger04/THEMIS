"""Tests for ToolRegistry — write tests first, then implementation."""

import pytest
from themis.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def clear_registry():
    """Isolate each test — reset registry state before and after."""
    original = dict(ToolRegistry._tools)
    ToolRegistry._tools.clear()
    yield
    ToolRegistry._tools.clear()
    ToolRegistry._tools.update(original)


def test_register_stores_function():
    @ToolRegistry.register(name="my_tool", description="A test tool")
    def my_tool(x: int) -> int:
        return x * 2

    assert "my_tool" in ToolRegistry.list_names()


def test_get_returns_original_function():
    @ToolRegistry.register(name="double", description="Doubles a number")
    def double(x: int) -> int:
        return x * 2

    fn = ToolRegistry.get("double")
    assert fn(5) == 10


def test_get_raises_for_unknown_tool():
    with pytest.raises(KeyError, match="not registered"):
        ToolRegistry.get("nonexistent_tool")


def test_list_names_returns_all_registered():
    @ToolRegistry.register(name="tool_a", description="A")
    def tool_a(): ...

    @ToolRegistry.register(name="tool_b", description="B")
    def tool_b(): ...

    names = ToolRegistry.list_names()
    assert "tool_a" in names
    assert "tool_b" in names


def test_get_langchain_tools_returns_list():
    @ToolRegistry.register(name="greet", description="Says hello")
    def greet(name: str) -> str:
        return f"Hello {name}"

    tools = ToolRegistry.get_langchain_tools()
    assert isinstance(tools, list)
    assert len(tools) == 1


def test_langchain_tool_has_correct_name():
    @ToolRegistry.register(name="add", description="Adds two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    tools = ToolRegistry.get_langchain_tools()
    assert tools[0].name == "add"


def test_decorator_returns_original_function_unchanged():
    @ToolRegistry.register(name="identity", description="Returns input")
    def identity(x):
        return x

    assert identity(42) == 42
