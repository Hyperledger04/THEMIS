"""Tests for themis/runtime/jobs.py — living-agent job handlers.

All tests run without Postgres or a real LLM by patching at two boundaries:
  - themis.runtime.jobs._get_postgres_url / _get_workspace_repo
  - themis.providers.router.ModelRouter.generate
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from themis.runtime.models import AgentJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(job_type: str, payload: dict | None = None) -> AgentJob:
    return AgentJob(
        matter_id="M-TEST",
        run_id="run_test",
        type=job_type,
        agent="document_processing_agent",
        status="queued",
        payload=payload or {},
    )


def _make_runtime_repo() -> MagicMock:
    repo = MagicMock()
    repo.create_job = MagicMock()
    repo.create_artifact = MagicMock()
    return repo


def _make_ws_repo(matter=None, facts=None, issues=None,
                  deadlines=None, drafts=None, documents=None,
                  parties=None, authorities=None, chronology=None) -> MagicMock:
    from themis.workspace.models import Matter
    ws = MagicMock()
    ws.get_matter = MagicMock(return_value=matter or Matter(
        matter_id="M-TEST", firm_id="firm_a",
        title="NI Act 138 Test", matter_type="criminal",
    ))
    ws.list_facts = MagicMock(return_value=facts or [])
    ws.list_issues = MagicMock(return_value=issues or [])
    ws.list_deadlines = MagicMock(return_value=deadlines or [])
    ws.list_drafts = MagicMock(return_value=drafts or [])
    ws.list_documents = MagicMock(return_value=documents or [])
    ws.list_parties = MagicMock(return_value=parties or [])
    ws.list_authorities = MagicMock(return_value=authorities or [])
    ws.list_chronology = MagicMock(return_value=chronology or [])
    ws.create_draft = MagicMock()
    return ws


# ---------------------------------------------------------------------------
# _llm_call — provider-agnostic routing
# ---------------------------------------------------------------------------

class TestLlmCall:
    @pytest.mark.asyncio
    async def test_uses_model_router(self):
        """_llm_call must call ModelRouter.generate — not call_llm from nodes."""
        from themis.runtime.jobs import _llm_call

        with patch(
            "themis.providers.router.ModelRouter.generate",
            new_callable=AsyncMock,
            return_value={"content": "test response", "parsed": None, "raw": None, "model": "x"},
        ) as mock_generate:
            result = await _llm_call("system prompt", "user prompt")

        assert result == "test response"
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][0]["content"] == "system prompt"
        assert call_kwargs["messages"][1]["role"] == "user"
        assert call_kwargs["messages"][1]["content"] == "user prompt"

    @pytest.mark.asyncio
    async def test_returns_content_string(self):
        """_llm_call must return a plain string, not a dict."""
        from themis.runtime.jobs import _llm_call

        with patch(
            "themis.providers.router.ModelRouter.generate",
            new_callable=AsyncMock,
            return_value={"content": "The cheque was dishonoured.", "parsed": None, "raw": None, "model": "x"},
        ):
            result = await _llm_call("sys", "user")

        assert isinstance(result, str)
        assert "cheque" in result


# ---------------------------------------------------------------------------
# handle_process_uploaded_documents
# ---------------------------------------------------------------------------

class TestProcessUploadedDocuments:
    @pytest.mark.asyncio
    async def test_enqueues_extract_job(self, tmp_path):
        """After ingestion, the handler must enqueue extract_facts_and_issues."""
        from themis.runtime.jobs import handle_process_uploaded_documents

        f = tmp_path / "brief.txt"
        f.write_text("The cheque was dishonoured on 14 March 2026.")

        job = _make_job("process_uploaded_documents", {
            "file_path": str(f),
            "firm_id": "firm_a",
        })
        runtime_repo = _make_runtime_repo()
        ws_repo = _make_ws_repo()

        from themis.ingestion.documents import IngestedDocument, PageText
        from themis.workspace.models import DocumentRecord
        fake_result = IngestedDocument(
            record=DocumentRecord(
                matter_id="M-TEST", firm_id="firm_a",
                filename="brief.txt", storage_uri=str(f),
            ),
            pages=[PageText(page=1, text="text", char_count=4)],
            anchor_count=2,
        )

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo), \
             patch("themis.ingestion.documents.ingest_file", return_value=fake_result):
            await handle_process_uploaded_documents(job, runtime_repo)

        runtime_repo.create_job.assert_called_once()
        enqueued = runtime_repo.create_job.call_args[0][0]
        assert enqueued.type == "extract_facts_and_issues"
        assert enqueued.payload["document_id"] == fake_result.record.document_id

    @pytest.mark.asyncio
    async def test_missing_file_path_raises(self):
        """Handler must raise ValueError when file_path is absent from payload."""
        from themis.runtime.jobs import handle_process_uploaded_documents

        job = _make_job("process_uploaded_documents", {})
        with pytest.raises(ValueError, match="file_path"):
            await handle_process_uploaded_documents(job, _make_runtime_repo())


# ---------------------------------------------------------------------------
# handle_build_chronology
# ---------------------------------------------------------------------------

class TestBuildChronology:
    @pytest.mark.asyncio
    async def test_creates_chronology_artifact(self):
        from themis.runtime.jobs import handle_build_chronology
        from themis.workspace.models import ChronologyItem

        items = [
            ChronologyItem(matter_id="M-TEST", date_text="14 March 2026",
                           event="Cheque dishonoured", normalized_date="2026-03-14"),
        ]
        ws_repo = _make_ws_repo(chronology=items)
        runtime_repo = _make_runtime_repo()
        job = _make_job("build_chronology", {"firm_id": "firm_a"})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo):
            await handle_build_chronology(job, runtime_repo)

        runtime_repo.create_artifact.assert_called_once()
        artifact = runtime_repo.create_artifact.call_args[0][0]
        assert artifact.artifact_type == "chronology"
        assert artifact.payload["entry_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_chronology_still_creates_artifact(self):
        from themis.runtime.jobs import handle_build_chronology

        ws_repo = _make_ws_repo(chronology=[])
        runtime_repo = _make_runtime_repo()
        job = _make_job("build_chronology", {"firm_id": "firm_a"})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo):
            await handle_build_chronology(job, runtime_repo)

        runtime_repo.create_artifact.assert_called_once()
        assert runtime_repo.create_artifact.call_args[0][0].payload["entry_count"] == 0


# ---------------------------------------------------------------------------
# handle_deadline_scan
# ---------------------------------------------------------------------------

class TestDeadlineScan:
    @pytest.mark.asyncio
    async def test_creates_alert_when_deadline_due_soon(self):
        from themis.runtime.jobs import handle_deadline_scan
        from themis.workspace.models import Deadline
        from datetime import date, timedelta

        soon = (date.today() + timedelta(days=5)).isoformat()
        deadlines = [Deadline(
            matter_id="M-TEST", title="Limitation deadline",
            due_date=soon, deadline_type="limitation",
        )]
        ws_repo = _make_ws_repo(deadlines=deadlines)
        runtime_repo = _make_runtime_repo()
        job = _make_job("deadline_scan", {"firm_id": "firm_a", "warning_days": 30})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo):
            await handle_deadline_scan(job, runtime_repo)

        runtime_repo.create_artifact.assert_called_once()
        artifact = runtime_repo.create_artifact.call_args[0][0]
        assert artifact.artifact_type == "deadline_alert"
        assert len(artifact.payload["deadlines"]) == 1

    @pytest.mark.asyncio
    async def test_no_artifact_when_no_urgent_deadlines(self):
        from themis.runtime.jobs import handle_deadline_scan
        from themis.workspace.models import Deadline
        from datetime import date, timedelta

        far = (date.today() + timedelta(days=120)).isoformat()
        deadlines = [Deadline(matter_id="M-TEST", title="Far deadline",
                              due_date=far, deadline_type="filing")]
        ws_repo = _make_ws_repo(deadlines=deadlines)
        runtime_repo = _make_runtime_repo()
        job = _make_job("deadline_scan", {"firm_id": "firm_a", "warning_days": 30})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo):
            await handle_deadline_scan(job, runtime_repo)

        runtime_repo.create_artifact.assert_not_called()


# ---------------------------------------------------------------------------
# handle_morning_brief
# ---------------------------------------------------------------------------

class TestMorningBrief:
    @pytest.mark.asyncio
    async def test_creates_morning_brief_artifact(self):
        from themis.runtime.jobs import handle_morning_brief

        ws_repo = _make_ws_repo()
        runtime_repo = _make_runtime_repo()
        job = _make_job("morning_brief", {"firm_id": "firm_a", "user_id": "lawyer_1"})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo), \
             patch("themis.runtime.jobs._llm_call", new_callable=AsyncMock,
                   return_value="## Morning Brief\n\nPriority: File reply today."):
            await handle_morning_brief(job, runtime_repo)

        runtime_repo.create_artifact.assert_called_once()
        artifact = runtime_repo.create_artifact.call_args[0][0]
        assert artifact.artifact_type == "morning_brief"
        assert "Morning Brief" in artifact.payload["markdown"]
        assert artifact.payload["user_id"] == "lawyer_1"

    @pytest.mark.asyncio
    async def test_raises_when_matter_not_found(self):
        from themis.runtime.jobs import handle_morning_brief

        ws_repo = _make_ws_repo()
        ws_repo.get_matter = MagicMock(return_value=None)
        job = _make_job("morning_brief", {"firm_id": "firm_a"})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo):
            with pytest.raises(ValueError, match="not found"):
                await handle_morning_brief(job, MagicMock())


# ---------------------------------------------------------------------------
# handle_next_actions
# ---------------------------------------------------------------------------

class TestNextActions:
    @pytest.mark.asyncio
    async def test_creates_next_actions_artifact(self):
        from themis.runtime.jobs import handle_next_actions

        ws_repo = _make_ws_repo()
        runtime_repo = _make_runtime_repo()
        job = _make_job("next_actions", {"firm_id": "firm_a"})

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo), \
             patch("themis.runtime.jobs._llm_call", new_callable=AsyncMock,
                   return_value="1. File vakalatnama\n2. Issue legal notice"):
            await handle_next_actions(job, runtime_repo)

        runtime_repo.create_artifact.assert_called_once()
        artifact = runtime_repo.create_artifact.call_args[0][0]
        assert artifact.artifact_type == "next_actions"
        assert "vakalatnama" in artifact.payload["markdown"]


# ---------------------------------------------------------------------------
# handle_draft_next_document
# ---------------------------------------------------------------------------

class TestDraftNextDocument:
    @pytest.mark.asyncio
    async def test_creates_draft_and_artifact(self):
        from themis.runtime.jobs import handle_draft_next_document

        ws_repo = _make_ws_repo()
        runtime_repo = _make_runtime_repo()
        job = _make_job("draft_next_document", {
            "firm_id": "firm_a", "doc_type": "legal_notice",
        })

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo), \
             patch("themis.runtime.jobs._llm_call", new_callable=AsyncMock,
                   return_value="LEGAL NOTICE\n\nTo: Respondent\n..."):
            await handle_draft_next_document(job, runtime_repo)

        ws_repo.create_draft.assert_called_once()
        draft = ws_repo.create_draft.call_args[0][0]
        assert draft.doc_type == "legal_notice"
        assert draft.version == 1
        assert "LEGAL NOTICE" in draft.content

        runtime_repo.create_artifact.assert_called_once()
        artifact = runtime_repo.create_artifact.call_args[0][0]
        assert artifact.artifact_type == "draft"

    @pytest.mark.asyncio
    async def test_increments_version_for_existing_drafts(self):
        from themis.runtime.jobs import handle_draft_next_document
        from themis.workspace.models import Draft

        existing = [Draft(matter_id="M-TEST", doc_type="legal_notice",
                          version=1, content="old content")]
        ws_repo = _make_ws_repo(drafts=existing)
        runtime_repo = _make_runtime_repo()
        job = _make_job("draft_next_document", {
            "firm_id": "firm_a", "doc_type": "legal_notice",
        })

        with patch("themis.runtime.jobs._get_postgres_url", return_value="postgres://test"), \
             patch("themis.runtime.jobs._get_workspace_repo", return_value=ws_repo), \
             patch("themis.runtime.jobs._llm_call", new_callable=AsyncMock,
                   return_value="REVISED LEGAL NOTICE\n..."):
            await handle_draft_next_document(job, runtime_repo)

        draft = ws_repo.create_draft.call_args[0][0]
        assert draft.version == 2
