# ARQ worker entrypoint — start with: python -m themis.worker.main
#
# LANGGRAPH: This process is separate from the control plane and Telegram gateway.
# It owns the long-running graph execution path. Gateways enqueue jobs; this
# worker picks them up, runs the Senior Counsel graph, and writes results back.
#
# WHY ARQ WorkerSettings class (not a function): ARQ discovers the settings class
# by name at startup. Class attributes are evaluated at import time, which is
# intentional — redis_settings must be a concrete RedisSettings instance, not a
# factory, because ARQ reads it before any async event loop starts.

from __future__ import annotations

import logging
import os

from themis.worker.jobs import index_matter_job, recover_paused_matters, run_matter_job

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    """
    Called once when the ARQ worker process starts.
    Scans Postgres for paused matters and re-enqueues them so interrupted
    runs are automatically resumed after a worker restart or crash.
    """
    logger.info("Themis worker starting — scanning for paused matters")
    result = await recover_paused_matters(ctx)
    logger.info("Startup recovery complete: %s", result)


def _redis_settings():
    """
    Build RedisSettings from REDIS_URL env var (or LexConfig if available).
    Evaluated at class-definition time — no async context needed.
    WHY not inline in class body: importing arq is conditional on the package
    being installed; wrapping in a function makes the import error explicit.
    """
    try:
        from arq.connections import RedisSettings
    except ImportError as e:
        raise ImportError(
            "arq is required for the worker. Run: uv add arq"
        ) from e

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        from themis.config import LexConfig
        cfg = LexConfig()
        redis_url = cfg.redis_url or redis_url
    except Exception:
        pass  # LexConfig unavailable at import time in some test contexts

    return RedisSettings.from_dsn(redis_url)


class WorkerSettings:
    """
    ARQ WorkerSettings — discovered by `arq themis.worker.main.WorkerSettings`
    or by `python -m themis.worker.main` (see __main__ block below).

    max_jobs = 10: allows up to 10 matters running concurrently per worker.
    job_timeout = 3600: research + draft can take up to 1 hour on large matters.
    keep_result = 3600: job results stay in Redis for 1 hour for status queries.
    """

    functions = [run_matter_job, index_matter_job, recover_paused_matters]
    on_startup = startup

    max_jobs: int = 10
    job_timeout: int = 3600   # seconds — long legal research jobs need time
    keep_result: int = 3600   # seconds — keep job results for status polling

    redis_settings = _redis_settings()


if __name__ == "__main__":
    from arq import run_worker

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("Starting Themis ARQ worker (press Ctrl+C to stop)")
    run_worker(WorkerSettings)
