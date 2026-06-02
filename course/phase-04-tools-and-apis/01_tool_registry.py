"""
Phase 4, Lesson 1: The Tool Registry Pattern
=============================================
Run with: python 01_tool_registry.py

The problem this lesson solves:
  Nodes in LexAgent need to call external APIs — search Indian Kanoon,
  calculate limitation periods, fetch documents. The WRONG approach is
  to import these functions directly inside nodes. The RIGHT approach is
  a registry: tools self-register, nodes look them up by name.

  Why? Because you want to add a new tool without touching any existing node.
  "Adding a tool = dropping a file in lexagent/tools/"
"""

# ── SECTION 1: THE PROBLEM ─────────────────────────────────────────────────────

print("=" * 60)
print("SECTION 1: Why a registry? The wrong approach first.")
print("=" * 60)

# WRONG WAY: direct imports inside a node
# This is what you DON'T want to do.

def research_node_WRONG(state):
    # This node is now COUPLED to specific tool implementations.
    # If you add a new tool, you must edit research_node_WRONG.
    # If kanoon_tool.py is renamed, this import breaks.
    # You cannot swap tools at runtime or inject mocks for testing.
    from some_tools_file import search_kanoon, calculate_limitation  # imaginary
    results = search_kanoon(state["matter_brief"])
    limitation = calculate_limitation(state["matter_type"], state["date"])
    return {"research_findings": results}

print("WRONG: research_node imports tools directly.")
print("  - Tight coupling: every new tool requires editing the node.")
print("  - Can't swap implementations (e.g., stub vs real API).")
print("  - Can't discover what tools are available at runtime.")
print()


# ── SECTION 2: THE REGISTRY PATTERN ───────────────────────────────────────────

print("=" * 60)
print("SECTION 2: The ToolRegistry — self-registration via decorator.")
print("=" * 60)

# This mirrors the actual pattern in lexagent/tools/registry.py.
# The real registry also converts tools to LangChain StructuredTool format,
# but let's build the core idea first.

class ToolRegistry:
    """
    A global registry for all LexAgent tools.

    Tools self-register using the @ToolRegistry.register decorator.
    Nodes call ToolRegistry.get("tool_name") to retrieve a function.
    No node ever imports a tool directly.
    """

    # WHY a class-level dict? It acts as module-level singleton state.
    # Every import of this class shares the same _tools dict.
    _tools: dict = {}

    @classmethod
    def register(cls, name: str, description: str, schema: dict):
        """
        Decorator factory: wraps a function and stores it in the registry.

        Usage:
            @ToolRegistry.register(
                name="search_kanoon",
                description="Search Indian Kanoon for case law",
                schema={"query": "string", "max_results": "int"}
            )
            def search_kanoon(query: str, max_results: int = 5) -> list:
                ...
        """
        def decorator(fn):
            # Store the function AND its metadata.
            # Metadata enables the LLM to understand what the tool does.
            cls._tools[name] = {
                "fn": fn,
                "description": description,
                "schema": schema,
            }
            print(f"  [Registry] Registered tool: '{name}'")
            # WHY return fn unchanged? The decorator must not break the
            # function — other code can still call it directly if needed.
            return fn
        return decorator

    @classmethod
    def get(cls, name: str):
        """Return the callable for a given tool name."""
        if name not in cls._tools:
            raise KeyError(f"Tool '{name}' not registered. Available: {list(cls._tools.keys())}")
        return cls._tools[name]["fn"]

    @classmethod
    def list_tools(cls) -> list[dict]:
        """Return a list of tool metadata — used to build prompts."""
        return [
            {"name": k, "description": v["description"], "schema": v["schema"]}
            for k, v in cls._tools.items()
        ]

    @classmethod
    def get_langchain_tools(cls):
        """
        Convert registered tools to LangChain StructuredTool format.

        This is what actually gets passed to llm.bind_tools(tools).
        bind_tools() appends the tool schemas to the LLM's system prompt,
        so the LLM knows it CAN call these tools and what args they take.

        The LLM then returns a response with a 'tool_calls' field when
        it wants to invoke a tool. The node extracts those calls,
        runs them through the registry, and returns results to the LLM.
        """
        # WHY not import LangChain here? This lesson file has no LangChain dep.
        # The real implementation in registry.py does:
        #   from langchain_core.tools import StructuredTool
        #   return [StructuredTool.from_function(fn=v["fn"], name=k, ...) for k, v in cls._tools.items()]
        # For now, return a simplified representation.
        return [
            {
                "type": "function",
                "function": {
                    "name": k,
                    "description": v["description"],
                    "parameters": {"type": "object", "properties": {
                        field: {"type": ftype}
                        for field, ftype in v["schema"].items()
                    }},
                }
            }
            for k, v in cls._tools.items()
        ]


# ── SECTION 3: TOOLS SELF-REGISTER ────────────────────────────────────────────

print()
print("=" * 60)
print("SECTION 3: Tools self-register — just drop a file.")
print("=" * 60)
print()

# In the real project, these would live in separate files:
#   lexagent/tools/kanoon_tool.py
#   lexagent/tools/limitation_tool.py
#
# Each file's module-level @ToolRegistry.register call fires when the file
# is imported. The __init__.py in lexagent/tools/ imports all tool files,
# so the registration happens automatically at startup.
#
# Adding a new tool = creating a new file + adding it to __init__.py.
# No existing code changes.

@ToolRegistry.register(
    name="search_kanoon",
    description="Search Indian Kanoon legal database for case law by keyword or citation.",
    schema={"query": "string", "max_results": "integer"},
)
def search_kanoon(query: str, max_results: int = 5) -> list:
    """
    Stub implementation — returns fake results so the lesson runs offline.
    The real implementation in lexagent/tools/kanoon_tool.py makes HTTP
    requests to api.indiankanoon.org when cfg.kanoon_mode == 'api'.
    """
    # WHY stub? Development doesn't require an API key. Tests run fast.
    return [
        {
            "tid": "stub-001",
            "title": "Maneka Gandhi v. Union of India",
            "citation": "AIR 1978 SC 597",
            "headline": f"Landmark case on Article 21 — personal liberty. Query was: '{query}'",
        },
        {
            "tid": "stub-002",
            "title": "K.S. Puttaswamy v. Union of India",
            "citation": "(2017) 10 SCC 1",
            "headline": "Nine-judge bench upheld right to privacy as fundamental right.",
        },
    ][:max_results]


@ToolRegistry.register(
    name="calculate_limitation",
    description="Calculate the limitation period deadline for a given matter type and cause of action date.",
    schema={"matter_type": "string", "cause_of_action_date": "string"},
)
def calculate_limitation(matter_type: str, cause_of_action_date: str) -> dict:
    """
    Compute when a claim expires under the Limitation Act 1963.
    The real implementation is in lexagent/tools/limitation_tool.py.
    """
    from datetime import date, timedelta

    PERIODS = {
        "money_suit": 3 * 365,          # Article 113, Schedule to Limitation Act
        "cheque_bounce": 30,            # Section 142(b), Negotiable Instruments Act
        "writ_petition": None,          # No limitation for constitutional remedies
        "specific_performance": 3 * 365,
        "tort": 3 * 365,
    }

    days = PERIODS.get(matter_type)
    cod = date.fromisoformat(cause_of_action_date)
    today = date.today()

    if days is None:
        return {
            "matter_type": matter_type,
            "deadline": "No statutory limitation",
            "days_remaining": None,
            "is_expired": False,
        }

    deadline = cod + timedelta(days=days)
    days_remaining = (deadline - today).days

    return {
        "matter_type": matter_type,
        "deadline": str(deadline),
        "days_remaining": days_remaining,
        "is_expired": days_remaining < 0,
    }


# ── SECTION 4: NODES USE THE REGISTRY ──────────────────────────────────────────

print()
print("=" * 60)
print("SECTION 4: Nodes look up tools by name — no direct imports.")
print("=" * 60)
print()

# RIGHT WAY: the node doesn't import specific tools.
# It asks the registry for whatever tool it needs by name.

def research_node_RIGHT(state: dict) -> dict:
    """
    A simplified version of lexagent/nodes/react_research.py.
    Notice: no tool imports. The node is tool-agnostic.
    """
    try:
        # 1. Retrieve the search function from the registry.
        search_fn = ToolRegistry.get("search_kanoon")

        # 2. Call it with the matter brief as query.
        results = search_fn(query=state.get("matter_brief", "article 21"), max_results=3)

        # 3. Return ONLY the changed state keys (LangGraph node contract).
        return {"research_findings": results}

    except Exception as e:
        # WHY catch everything here? Nodes must NEVER raise.
        # An exception would crash the entire graph run.
        # Set the error key instead — the graph can route on it.
        return {"error": str(e)}


# Simulate calling the node
fake_state = {"matter_brief": "right to life article 21 detention"}
result = research_node_RIGHT(fake_state)

print("Node result (only changed keys returned):")
for case in result["research_findings"]:
    print(f"  [{case['citation']}] {case['title']}")
    print(f"    {case['headline'][:80]}...")
print()


# ── SECTION 5: THE TOOL CALL FLOW ─────────────────────────────────────────────

print("=" * 60)
print("SECTION 5: How LLM tool calls flow through the registry.")
print("=" * 60)
print()

# When you do llm.bind_tools(ToolRegistry.get_langchain_tools()):
#
#   1. LangChain sends tool schemas in the system prompt to the LLM.
#   2. LLM decides to call a tool → returns:
#        response.tool_calls = [
#            {"name": "search_kanoon", "args": {"query": "article 21", "max_results": 5}}
#        ]
#   3. Your node reads response.tool_calls.
#   4. For each call: fn = ToolRegistry.get(call["name"]); result = fn(**call["args"])
#   5. Add result as a ToolMessage to messages list.
#   6. Send messages + result back to LLM.
#   7. LLM now has the search results and can reason about them.

# Let's simulate this flow manually:

def simulate_tool_call_flow():
    # Imagine the LLM returned this tool call request:
    llm_tool_calls = [
        {"name": "search_kanoon", "args": {"query": "maneka gandhi article 21"}},
        {"name": "calculate_limitation", "args": {
            "matter_type": "money_suit",
            "cause_of_action_date": "2022-01-15"
        }},
    ]

    print("Simulated LLM tool calls:")
    results = []
    for call in llm_tool_calls:
        print(f"  LLM wants: {call['name']}({call['args']})")
        fn = ToolRegistry.get(call["name"])
        result = fn(**call["args"])
        results.append({"tool": call["name"], "result": result})
        print(f"  Result: {str(result)[:100]}...")
        print()

    return results

simulate_tool_call_flow()

# Show what bind_tools sends to the LLM
print("Tool schemas sent to LLM via bind_tools():")
for tool_schema in ToolRegistry.get_langchain_tools():
    fn = tool_schema["function"]
    print(f"  Tool: {fn['name']}")
    print(f"  Desc: {fn['description'][:60]}...")
    print(f"  Args: {list(fn['parameters']['properties'].keys())}")
    print()

print("All registered tools:")
for tool_info in ToolRegistry.list_tools():
    print(f"  - {tool_info['name']}: {tool_info['description'][:50]}...")


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────

print()
print("=" * 60)
print("PAUSE AND THINK")
print("=" * 60)
print("""
1. Open lexagent/tools/registry.py. How does the real ToolRegistry differ
   from the one in this lesson? What extra validation does it do on
   tool names and schemas?

2. Open lexagent/tools/kanoon_tool.py. How does it decide between
   stub mode, api mode, and mcp mode? Which config field controls this,
   and where is that field defined?

3. The decorator @ToolRegistry.register runs at module import time.
   This means if two files register a tool with the same name, the
   second one silently overwrites the first. How would you add a guard
   against accidental overwriting? Would you raise an error or warn?

4. In lexagent/nodes/react_research.py, the node calls
   ToolRegistry.get_langchain_tools() and passes the result to
   llm.bind_tools(). What happens at the LangChain level when you
   call bind_tools()? What does the resulting LLM object look like
   compared to the original?

5. The registry pattern means nodes are tool-agnostic. But there is a
   hidden coupling: the node must know the tool's NAME as a string
   (e.g., "search_kanoon"). If that name changes, the node silently
   breaks at runtime. How does the real LexAgent protect against this?
   Hint: look for constants or an enum in lexagent/tools/.
""")
