# ARQ job functions for the living agent worker.
#
# WHY ARQ not APScheduler: ARQ is a true async task queue backed by Redis.
# APScheduler (used for reminders) is cron-style; ARQ is work-queue style.
# A matter run can take minutes; ARQ gives durable retry, concurrency control,
# and a result store. APScheduler would block or lose jobs on crash.
#
# Job function signature: async def job(ctx, *args, **kwargs)
# ctx["redis"] is the ArqRedis pool — used to enqueue dependent jobs.
# ARQ serialises args/kwargs to Redis; all params must be JSON-serialisable.
#
# Key Invariant §1: Only Senior Counsel (via persist_matter_step) writes to
# Postgres. These jobs invoke the graph; they do not write matter rows directly.

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_matter_job(ctx: dict, matter_id: str, firm_id: str) -> dict:
    """
    ARQ job: resume or start a matter's Senior Counsel graph run.

    Loads the matter from Postgres (RLS-scoped to firm_id), then:
    - If status == "paused" AND next_action is set: resume from next_action params.
    - Otherwise: build an initial SeniorCounselState from the matter row and start fresh.

    Gracefully skips when no postgres_url is configured (dev / CI mode).
    """
    try:
        from themis.config import LexConfig
        cfg = LexConfig()

        if not cfg.postgres_url:
            logger.warning("run_matter_job: no postgres_url configured — skipping (dev mode)")
            return {"skipped": True, "reason": "no_postgres", "matter_id": matter_id}

        from themis.db.matter_store import MatterStore
        from themis.graph import get_graph

        store = MatterStore(cfg.postgres_url)
        matter = await store.get_matter(matter_id, firm_id=firm_id)

        if matter is None:
            logger.warning("run_matter_job: matter %s not found in firm %s", matter_id, firm_id)
            return {"error": f"matter {matter_id} not found", "matter_id": matter_id}

        graph = get_graph()
        # LANGGRAPH: thread_id scopes the checkpointer to this matter's run history.
        # Using matter_id (not a session UUID) means the graph can resume across
        # process restarts — the checkpointer finds the prior run by thread_id.
        config = {"configurable": {"thread_id": matter_id}}

        if matter.get("status") == "paused" and matter.get("next_action"):
            logger.info("run_matter_job: resuming paused matter %s", matter_id)
            # WHY next_action["params"]: structured JSON per Key Invariant §3 —
            # ARQ deserialises and invokes directly, no LLM step required.
            params = matter["next_action"].get("params") or {}
            result = await graph.ainvoke(params, config=config)
        else:
            logger.info("run_matter_job: starting fresh run for matter %s", matter_id)
            initial_state = _initial_state_from_matter(matter)
            result = await graph.ainvoke(initial_state, config=config)

        logger.info(
            "run_matter_job: matter %s completed with status=%s",
            matter_id,
            result.get("status"),
        )
        return {"matter_id": matter_id, "status": result.get("status", "complete")}

    except Exception as e:
        logger.exception("run_matter_job failed for matter %s", matter_id)
        return {"error": str(e), "matter_id": matter_id}


async def index_matter_job(ctx: dict, matter_id: str) -> dict:
    """
    ARQ job: async-index a matter summary into Qdrant for semantic search.

    WHY async (not inline in the graph): DrafterAgent needs judgments indexed
    synchronously (same run), but matter summaries are only needed for future
    searches — indexing them here, after the graph completes, adds zero latency
    to the lawyer's draft turn.

    V3.4 stub: logs the intent. Full Qdrant upsert wires in with R2C when the
    semantic memory layer (themis/memory/semantic.py) ships.
    """
    logger.info(
        "index_matter_job: matter %s queued for Qdrant summary indexing (stub — R2C)",
        matter_id,
    )
    # R2C implementation:
    # from themis.memory.semantic import upsert_matter_summary
    # await upsert_matter_summary(matter_id)
    return {"matter_id": matter_id, "indexed": False, "reason": "qdrant_stub_v34"}


async def recover_paused_matters(ctx: dict) -> dict:
    """
    Startup job: scan Postgres for paused matters and re-enqueue run_matter_job.

    WHY on_startup not a cron: if the worker process crashed mid-run, paused
    matters sit with status='paused' indefinitely. Scanning at startup heals them
    without a polling loop. The scan is idempotent — re-enqueueing an already-
    running matter is harmless because ARQ deduplicates by job_id when a
    job_id is supplied (we don't supply one here, so duplicates are possible
    on rapid restart — acceptable in V3.4, deduplication comes in V3.5).

    Gracefully skips when no postgres_url is configured (dev / CI mode).
    """
    try:
        from themis.config import LexConfig
        cfg = LexConfig()

        if not cfg.postgres_url:
            logger.debug("recover_paused_matters: no postgres_url — skipping")
            return {"recovered": 0, "reason": "no_postgres"}

        from themis.db.matter_store import MatterStore

        store = MatterStore(cfg.postgres_url)
        # list_matters with status filter — returns paused matters across all firms.
        # WHY no firm filter: recovery must be global; RLS is set inside run_matter_job.
        paused = await store.list_matters(status="paused")

        pool = ctx["redis"]
        count = 0
        for matter in paused:
            await pool.enqueue_job(
                "run_matter_job",
                matter["matter_id"],
                matter.get("firm_id", "default"),
            )
            count += 1
            logger.info(
                "recover_paused_matters: re-enqueued matter %s (firm %s)",
                matter["matter_id"],
                matter.get("firm_id"),
            )

        logger.info("recover_paused_matters: %d paused matter(s) re-enqueued", count)
        return {"recovered": count}

    except Exception as e:
        logger.exception("recover_paused_matters failed")
        return {"error": str(e), "recovered": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initial_state_from_matter(matter: dict) -> dict:
    """
    Build a minimal SeniorCounselState from a Postgres matter row.
    Used when a matter has no prior checkpoint to resume from.
    """
    return {
        "matter_id": matter.get("matter_id") or "",
        "firm_id": matter.get("firm_id") or "default",
        "matter_type": matter.get("matter_type") or "",
        "jurisdiction": matter.get("jurisdiction") or "",
        "parties": matter.get("parties") or [],
        "purpose": matter.get("purpose") or "",
        "status": "researching",
        "execution_plan": [],
        "active_specialist": None,
        "messages": [],
        "error": None,
    }
