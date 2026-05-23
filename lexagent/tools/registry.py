# WHY: Decorator-based self-registration so adding a new tool is dropping a file.
# No central list to maintain — tools announce themselves at import time.

from typing import Callable


class ToolRegistry:
    _tools: dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, description: str, schema: dict | None = None):
        """Decorator — registers a callable as a named tool at module import time."""
        def decorator(fn: Callable) -> Callable:
            cls._tools[name] = {
                "fn": fn,
                "name": name,
                "description": description,
                "schema": schema or {},
            }
            return fn
        return decorator

    @classmethod
    def get(cls, name: str) -> Callable:
        entry = cls._tools.get(name)
        if not entry:
            raise KeyError(
                f"Tool '{name}' not registered. Available: {list(cls._tools)}"
            )
        return entry["fn"]

    @classmethod
    def list_names(cls) -> list[str]:
        return list(cls._tools.keys())

    @classmethod
    def get_langchain_tools(cls) -> list:
        """
        Return tools as LangChain StructuredTool objects for bind_tools().

        # LANGGRAPH: bind_tools() attaches tool schemas to the LLM so it can emit
        # tool-call messages. StructuredTool wraps any Python callable with the
        # JSON schema LangChain needs to describe the tool to the model.
        """
        from langchain_core.tools import StructuredTool

        return [
            StructuredTool.from_function(
                func=entry["fn"],
                name=entry["name"],
                description=entry["description"],
            )
            for entry in cls._tools.values()
        ]
