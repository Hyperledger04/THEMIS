"""Tests for agent runtime models and worker — themis/runtime/."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from themis.runtime.models import (
    AgentApproval,
    AgentArtifact,
    AgentJob,
    AgentNotification,
    AgentRun,
    AgentStep,
    AgentToolCall,
    RuntimeEvent,
)
from themis.runtime.worker import RuntimeWorker, register_handler


class TestAgentRun:
    def test_defaults(self):
        r = AgentRun(matter_id="m_001", goal="Draft NI Act complaint")
        assert r.run_id.startswith("run_")
        assert r.status == "queued"
        assert r.firm_id == "default"

    def test_id_uniqueness(self):
        ids = {AgentRun(matter_id="m", goal="g").run_id for _ in range(30)}
        assert len(ids) == 30


class TestAgentJob:
    def test_defaults(self):
        j = AgentJob(matter_id="m", run_id="run_x", type="build_chronology", agent="chronology_agent")
        assert j.job_id.startswith("job_")
        assert j.status == "queued"
        assert not j.requires_approval

    def test_approval_required(self):
        j = AgentJob(
            matter_id="m", run_id="r", type="send_notice",
            agent="notification_agent", requires_approval=True,
        )
        assert j.requires_approval


class TestAgentStep:
    def test_defaults(self):
        s = AgentStep(job_id="job_x", run_id="run_x", name="extract_facts")
        assert s.step_id.startswith("step_")
        assert s.input_json == {}
        assert s.output_json == {}


class TestAgentToolCall:
    def test_defaults(self):
        tc = AgentToolCall(step_id="step_x", run_id="run_x", tool_name="kanoon_search")
        assert tc.tool_call_id.startswith("tool_")


class TestAgentArtifact:
    def test_defaults(self):
        a = AgentArtifact(matter_id="m", run_id="r", artifact_type="draft", title="Legal Notice")
        assert a.artifact_id.startswith("artifact_")
        assert a.source_anchor_ids == []


class TestAgentApproval:
    def test_defaults(self):
        a = AgentApproval(matter_id="m", run_id="r", requested_action="send_notice")
        assert a.approval_id.startswith("approval_")
        assert a.status == "pending"
        assert a.risk_level == "medium"

    def test_high_risk(self):
        a = AgentApproval(matter_id="m", run_id="r", requested_action="file_complaint", risk_level="high")
        assert a.risk_level == "high"


class TestAgentNotification:
    def test_defaults(self):
        n = AgentNotification(recipient="user@example.com", body="Your draft is ready.")
        assert n.notification_id.startswith("notif_")
        assert n.status == "queued"
        assert n.channel == "console"

    def test_telegram_channel(self):
        n = AgentNotification(recipient="123456789", body="Draft ready.", channel="telegram")
        assert n.channel == "telegram"


class TestRuntimeEvent:
    def test_defaults(self):
        e = RuntimeEvent(event_type="NEW_DOCUMENT")
        assert e.event_id.startswith("event_")
        assert e.payload == {}


# ---------------------------------------------------------------------------
# Worker tests (no real Postgres — mock repo)
# ---------------------------------------------------------------------------

def _make_mock_repo(jobs=None):
    repo = MagicMock()
    repo.get_queued_jobs.return_value = jobs or []
    return repo


class TestRuntimeWorker:
    def test_no_jobs_exits_when_max_reached(self):
        repo = _make_mock_repo(jobs=[])
        worker = RuntimeWorker(repo, poll_interval=0.01)
        asyncio.get_event_loop().run_until_complete(worker.run(max_jobs=0))
        # Should return immediately with no jobs processed

    def test_unknown_job_type_fails_job(self):
        job = AgentJob(matter_id="m", run_id="r", type="unknown_type", agent="drafting_agent")
        repo = _make_mock_repo(jobs=[job])
        worker = RuntimeWorker(repo, poll_interval=0.01)
        asyncio.get_event_loop().run_until_complete(worker.run(max_jobs=1))
        repo.fail_job.assert_called_once()
        call = repo.fail_job.call_args
        assert call[0][0] == job.job_id       # first positional = job_id
        assert "unknown_type" in call[1]["error"]  # keyword arg

    def test_registered_handler_called(self):
        executed = []

        @register_handler("test_job_type_xyz")
        async def _handler(job, repo):
            executed.append(job.job_id)

        job = AgentJob(matter_id="m", run_id="r", type="test_job_type_xyz", agent="drafting_agent")
        repo = _make_mock_repo(jobs=[job])
        worker = RuntimeWorker(repo, poll_interval=0.01)
        asyncio.get_event_loop().run_until_complete(worker.run(max_jobs=1))
        assert job.job_id in executed
        repo.update_job_status.assert_any_call(job.job_id, "running")
        repo.update_job_status.assert_any_call(job.job_id, "completed")

    def test_failing_handler_marks_job_failed(self):
        @register_handler("test_failing_job_xyz")
        async def _bad_handler(job, repo):
            raise RuntimeError("extraction failed")

        job = AgentJob(matter_id="m", run_id="r", type="test_failing_job_xyz", agent="drafting_agent")
        repo = _make_mock_repo(jobs=[job])
        worker = RuntimeWorker(repo, poll_interval=0.01)
        asyncio.get_event_loop().run_until_complete(worker.run(max_jobs=1))
        repo.fail_job.assert_called_once()
        call = repo.fail_job.call_args
        assert "extraction failed" in call[1]["error"]
