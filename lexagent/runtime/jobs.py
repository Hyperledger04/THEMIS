"""
MVP job handlers for the LexAgent living-agent worker.

Each handler is registered with @register_handler(job_type) and will be
picked up automatically by RuntimeWorker when a matching job is dequeued.

Approval gate rule (§8A Living Agent):
  Handlers may read, extract, draft, analyse, and recommend.
  They MUST NOT send emails, file documents, or mutate external systems.
  Any such action requires an AgentApproval record with status='approved'.

Job payload conventions:
  Every job payload is a plain dict stored in agent_jobs.payload_json.
  Required keys are documented on each handler.

Worker wiring: import this module to register all handlers before starting
the worker, e.g. in lex worker CLI:
    import lexagent.runtime.jobs  # noqa: F401
"""
from __future__ import annotations

import logging
from typing import Optional

from lexagent.runtime.worker import register_handler

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _get_workspace_repo(postgres_url: str):
    """Create a PostgresWorkspaceRepository from a known URL."""
    from lexagent.workspace.repository import PostgresWorkspaceRepository
    return PostgresWorkspaceRepository(postgres_url)


def _get_postgres_url() -> str:
    from lexagent.config import LexConfig
    cfg = LexConfig()
    url = cfg.postgres_url
    if not url:
        raise RuntimeError(
            "POSTGRES_URL not set. Set LEX_POSTGRES_URL or DATABASE_URL in your environment."
        )
    return url


async def _llm_call(system: str, user: str) -> str:
    """Provider-agnostic LLM call for job handlers. Uses ModelRouter so background
    jobs are not coupled to any specific provider SDK or LangGraph node layer."""
    from lexagent.providers.router import ModelRouter
    router = ModelRouter()
    result = await router.generate(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return result["content"]


# ------------------------------------------------------------------
# process_uploaded_documents
# ------------------------------------------------------------------

@register_handler("process_uploaded_documents")
async def handle_process_uploaded_documents(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Ingest a file that was uploaded to a matter.

    Required payload keys:
      file_path  — absolute path to the uploaded file
      firm_id    — owning firm (defaults to "default")
    """
    payload = job.payload
    file_path: Optional[str] = payload.get("file_path")
    firm_id: str = payload.get("firm_id", "default")

    if not file_path:
        raise ValueError("process_uploaded_documents job missing required 'file_path' in payload")

    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    from lexagent.ingestion.documents import ingest_file
    result = ingest_file(
        file_path=file_path,
        matter_id=job.matter_id,
        firm_id=firm_id,
        repo=ws_repo,
        run_id=job.run_id,
    )

    logger.info(
        "process_uploaded_documents: matter=%s file=%s pages=%d anchors=%d",
        job.matter_id,
        result.record.filename,
        len(result.pages),
        result.anchor_count,
    )

    # Enqueue extraction as a follow-on job so the worker processes it independently
    from datetime import datetime, timezone
    from lexagent.runtime.models import AgentJob
    extract_job = AgentJob(
        matter_id=job.matter_id,
        run_id=job.run_id,
        type="extract_facts_and_issues",
        agent="document_processing_agent",
        status="queued",
        requires_approval=False,
        payload={
            "document_id": result.record.document_id,
            "firm_id": firm_id,
        },
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    runtime_repo.create_job(extract_job)
    logger.info("Queued extract_facts_and_issues job %s", extract_job.job_id)


# ------------------------------------------------------------------
# extract_facts_and_issues
# ------------------------------------------------------------------

@register_handler("extract_facts_and_issues")
async def handle_extract_facts_and_issues(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Run LLM extraction on an already-ingested document.

    Required payload keys:
      document_id — ID of the DocumentRecord to process
      firm_id     — owning firm
    """
    payload = job.payload
    document_id: Optional[str] = payload.get("document_id")
    firm_id: str = payload.get("firm_id", "default")

    if not document_id:
        raise ValueError("extract_facts_and_issues missing required 'document_id' in payload")

    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    doc = ws_repo.get_document(document_id, job.matter_id, firm_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found in matter {job.matter_id}")

    # Reconstruct page text from the stored file
    from lexagent.ingestion.documents import _extract_text
    from pathlib import Path
    _, pages = _extract_text(Path(doc.storage_uri), doc.mime_type or "")

    anchors = ws_repo.get_anchors_for_document(document_id, job.matter_id, firm_id)

    from lexagent.ingestion.extractors import extract_from_pages, persist_extraction
    result = await extract_from_pages(
        matter_id=job.matter_id,
        document_id=document_id,
        pages=pages,
        anchors=anchors,
        llm_callable=_llm_call,
        run_id=job.run_id,
        extractor_agent="extraction_worker",
    )
    persist_extraction(result, ws_repo)

    logger.info(
        "extract_facts_and_issues: matter=%s doc=%s facts=%d chrono=%d parties=%d issues=%d deadlines=%d",
        job.matter_id, document_id,
        len(result.facts), len(result.chronology_items),
        len(result.parties), len(result.issues), len(result.deadlines),
    )


# ------------------------------------------------------------------
# build_chronology
# ------------------------------------------------------------------

@register_handler("build_chronology")
async def handle_build_chronology(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Assemble and log the sorted chronology for a matter.

    Required payload keys:
      firm_id — owning firm
    """
    firm_id: str = job.payload.get("firm_id", "default")
    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    from lexagent.ingestion.chronology import build_and_format_chronology
    entries, text = build_and_format_chronology(job.matter_id, firm_id, ws_repo)

    logger.info(
        "build_chronology: matter=%s entries=%d",
        job.matter_id, len(entries),
    )

    # Persist chronology as an artifact so the UI can display it
    from datetime import datetime, timezone
    from lexagent.runtime.models import AgentArtifact
    artifact = AgentArtifact(
        matter_id=job.matter_id,
        run_id=job.run_id,
        artifact_type="chronology",
        title=f"Matter Chronology ({len(entries)} events)",
        payload={"markdown": text, "entry_count": len(entries)},
    )
    runtime_repo.create_artifact(artifact)


# ------------------------------------------------------------------
# deadline_scan
# ------------------------------------------------------------------

@register_handler("deadline_scan")
async def handle_deadline_scan(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Scan upcoming deadlines for a matter and surface any that are due soon.

    Required payload keys:
      firm_id          — owning firm
      warning_days     — flag deadlines due within N days (default: 30)
    """
    firm_id: str = job.payload.get("firm_id", "default")
    warning_days: int = int(job.payload.get("warning_days", 30))

    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    deadlines = ws_repo.list_deadlines(job.matter_id, firm_id, status="upcoming")

    from datetime import date
    today = date.today()
    urgent = [
        d for d in deadlines
        if d.due_date
        and (date.fromisoformat(d.due_date[:10]) - today).days <= warning_days
    ]

    logger.info(
        "deadline_scan: matter=%s total_upcoming=%d urgent=%d",
        job.matter_id, len(deadlines), len(urgent),
    )

    if urgent:
        from datetime import datetime, timezone
        from lexagent.runtime.models import AgentArtifact
        lines = [
            f"- **{d.title}** — due {d.due_date} [{d.deadline_type}]"
            for d in sorted(urgent, key=lambda x: x.due_date)
        ]
        artifact = AgentArtifact(
            matter_id=job.matter_id,
            run_id=job.run_id,
            artifact_type="deadline_alert",
            title=f"{len(urgent)} deadline(s) due within {warning_days} days",
            payload={"deadlines": [d.model_dump() for d in urgent], "markdown": "\n".join(lines)},
        )
        runtime_repo.create_artifact(artifact)


# ------------------------------------------------------------------
# morning_brief
# ------------------------------------------------------------------

@register_handler("morning_brief")
async def handle_morning_brief(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Generate a morning brief for the lawyer summarising matter status,
    chronology, upcoming deadlines, and suggested next actions.

    Required payload keys:
      firm_id   — owning firm
      user_id   — lawyer receiving the brief
    """
    firm_id: str = job.payload.get("firm_id", "default")
    user_id: str = job.payload.get("user_id", "default")

    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    matter = ws_repo.get_matter(job.matter_id, firm_id)
    if not matter:
        raise ValueError(f"Matter {job.matter_id} not found for firm {firm_id}")

    from lexagent.ingestion.chronology import build_and_format_chronology
    _, chrono_text = build_and_format_chronology(job.matter_id, firm_id, ws_repo)

    deadlines = ws_repo.list_deadlines(job.matter_id, firm_id, status="upcoming")
    facts = ws_repo.list_facts(job.matter_id, firm_id)
    drafts = ws_repo.list_drafts(job.matter_id, firm_id)

    deadline_lines = "\n".join(
        f"- {d.title} — due {d.due_date}" for d in deadlines[:10]
    ) or "None recorded."

    system = (
        "You are a senior legal assistant preparing a morning brief for a lawyer. "
        "Be concise, professional, and actionable. Format as markdown."
    )
    user = (
        f"# Morning Brief: {matter.title}\n\n"
        f"**Matter type:** {matter.matter_type}\n"
        f"**Jurisdiction:** {matter.jurisdiction or 'Not specified'}\n\n"
        f"## Upcoming Deadlines\n{deadline_lines}\n\n"
        f"## Facts on record: {len(facts)}\n"
        f"## Drafts on record: {len(drafts)}\n\n"
        f"{chrono_text}\n\n"
        "Produce a brief that covers:\n"
        "1. Status summary (2-3 sentences)\n"
        "2. Priority actions for today\n"
        "3. Any deadline or risk alerts\n"
        "4. What the agent worked on overnight\n"
    )

    brief_text = await _llm_call(system, user)

    from datetime import datetime, timezone
    from lexagent.runtime.models import AgentArtifact
    artifact = AgentArtifact(
        matter_id=job.matter_id,
        run_id=job.run_id,
        artifact_type="morning_brief",
        title=f"Morning Brief — {matter.title}",
        payload={"markdown": brief_text, "user_id": user_id},
    )
    runtime_repo.create_artifact(artifact)
    logger.info("morning_brief generated for matter=%s user=%s", job.matter_id, user_id)


# ------------------------------------------------------------------
# next_actions
# ------------------------------------------------------------------

@register_handler("next_actions")
async def handle_next_actions(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Analyse the matter workspace and recommend the next 3-5 concrete actions.

    Required payload keys:
      firm_id — owning firm
    """
    firm_id: str = job.payload.get("firm_id", "default")
    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    matter = ws_repo.get_matter(job.matter_id, firm_id)
    if not matter:
        raise ValueError(f"Matter {job.matter_id} not found for firm {firm_id}")

    facts = ws_repo.list_facts(job.matter_id, firm_id)
    issues = ws_repo.list_issues(job.matter_id, firm_id)
    deadlines = ws_repo.list_deadlines(job.matter_id, firm_id, status="upcoming")
    drafts = ws_repo.list_drafts(job.matter_id, firm_id)
    documents = ws_repo.list_documents(job.matter_id, firm_id)

    system = (
        "You are a senior Indian litigation counsel advising a lawyer on next steps. "
        "Be specific, actionable, and grounded in the facts provided."
    )
    user = (
        f"# Matter: {matter.title} ({matter.matter_type})\n"
        f"Jurisdiction: {matter.jurisdiction or 'Not specified'}\n\n"
        f"**Documents ingested:** {len(documents)}\n"
        f"**Facts extracted:** {len(facts)}\n"
        f"**Issues identified:** {len(issues)}\n"
        f"**Drafts created:** {len(drafts)}\n"
        f"**Upcoming deadlines:** {len(deadlines)}\n\n"
        + (
            "**Open issues:**\n"
            + "\n".join(f"- {i.text}" for i in issues[:10])
            + "\n\n"
            if issues else ""
        )
        + (
            "**Upcoming deadlines:**\n"
            + "\n".join(f"- {d.title} (due {d.due_date})" for d in deadlines[:5])
            + "\n\n"
            if deadlines else ""
        )
        + "Based on the above, list the 3-5 most important next actions the lawyer should take. "
        "Format as a numbered markdown list. Each action should be specific and immediately actionable."
    )

    actions_text = await _llm_call(system, user)

    from datetime import datetime, timezone
    from lexagent.runtime.models import AgentArtifact
    artifact = AgentArtifact(
        matter_id=job.matter_id,
        run_id=job.run_id,
        artifact_type="next_actions",
        title=f"Next Actions — {matter.title}",
        payload={"markdown": actions_text},
    )
    runtime_repo.create_artifact(artifact)
    logger.info("next_actions generated for matter=%s", job.matter_id)


# ------------------------------------------------------------------
# draft_next_document
# ------------------------------------------------------------------

@register_handler("draft_next_document")
async def handle_draft_next_document(job, runtime_repo, ledger=None, halt_flag=None):
    """
    Draft the most likely next document for the matter based on current workspace state.

    Required payload keys:
      firm_id   — owning firm
      doc_type  — optional hint for document type (e.g. "legal_notice", "writ_petition")
    """
    firm_id: str = job.payload.get("firm_id", "default")
    doc_type_hint: str = job.payload.get("doc_type", "")

    postgres_url = _get_postgres_url()
    ws_repo = _get_workspace_repo(postgres_url)

    matter = ws_repo.get_matter(job.matter_id, firm_id)
    if not matter:
        raise ValueError(f"Matter {job.matter_id} not found for firm {firm_id}")

    from lexagent.ingestion.chronology import build_and_format_chronology
    _, chrono_text = build_and_format_chronology(job.matter_id, firm_id, ws_repo)

    parties = ws_repo.list_parties(job.matter_id, firm_id)
    facts = ws_repo.list_facts(job.matter_id, firm_id)
    issues = ws_repo.list_issues(job.matter_id, firm_id)
    authorities = ws_repo.list_authorities(job.matter_id, firm_id)

    party_lines = "\n".join(
        f"- {p.name} ({p.role})" for p in parties
    ) or "Not identified."
    fact_lines = "\n".join(
        f"- {f.text}" for f in facts[:20]
    ) or "No facts extracted yet."
    issue_lines = "\n".join(
        f"- {i.text}" for i in issues[:10]
    ) or "No issues identified yet."
    authority_lines = "\n".join(
        f"- {a.title} ({a.citation or 'no citation'}): {a.proposition}"
        for a in authorities[:10]
    ) or "No authorities identified yet."

    doc_type_str = f"Document type: {doc_type_hint}\n" if doc_type_hint else ""
    system = (
        "You are a senior Indian litigation counsel drafting a court-ready legal document. "
        "Use the matter facts and chronology to produce a complete, well-structured draft. "
        "Cite only the authorities provided. Do not hallucinate citations."
    )
    user = (
        f"# Draft: {matter.title}\n"
        f"Matter type: {matter.matter_type}\n"
        f"Jurisdiction: {matter.jurisdiction or 'Not specified'}\n"
        f"{doc_type_str}\n"
        f"## Parties\n{party_lines}\n\n"
        f"## Key Facts\n{fact_lines}\n\n"
        f"## Issues\n{issue_lines}\n\n"
        f"## Authorities\n{authority_lines}\n\n"
        f"{chrono_text}\n\n"
        "Produce a complete draft document. Structure it with proper legal headings. "
        "Mark any placeholder facts as [VERIFY: description]."
    )

    draft_text = await _llm_call(system, user)

    # Persist as workspace Draft (immutable — each invocation creates a new version)
    from lexagent.workspace.models import Draft
    existing_drafts = ws_repo.list_drafts(job.matter_id, firm_id)
    same_type = [d for d in existing_drafts if d.doc_type == (doc_type_hint or matter.matter_type)]
    version = len(same_type) + 1

    draft = Draft(
        matter_id=job.matter_id,
        doc_type=doc_type_hint or matter.matter_type,
        version=version,
        content=draft_text,
        status="draft",
    )
    ws_repo.create_draft(draft)

    # Also persist as runtime artifact so the morning brief can reference it
    from lexagent.runtime.models import AgentArtifact
    artifact = AgentArtifact(
        matter_id=job.matter_id,
        run_id=job.run_id,
        artifact_type="draft",
        title=f"Draft v{version}: {doc_type_hint or matter.matter_type}",
        payload={"draft_id": draft.draft_id, "doc_type": draft.doc_type, "version": version},
    )
    runtime_repo.create_artifact(artifact)
    logger.info(
        "draft_next_document: matter=%s doc_type=%s version=%d",
        job.matter_id, draft.doc_type, version,
    )
