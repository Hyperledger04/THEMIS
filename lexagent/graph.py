# LANGGRAPH: A StateGraph is the core concept in LangGraph.
# It is a directed graph where:
#   - Nodes are Python functions (sync or async) that receive LexState and return a partial dict
#   - Edges define the flow between nodes
#   - Conditional edges let the graph make routing decisions based on state values
#
# The graph is compiled once at startup and then invoked for each matter.
# Compilation validates the graph structure and returns a runnable object.

import logging

from langgraph.graph import END, StateGraph

from lexagent.config import LexConfig
from lexagent.nodes import cite, draft, intake, research, review
from lexagent.state import LexState

logger = logging.getLogger(__name__)

# WHY: Graph singleton — compiled once at module load, shared across all requests.
# Under Telegram concurrent load, rebuilding the graph per-request adds latency
# and prevents LangGraph's internal caching from working across invocations.
#
# Phase 9: _GRAPH is now a dict keyed by checkpointer type so we can hold both
# the Postgres-backed graph (production) and the in-memory graph (stub/tests)
# without rebuilding unnecessarily.
# Matter types that never benefit from case-law research.
# For these, intake routes directly to draft, skipping the research node entirely.
_NO_RESEARCH_TYPES = (
    "legal notice",
    "demand notice",
    "affidavit",
    "vakalatnama",
)

_GRAPHS: dict = {}


def get_graph(cfg: LexConfig | None = None):
    """
    Return the compiled graph. On first call, builds it and caches it.

    Phase 9: If cfg.postgres_url is set AND langgraph-checkpoint-postgres is
    installed, compiles with AsyncPostgresSaver for full native persistence.
    Falls back to MemorySaver when Postgres is not configured (dev/CI mode).

    WHY fall back rather than fail: The graph must be usable for tests and
    offline development where a Postgres instance isn't running.
    """
    global _GRAPHS
    if cfg is None:
        cfg = LexConfig()

    key = "postgres" if cfg.postgres_url else "memory"
    if key in _GRAPHS:
        return _GRAPHS[key]

    _GRAPHS[key] = _build_with_checkpointer(cfg)
    return _GRAPHS[key]


def _build_with_checkpointer(cfg: LexConfig):
    """Compile the graph with the appropriate checkpointer for the environment."""
    graph_def = build_graph()

    if cfg.postgres_url:
        try:
            # LANGGRAPH: AsyncPostgresSaver stores a full snapshot of LexState
            # after every node. Resuming a matter = calling graph.astream() with
            # the same thread_id — LangGraph reloads the last checkpoint automatically.
            # WHY: This replaces the manual session_store.py SQLite hack entirely.
            # Human-in-the-loop, time-travel debugging, and fault-tolerance are free.
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = AsyncPostgresSaver.from_conn_string(cfg.postgres_url)
            logger.info("Graph compiled with AsyncPostgresSaver (Postgres)")
            return graph_def.compile(checkpointer=checkpointer)
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-postgres not installed. "
                "Falling back to MemorySaver. Run: uv add langgraph-checkpoint-postgres"
            )
        except Exception as e:
            logger.warning("AsyncPostgresSaver failed (%s). Falling back to MemorySaver.", e)

    # Fallback: MemorySaver — state lives only for the process lifetime.
    # Fine for tests and single-session CLI use; not suitable for 24/7 production.
    from langgraph.checkpoint.memory import MemorySaver

    logger.info("Graph compiled with MemorySaver (no Postgres URL set)")
    return graph_def.compile(checkpointer=MemorySaver())


async def setup_checkpointer(cfg: LexConfig | None = None) -> None:
    """
    Run the one-time Postgres table setup for LangGraph checkpoints.

    LANGGRAPH: AsyncPostgresSaver.setup() creates the checkpoint tables
    (checkpoints, checkpoint_blobs, checkpoint_writes) if they don't exist.
    Call this once on server startup — it's idempotent.

    WHY separate from get_graph(): get_graph() is synchronous (called at import
    time for the singleton). Postgres setup requires async; call it explicitly
    from the FastAPI lifespan or the Telegram bot startup.
    """
    if cfg is None:
        cfg = LexConfig()
    if not cfg.postgres_url:
        return

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpointer = AsyncPostgresSaver.from_conn_string(cfg.postgres_url)
        await checkpointer.setup()
        logger.info("LangGraph Postgres checkpoint tables ready.")
    except ImportError:
        logger.warning("langgraph-checkpoint-postgres not installed; skipping setup.")
    except Exception as e:
        logger.error("Checkpoint setup failed: %s", e)


def invalidate_graph_cache() -> None:
    """Clear the graph cache — used in tests to force a fresh compile."""
    global _GRAPHS
    _GRAPHS.clear()


# -----------------------------------------------------------------------
# Routing functions — these are the "decision points" in the graph.
# LANGGRAPH: A conditional edge calls a routing function and routes to
# the node whose name matches the returned string.
# -----------------------------------------------------------------------


def _make_routes(cfg: LexConfig):
    """
    Return routing closures that capture a single LexConfig instance.
    WHY: Instantiating LexConfig() inside each routing call reads .env on
    every edge evaluation. Under concurrent Telegram users this adds unnecessary
    overhead. We capture cfg once at build_graph() time instead.
    """

    def route_after_intake(state: LexState) -> str:
        """
        After intake runs, decide what to do next:
        - If the lawyer hasn't answered all questions yet → loop back to intake
        - If workflow_mode is contract_review → skip research, go straight to contract_review
        - If all required fields are collected → move to research
        - If there was an error → end the graph
        """
        if state.get("error"):
            return END

        # LANGGRAPH: Returning a string here tells the graph which node to go to next.
        # This is how you implement loops — intake can route back to itself until done.
        if state.get("intake_complete"):
            # Phase 7: contract review branch bypasses the research → draft pipeline.
            if state.get("workflow_mode") == "contract_review":
                return "contract_review"
            # Skip research for document types that don't need case law.
            mt = (state.get("matter_type") or "").lower()
            if any(t in mt for t in _NO_RESEARCH_TYPES):
                return "draft"
            return "research"
        # WHY: return END (not "intake") so the graph yields back to the CLI after
        # each incomplete intake round. The CLI's while-loop re-invokes the graph
        # with the user's answers appended — this is the human-in-the-loop pattern.
        # Looping back to "intake" internally means the LLM runs multiple times
        # with no new user input, producing an infinite spinner with no questions shown.
        return END

    def route_after_research(state: LexState) -> str:
        """
        After research runs:
        - research_only=True → stop here (CLI renders a findings table, no draft)
        - otherwise → draft
        """
        if state.get("error"):
            return END
        if state.get("research_only"):
            return END
        return "draft"

    def route_after_draft(state: LexState) -> str:
        """
        After draft runs:
        - Phase 5: Route to cite (which feeds review) when research findings exist.
        - If no findings, skip cite and go directly to review for validation + .docx.
        """
        if state.get("error"):
            return END

        # WHY: cite needs a corpus to retrieve against. If no findings exist,
        # skip cite and go straight to review so we still get .docx output and
        # validation (length check, empty-draft check) without false unverified warnings.
        if cfg.auto_verify_citations and state.get("research_findings"):
            return "cite"
        return "review"

    return route_after_intake, route_after_research, route_after_draft


# -----------------------------------------------------------------------
# Graph assembly
# -----------------------------------------------------------------------


def build_graph() -> StateGraph:
    """
    Assemble the LangGraph StateGraph (without checkpointer).

    LANGGRAPH: StateGraph(LexState) creates a graph typed to our state.
    Every node in this graph must accept LexState and return a partial dict.

    Returns an uncompiled StateGraph. Call get_graph() to get the compiled,
    checkpointer-equipped runnable. Direct compile() calls are for tests only.

    Phase 9: Checkpointer is injected at compile time by get_graph() /
    _build_with_checkpointer() so the same graph definition works with both
    Postgres (production) and MemorySaver (tests/CLI).
    """
    cfg = LexConfig()
    route_after_intake, route_after_research, route_after_draft = _make_routes(cfg)

    # LANGGRAPH: StateGraph(LexState) tells LangGraph the shape of the state.
    # It uses this to validate that nodes return keys that exist in LexState.
    graph = StateGraph(LexState)

    # Import Phase 7 nodes here to avoid circular imports at module load time.
    from lexagent.nodes import contract_review

    # LANGGRAPH: add_node(name, function) registers a function as a named node.
    # The name is what routing functions return to navigate to this node.
    graph.add_node("intake", intake.run)
    graph.add_node("research", research.run)
    graph.add_node("draft", draft.run)
    graph.add_node("cite", cite.run)
    graph.add_node("review", review.run)
    graph.add_node("contract_review", contract_review.run)

    # LANGGRAPH: set_entry_point(name) defines where the graph starts.
    # Every graph.invoke() call begins at this node.
    graph.set_entry_point("intake")

    # LANGGRAPH: add_conditional_edges(source, routing_fn) calls routing_fn
    # after "source" runs and routes to whatever string it returns.
    # The routing function receives the full state and returns a node name or END.
    graph.add_conditional_edges("intake", route_after_intake)

    # LANGGRAPH: add_conditional_edges on draft too — handles cite-or-review routing.
    graph.add_conditional_edges("draft", route_after_draft)

    # research → draft normally; research_only=True → END
    graph.add_conditional_edges("research", route_after_research)

    # cite feeds into review; review is the terminal node in Phase 5
    # LANGGRAPH: first time chaining cite→review — review validates grounding
    # and writes the .docx if --output was requested.
    graph.add_edge("cite", "review")
    graph.add_edge("review", END)

    # Phase 7: contract_review is a terminal branch — goes straight to END.
    graph.add_edge("contract_review", END)

    return graph
