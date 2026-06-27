# LANGGRAPH: A StateGraph is the core concept in LangGraph.
# It is a directed graph where:
#   - Nodes are Python functions (sync or async) that receive SeniorCounselState and return a partial dict
#   - Edges define the flow between nodes
#   - Conditional edges let the graph make routing decisions based on state values
#
# V3.3: build_graph() now delegates to build_senior_counsel_graph() from
# themis/agents/senior_counsel.py. The external API (get_graph, setup_checkpointer,
# invalidate_graph_cache) is unchanged — callers are unaffected.

import logging

from langgraph.graph import StateGraph

from themis.config import LexConfig

logger = logging.getLogger(__name__)

# WHY: Graph singleton — compiled once at module load, shared across all requests.
# Under Telegram concurrent load, rebuilding the graph per-request adds latency
# and prevents LangGraph's internal caching from working across invocations.
#
# Phase 9: _GRAPH is now a dict keyed by checkpointer type so we can hold both
# the Postgres-backed graph (production) and the in-memory graph (stub/tests)
# without rebuilding unnecessarily.
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
# Graph assembly (V3.3 — delegates to Senior Counsel subgraph)
# -----------------------------------------------------------------------


def build_graph() -> StateGraph:
    """
    Assemble the LangGraph StateGraph (without checkpointer).

    V3.3: Delegates to build_senior_counsel_graph() from themis/agents/senior_counsel.py.
    The Senior Counsel subgraph coordinates specialist agents (researcher, drafter,
    reviewer, verification) via send() dispatch with an execution_plan queue.

    External callers (get_graph, CLI, gateways) are unchanged — only the internals changed.
    Returns an uncompiled StateGraph; get_graph() injects the checkpointer.
    """
    # WHY lazy import: avoids circular imports at module load time.
    # senior_counsel imports from themis.nodes; keeping it lazy breaks any cycle.
    from themis.agents.senior_counsel import build_senior_counsel_graph
    return build_senior_counsel_graph()
