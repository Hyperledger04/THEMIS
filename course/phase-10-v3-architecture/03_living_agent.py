"""
Phase 10, Lesson 3: The Living Agent — LexAgent Working While You Sleep

Today: LexAgent only works when the lawyer is online.
V3: lex worker runs 24/7, picks up jobs, prepares matter before you arrive.
"""
import asyncio
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel

print("=" * 60)
print("The Living Agent — 24/7 Background Worker")
print("=" * 60)

# ── SECTION 1: The gap ─────────────────────────────────────────────────────────
print("""
  Today's LexAgent:
    Lawyer opens laptop → sends brief → waits 60 seconds → gets draft
    Lawyer closes laptop → LexAgent stops

  V3 Living Agent:
    9:00 PM: Lawyer uploads 20 PDFs of case documents, goes home
    9:05 PM: Worker picks up "process_uploaded_documents" job
    9:30 PM: Worker finishes chronology, evidence table, research memo
    8:45 AM: Lawyer opens laptop → morning brief ready → starts drafting immediately

  The difference: compounding time savings. Every morning brief = 2-3 hours saved.
""")

# ── SECTION 2: Job model ──────────────────────────────────────────────────────
class Job(BaseModel):
    job_id: str
    firm_id: str
    matter_id: str
    job_type: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict] = None

    def model_post_init(self, __context):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


# Job types — what the living agent can do autonomously:
JOB_TYPES = {
    "process_uploaded_documents": "Extract text, chunk, extract dates/parties/facts",
    "extract_facts_and_issues":   "Build fact sheet and issue list from documents",
    "build_chronology":           "Create timeline of events from extracted dates",
    "create_research_memo":       "Research relevant case law for the matter",
    "create_risk_analysis":       "Identify weak points and adverse authorities",
    "deadline_scan":              "Check all limitation periods and court deadlines",
    "morning_brief":              "Summarize overnight work for the lawyer",
    "next_actions":               "Recommend what to do next on the matter",
    "draft_next_document":        "Draft the likely next required court document",
}

print("── Job Types the Living Agent Can Run ──")
for jtype, desc in JOB_TYPES.items():
    print(f"  {jtype:<35} {desc}")

# ── SECTION 3: In-memory job queue (Postgres in production) ───────────────────
class JobQueue:
    """In-memory job queue. Production: SELECT ... FROM jobs WHERE status='pending' FOR UPDATE SKIP LOCKED."""

    def __init__(self):
        self._jobs: list[Job] = []

    def enqueue(self, job: Job) -> None:
        self._jobs.append(job)
        print(f"  [queue] Enqueued: {job.job_type} for matter {job.matter_id}")

    def pop_next_pending(self) -> Optional[Job]:
        """Get oldest pending job (FIFO). Returns None if queue empty."""
        for job in self._jobs:
            if job.status == "pending":
                return job
        return None

    def update_status(self, job_id: str, status: str, **kwargs) -> None:
        for job in self._jobs:
            if job.job_id == job_id:
                job.status = status
                for k, v in kwargs.items():
                    setattr(job, k, v)

    def summary(self) -> dict:
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for job in self._jobs:
            counts[job.status] += 1
        return counts


# ── SECTION 4: Job handlers ───────────────────────────────────────────────────
async def handle_process_documents(job: Job) -> dict:
    """Stub: extract text from uploaded documents."""
    await asyncio.sleep(0.1)  # simulate work
    return {"pages_processed": 47, "facts_extracted": 12, "dates_found": 8}

async def handle_build_chronology(job: Job) -> dict:
    await asyncio.sleep(0.1)
    return {
        "chronology": [
            {"date": "2023-01-15", "event": "Cheque issued for ₹5,00,000"},
            {"date": "2023-03-01", "event": "Cheque presented for payment"},
            {"date": "2023-03-03", "event": "Cheque returned dishonoured"},
            {"date": "2023-03-20", "event": "Legal notice sent"},
            {"date": "2023-04-05", "event": "Notice period expired — no payment"},
        ]
    }

async def handle_morning_brief(job: Job) -> dict:
    await asyncio.sleep(0.1)
    return {
        "brief": (
            "Good morning. Overnight work on Sharma v. State:\n"
            "• Processed 47 pages → 12 facts, 8 key dates extracted\n"
            "• Chronology built: 5 timeline entries\n"
            "• WARNING: Limitation period expires in 8 days\n"
            "• Next recommended action: Draft complaint under Section 138 NI Act"
        )
    }

JOB_HANDLERS = {
    "process_uploaded_documents": handle_process_documents,
    "build_chronology": handle_build_chronology,
    "morning_brief": handle_morning_brief,
}

# ── SECTION 5: Worker loop ────────────────────────────────────────────────────
# THE APPROVAL RULE: the living agent may read, summarize, extract, draft, analyze.
# It must NOT file, send emails, message clients, or call external services
# without explicit lawyer approval. This is non-negotiable.

async def run_job(job: Job, queue: JobQueue) -> None:
    queue.update_status(job.job_id, "running", started_at=datetime.now().isoformat())
    print(f"  [worker] Running: {job.job_type} ({job.matter_id})")

    handler = JOB_HANDLERS.get(job.job_type)
    if not handler:
        queue.update_status(job.job_id, "failed", error=f"No handler for {job.job_type}")
        return

    try:
        result = await handler(job)
        queue.update_status(job.job_id, "completed",
                            completed_at=datetime.now().isoformat(),
                            result=result)
        print(f"  [worker] Done: {job.job_type} → {list(result.keys())}")
    except Exception as e:
        queue.update_status(job.job_id, "failed", error=str(e))
        print(f"  [worker] Failed: {job.job_type} — {e}")

async def worker_loop(queue: JobQueue, max_cycles: int = 5) -> None:
    """Runs until queue is empty (or max_cycles for demo safety)."""
    for cycle in range(max_cycles):
        job = queue.pop_next_pending()
        if not job:
            print(f"  [worker] Queue empty, sleeping...")
            break
        await run_job(job, queue)
        await asyncio.sleep(0.05)  # in production: sleep(10) between polls

# ── SECTION 6: Demo ───────────────────────────────────────────────────────────
print("\n── Simulating overnight job run ──\n")

async def demo():
    queue = JobQueue()
    matter_id = "sharma-v-state-138"

    # Lawyer uploads documents at 9 PM and goes home
    print("9:00 PM — Lawyer uploads documents, queues jobs:")
    queue.enqueue(Job(job_id="j001", firm_id="f1", matter_id=matter_id,
                     job_type="process_uploaded_documents"))
    queue.enqueue(Job(job_id="j002", firm_id="f1", matter_id=matter_id,
                     job_type="build_chronology"))
    queue.enqueue(Job(job_id="j003", firm_id="f1", matter_id=matter_id,
                     job_type="morning_brief"))

    print("\n9:05 PM — Worker starts processing:")
    await worker_loop(queue)

    print("\n8:45 AM — Morning brief for lawyer:")
    brief_job = next(j for j in queue._jobs if j.job_type == "morning_brief")
    print(brief_job.result["brief"])

    print(f"\nJob summary: {queue.summary()}")

asyncio.run(demo())

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Read LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md Section 8A.
     The roadmap says to use a Postgres 'jobs' table and FOR UPDATE SKIP LOCKED.
     Why does "SKIP LOCKED" matter when running multiple worker processes?

  2. The approval rule says the worker must NOT send emails without approval.
     Where in the job lifecycle would you add an approval gate?
     (Hint: see the roadmap's "approval_gates" field in ExecutionDAG)

  3. If the worker process crashes mid-job (status="running" but process died),
     how would you detect and recover stuck jobs in production?
     (Hint: check started_at + timeout threshold)

  4. Open lexagent/runtime/ — what files already exist? Does a worker.py exist?
     What's the current state vs the V3 plan?

  5. Morning brief content comes from job results. Who should approve the
     morning brief before it's sent to the lawyer via Telegram?
     Design the approval flow in 3 steps.
""")
