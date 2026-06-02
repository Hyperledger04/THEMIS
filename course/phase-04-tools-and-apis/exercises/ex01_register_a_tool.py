"""
Phase 4 — Exercise 1: Build a ToolRegistry from Scratch

Implement ToolRegistry with a @register decorator, then register 3 tools and call them.
"""
from datetime import date, timedelta
from typing import Any


# ── IMPLEMENT THIS ────────────────────────────────────────────────────────────

class ToolRegistry:
    _tools: dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, description: str):
        """
        Decorator factory. Usage:
            @ToolRegistry.register(name="my_tool", description="Does X")
            def my_tool(...): ...
        """
        def decorator(fn):
            # TODO: store fn and description in cls._tools[name]
            # cls._tools[name] = {"fn": fn, "description": description}
            return fn
        return decorator

    @classmethod
    def call(cls, name: str, **kwargs) -> Any:
        """Look up tool by name and call it with kwargs. Raise KeyError if not found."""
        # TODO: look up cls._tools[name]["fn"] and call it with **kwargs
        pass

    @classmethod
    def list_tools(cls) -> list[str]:
        """Return sorted list of registered tool names."""
        # TODO: return sorted(cls._tools.keys())
        pass

    @classmethod
    def describe(cls, name: str) -> str:
        """Return description of a tool."""
        # TODO: return cls._tools[name]["description"]
        pass


# ── REGISTER 3 TOOLS ─────────────────────────────────────────────────────────

# TODO: Use @ToolRegistry.register decorator to register each tool below.

# Tool 1: search_kanoon — stub returning 2 hardcoded cases
def search_kanoon(query: str) -> list[dict]:
    return [
        {"title": "Maneka Gandhi v. Union of India", "citation": "AIR 1978 SC 597"},
        {"title": "Kesavananda Bharati v. Kerala", "citation": "AIR 1973 SC 1461"},
    ]

# Tool 2: calculate_limitation — returns deadline info
PERIODS = {"money_suit": 3*365, "cheque_bounce": 30, "writ_petition": None}

def calculate_limitation(matter_type: str, days_since_coa: int) -> dict:
    period = PERIODS.get(matter_type)
    if period is None:
        return {"deadline": None, "note": "No fixed period — apply laches doctrine"}
    days_remaining = period - days_since_coa
    return {
        "period_days": period,
        "days_remaining": days_remaining,
        "is_expired": days_remaining < 0,
    }

# Tool 3: fetch_judgment — stub returning hardcoded text
def fetch_judgment(tid: str) -> str:
    return (
        f"[Judgment {tid}] The right to personal liberty under Article 21 "
        "includes the right to travel abroad. The passport cannot be impounded "
        "without hearing — Maneka Gandhi v. Union of India, AIR 1978 SC 597."
    )


# ── TESTS ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Registered tools:", ToolRegistry.list_tools())
    assert len(ToolRegistry.list_tools()) == 3, "Should have 3 tools"

    # Call search_kanoon
    results = ToolRegistry.call("search_kanoon", query="article 21 right to life")
    print(f"\nsearch_kanoon results: {len(results)} cases")
    for r in results:
        print(f"  - {r['title']} ({r['citation']})")

    # Call calculate_limitation
    lim = ToolRegistry.call("calculate_limitation", matter_type="money_suit", days_since_coa=900)
    print(f"\ncalculate_limitation: {lim}")

    # Call fetch_judgment
    text = ToolRegistry.call("fetch_judgment", tid="1234567")
    print(f"\nfetch_judgment preview: {text[:80]}...")

    print("\n✅ All tools registered and callable!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/registry.py — how does the real ToolRegistry differ?
#    Does it store a schema dict per tool? How is that used with bind_tools()?
# 2. Why does ToolRegistry use a class-level _tools dict instead of a module-level dict?
# 3. What happens if you register two tools with the same name? Is that a bug or a feature?
