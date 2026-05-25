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
            if not entry.get("_firm_id")  # exclude firm-scoped tools from global list
        ]

    @classmethod
    def register_langchain_tool(cls, tool, firm_id: str | None = None) -> None:
        """
        Register a pre-built LangChain StructuredTool directly.

        WHY: MCP/REST connectors produce LangChain StructuredTool objects directly
        (via langchain-mcp-adapters). This method lets them register without going
        through the @register decorator, which requires a plain Python callable.
        Optionally scoped to a firm via firm_id so connector tools don't leak
        across tenant boundaries.
        """
        cls._tools[tool.name] = {
            "fn": tool.func if hasattr(tool, "func") else tool.run,
            "name": tool.name,
            "description": tool.description,
            "schema": tool.args_schema.schema() if hasattr(tool, "args_schema") and tool.args_schema else {},
            "_langchain_tool": tool,
            "_firm_id": firm_id,
        }

    @classmethod
    def get_firm_tools(cls, firm_id: str) -> list:
        """
        Return LangChain StructuredTool objects registered for a specific firm.

        WHY: Multi-tenant connector tools are namespaced by firm_id so a tool
        registered by Firm A cannot be invoked by Firm B's agents.
        Returns both global tools (no firm_id) and firm-scoped tools for firm_id.
        """
        from langchain_core.tools import StructuredTool

        result = []
        for entry in cls._tools.values():
            entry_firm = entry.get("_firm_id")
            if entry_firm is not None and entry_firm != firm_id:
                continue  # belongs to a different firm
            if lc_tool := entry.get("_langchain_tool"):
                result.append(lc_tool)
            else:
                result.append(
                    StructuredTool.from_function(
                        func=entry["fn"],
                        name=entry["name"],
                        description=entry["description"],
                    )
                )
        return result

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Remove a tool from the registry by name.

        WHY: Connector tools must be removable at runtime — when a lawyer
        disconnects a third-party integration, its tools should stop appearing
        in the ReAct agent's tool list immediately without a restart.
        Returns True if the tool was found and removed, False if it was absent.
        """
        if name in cls._tools:
            del cls._tools[name]
            return True
        return False
