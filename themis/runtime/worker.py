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

import inspect

from themis.runtime.brakes import CostCapReached, CostLedger, HaltFlag

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

    def __init__(
        self,
        repo,
        poll_interval: float = 5.0,
        session_cap_usd: float = 0.0,
        job_cap_usd: float = 0.0,
        idle_timeout_minutes: int = 0,
    ) -> None:
        self._repo = repo
        self._poll_interval = poll_interval
        self._session_cap = session_cap_usd
        self._job_cap = job_cap_usd
        self._idle_timeout = idle_timeout_minutes
        self._session_spent: float = 0.0
        self._running = False

    async def run(self, max_jobs: Optional[int] = None) -> None:
        """
        Poll loop. Runs forever unless max_jobs is set (used in tests).
        Cancel the task to stop the worker gracefully.
        """
        self._running = True
        processed = 0
        logger.info("Themis runtime worker started.")

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

        # F3: Instantiate per-job brakes from worker config
        ledger = CostLedger(
            session_cap_usd=self._session_cap,
            job_cap_usd=self._job_cap,
            session_spent_so_far=self._session_spent,
        )
        halt_flag = HaltFlag(self._repo, idle_timeout_minutes=self._idle_timeout)

        # Check for external halt before starting the job
        halt_reason = halt_flag.should_halt(job.job_id)
        if halt_reason:
            logger.info("Job %s halted before start: %s", job.job_id, halt_reason)
            self._repo.cancel_job(job.job_id, reason=halt_reason)
            return

        self._repo.update_job_status(job.job_id, "running")
        logger.info("Executing job %s (type=%s, agent=%s)", job.job_id, job.type, job.agent)

        try:
            # Pass brake objects only to handlers that declare them in their signature.
            # WHY: Existing handlers take (job, repo) only; new handlers opt in to
            # ledger/halt_flag by declaring those keyword params.
            sig = inspect.signature(handler)
            kwargs = {}
            if "ledger" in sig.parameters:
                kwargs["ledger"] = ledger
            if "halt_flag" in sig.parameters:
                kwargs["halt_flag"] = halt_flag
            await handler(job, self._repo, **kwargs)
            # Persist accumulated cost back to session total
            self._session_spent += ledger.job_spent
            self._repo.update_job_status(job.job_id, "completed")
            logger.info("Job %s completed (cost $%.4f).", job.job_id, ledger.job_spent)
        except CostCapReached as exc:
            logger.warning("Job %s halted: %s", job.job_id, exc)
            self._session_spent += ledger.job_spent
            self._repo.cancel_job(job.job_id, reason=str(exc))
        except Exception as exc:
            logger.exception("Job %s failed: %s", job.job_id, exc)
            self._repo.fail_job(job.job_id, error=str(exc))

    def stop(self) -> None:
        self._running = False
