"""
Agent runtime worker — polls for queued jobs and executes them.

MVP design: single-process, Postgres-backed, asyncio poll loop.
No Temporal/NATS/Kafka — those come when throughput demands it.

Approval gate rule: the worker may extract, draft, and research.
It must NOT send, file, or mutate external systems without an
AgentApproval record with status='approved'.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Registry: job_type -> async handler function
_HANDLERS: dict[str, Callable] = {}


def register_handler(job_type: str):
    """Decorator to register a coroutine as the handler for a job type."""
    def decorator(fn: Callable) -> Callable:
        _HANDLERS[job_type] = fn
        return fn
    return decorator


class RuntimeWorker:
    """
    Single-process job worker. Polls agent_jobs for queued work,
    records steps and tool calls, and persists output artifacts.

    Usage:
        worker = RuntimeWorker(repo)
        await worker.run()              # blocks until cancelled
        await worker.run(max_jobs=10)   # for tests / bounded runs
    """

    def __init__(self, repo, poll_interval: float = 5.0) -> None:
        self._repo = repo
        self._poll_interval = poll_interval
        self._running = False

    async def run(self, max_jobs: Optional[int] = None) -> None:
        """
        Poll loop. Runs forever unless max_jobs is set (used in tests).
        Cancel the task to stop the worker gracefully.
        """
        self._running = True
        processed = 0
        logger.info("LexAgent runtime worker started.")

        try:
            while self._running:
                jobs = self._repo.get_queued_jobs(limit=5)
                if not jobs:
                    if max_jobs is not None and processed >= max_jobs:
                        break
                    await asyncio.sleep(self._poll_interval)
                    continue

                for job in jobs:
                    if max_jobs is not None and processed >= max_jobs:
                        return
                    await self._execute_job(job)
                    processed += 1
        except asyncio.CancelledError:
            logger.info("Worker cancelled — shutting down.")
        finally:
            self._running = False

    async def _execute_job(self, job) -> None:
        handler = _HANDLERS.get(job.type)
        if handler is None:
            logger.warning("No handler registered for job type '%s' — marking failed.", job.type)
            self._repo.fail_job(job.job_id, error=f"No handler for job type: {job.type}")
            return

        self._repo.update_job_status(job.job_id, "running")
        logger.info("Executing job %s (type=%s, agent=%s)", job.job_id, job.type, job.agent)

        try:
            await handler(job, self._repo)
            self._repo.update_job_status(job.job_id, "completed")
            logger.info("Job %s completed.", job.job_id)
        except Exception as exc:
            logger.exception("Job %s failed: %s", job.job_id, exc)
            self._repo.fail_job(job.job_id, error=str(exc))

    def stop(self) -> None:
        self._running = False
